#!/usr/bin/env python3
"""
Disposable bulk user importer for openIMIS (UAT).

Reads a CSV exported from the Google Form responses sheet and creates interactive
users via the openIMIS GraphQL `createUser` mutation — the SAME API the admin UI
uses. Nothing is installed into the openIMIS image, DB schema, or modules: this is
a standalone client. To discard it later, delete this folder (and, if you want,
deactivate the users in the admin UI). No migration, no fork, no image drift.

Stdlib only — no pip install. Runs anywhere with Python 3.8+.

Typical use:
    export OIMIS_ADMIN_USER=Admin
    export OIMIS_ADMIN_PASSWORD=...          # not echoed; prompted if unset
    # 1) find the default role id to assign everyone
    python3 import_users.py --url http://localhost:8080 --list-roles
    # 2) dry-run: validate the sheet, show new vs existing, create nothing
    python3 import_users.py --url http://localhost:8080 --csv users.csv \
        --role-id 17 --district-id 42 --dry-run
    # 3) real import
    python3 import_users.py --url http://localhost:8080 --csv users.csv \
        --role-id 17 --district-id 42

CSV columns (case-insensitive; override names with --col-*):
    first_name, last_name, username, email, password
Optional: phone
"""
import argparse
import csv
import getpass
import http.cookiejar
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import uuid

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class GraphQLClient:
    def __init__(self, base_url, insecure=False):
        self.graphql_url = base_url.rstrip("/") + "/api/graphql"
        self.cookies = http.cookiejar.CookieJar()
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            urllib.request.HTTPSHandler(context=ctx),
        )

    def execute(self, query, variables=None):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            self.graphql_url, data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=60) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} from {self.graphql_url}: {e.read().decode()[:300]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Cannot reach {self.graphql_url}: {e.reason}")
        if body.get("errors"):
            raise RuntimeError("GraphQL error: " + json.dumps(body["errors"])[:500])
        return body.get("data") or {}

    def login(self, username, password):
        data = self.execute(
            "mutation($u:String!,$p:String!){ tokenAuth(username:$u,password:$p){ token } }",
            {"u": username, "p": password},
        )
        if not (data.get("tokenAuth") or {}).get("token"):
            raise RuntimeError("Login failed — no token returned (check admin credentials).")


def resolve_int_id(node_id):
    """RoleGQLType.id may be a relay global id (base64 'Role:123'); return the int."""
    if node_id is None:
        return None
    s = str(node_id)
    if s.isdigit():
        return int(s)
    try:
        import base64
        decoded = base64.b64decode(s).decode()
        if ":" in decoded and decoded.split(":")[-1].isdigit():
            return int(decoded.split(":")[-1])
    except Exception:
        pass
    return s  # give back whatever we got so the user can see it


def list_roles(client):
    data = client.execute(
        "query{ role(first:500){ edges{ node{ id name isSystem isBlocked } } } }"
    )
    edges = (data.get("role") or {}).get("edges") or []
    print(f"{'ROLE_ID':<10} {'NAME':<40} SYSTEM")
    for e in edges:
        n = e["node"]
        print(f"{str(resolve_int_id(n.get('id'))):<10} {(n.get('name') or ''):<40} {n.get('isSystem')}")
    print(f"\n{len(edges)} roles. Pass one by name with --role-name (default 'IMIS Administrator') "
          f"or an explicit id with --role-id.")


def resolve_role_id(client, role_name):
    """Look up a role's integer id by NAME on THIS server (ids differ per deployment)."""
    data = client.execute("query{ role(first:1000){ edges{ node{ id name isSystem isBlocked } } } }")
    nodes = [e["node"] for e in ((data.get("role") or {}).get("edges") or [])]
    matches = [n for n in nodes
               if (n.get("name") or "").strip().lower() == role_name.strip().lower()
               and not n.get("isBlocked")]
    if not matches:
        avail = ", ".join(sorted({(n.get("name") or "") for n in nodes}))
        raise RuntimeError(f"role '{role_name}' not found. Available: {avail}")
    if len(matches) > 1:
        system = [n for n in matches if n.get("isSystem")]
        if len(system) == 1:
            matches = system
        else:
            raise RuntimeError(f"role name '{role_name}' is ambiguous ({len(matches)} matches).")
    return resolve_int_id(matches[0]["id"])


def user_exists(client, username):
    # 'username' is the exact filter arg (django-filter names the default lookup by the
    # bare field) and a valid output field on UserGQLType. Match case-insensitively.
    data = client.execute(
        "query($u:String!){ users(username:$u, first:5){ edges{ node{ username } } } }",
        {"u": username},
    )
    edges = (data.get("users") or {}).get("edges") or []
    return any((e["node"].get("username") or "").lower() == username.lower() for e in edges)


def create_user(client, row, role_ids, district_ids, language):
    cmid = str(uuid.uuid4())
    variables = {"input": {
        "clientMutationId": cmid,
        "clientMutationLabel": f"UAT bulk create {row['username']}",
        "otherNames": row["first_name"],
        "lastName": row["last_name"],
        "username": row["username"],
        "email": row["email"],
        "password": row["password"],
        "language": language,
        "userTypes": ["INTERACTIVE"],
        "roles": role_ids,
    }}
    # districts are optional on the backend (only the UI makes them mandatory) — send
    # the field only when ids are actually provided.
    if district_ids:
        variables["input"]["districts"] = district_ids
    client.execute(
        "mutation($input:CreateUserMutationInput!){ createUser(input:$input){ clientMutationId internalId } }",
        variables,
    )
    # createUser runs synchronously and records a MutationLog (status: RECEIVED=0,
    # ERROR=1, SUCCESS=2) with any validation error. Try to read it for a precise
    # reason, but never let a log-query hiccup mask a successful create — the
    # existence check below is authoritative.
    try:
        log = client.execute(
            "query($id:String!){ mutationLogs(clientMutationId:$id, first:1){ edges{ node{ status error } } } }",
            {"id": cmid},
        )
        edges = (log.get("mutationLogs") or {}).get("edges") or []
        if edges:
            node = edges[0]["node"]
            if node.get("status") == 1 and not user_exists(client, row["username"]):
                return False, node.get("error") or "mutation reported ERROR"
    except RuntimeError:
        pass
    if user_exists(client, row["username"]):
        return True, None
    return False, "user not found after create (see server logs)"


COLS = ("first_name", "last_name", "username", "email", "password")


def load_rows(path, colmap):
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
        resolved = {}
        for key in COLS + ("phone", "team"):
            wanted = colmap.get(key, key).strip().lower()
            if wanted in headers:
                resolved[key] = headers[wanted]
        missing = [c for c in COLS if c not in resolved]
        if missing:
            raise RuntimeError(
                f"CSV is missing required column(s): {', '.join(missing)}. "
                f"Found headers: {list(reader.fieldnames or [])}. "
                f"Use --col-<field> to map to the Google Form's column titles."
            )
        rows = []
        for i, raw in enumerate(reader, start=2):  # row 1 = header
            rows.append({"_line": i, **{k: (raw.get(v) or "").strip() for k, v in resolved.items()}})
        return rows


def validate(rows, max_username, pw_min=8):
    seen_user, seen_email = {}, {}
    for r in rows:
        errs = []
        for c in COLS:
            if not r.get(c):
                errs.append(f"missing {c}")
        u = r.get("username", "")
        if u and len(u) > max_username:
            errs.append(f"username >{max_username} chars ({len(u)})")
        if u and not re.fullmatch(r"[A-Za-z0-9_.\-]+", u):
            errs.append("username has spaces/invalid chars")
        if r.get("email") and not EMAIL_RE.match(r["email"]):
            errs.append("invalid email")
        # openIMIS default password policy: >=pw_min chars, >=1 upper, >=1 lower, >=1 digit.
        # (Server also rejects passwords too similar to the name/username/email.)
        pw = r.get("password", "")
        if pw:
            if len(pw) < pw_min:
                errs.append(f"password <{pw_min} chars")
            if not any(c.isupper() for c in pw):
                errs.append("password needs an uppercase letter")
            if not any(c.islower() for c in pw):
                errs.append("password needs a lowercase letter")
            if not any(c.isdigit() for c in pw):
                errs.append("password needs a digit")
        if u:
            if u.lower() in seen_user:
                errs.append(f"duplicate username in file (line {seen_user[u.lower()]})")
            else:
                seen_user[u.lower()] = r["_line"]
        em = r.get("email", "").lower()
        if em:
            if em in seen_email:
                errs.append(f"duplicate email in file (line {seen_email[em]})")
            else:
                seen_email[em] = r["_line"]
        r["_errors"] = errs
    return rows


def parse_int_list(cell):
    return [int(x) for x in re.split(r"[;,]", cell or "") if x.strip()]


def load_servers(path):
    """servers.csv: team,url[,role_ids,district_ids,insecure]. ids are ;-separated.
    role_ids/district_ids are OPTIONAL: leave role_ids blank to resolve --role-name
    ('IMIS Administrator') per server; leave district_ids blank to assign none."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = {h.strip().lower(): h for h in (reader.fieldnames or [])}
        for req in ("team", "url"):
            if req not in headers:
                raise RuntimeError(f"servers file missing column '{req}'. Found: {list(reader.fieldnames or [])}")
        servers = {}
        for raw in reader:
            g = lambda k: (raw.get(headers[k]) or "").strip() if k in headers else ""
            team = g("team").lower()
            if not team:
                continue
            servers[team] = {
                "team": team,
                "url": g("url"),
                "role_ids": parse_int_list(g("role_ids")),      # empty -> resolve by name
                "district_ids": parse_int_list(g("district_ids")),
                "insecure": g("insecure").lower() in ("1", "true", "yes"),
            }
        if not servers:
            raise RuntimeError("no servers defined in " + path)
        return servers


def creds_for(team, args):
    """Per-server admin creds: env OIMIS_ADMIN_*_<TEAM> overrides the shared OIMIS_ADMIN_*."""
    key = re.sub(r"[^A-Z0-9]", "_", team.upper())
    user = (os.environ.get(f"OIMIS_ADMIN_USER_{key}") or args.admin_user
            or input(f"[{team}] Admin username: ").strip())
    pw = (os.environ.get(f"OIMIS_ADMIN_PASSWORD_{key}") or args.admin_password
          or getpass.getpass(f"[{team}] Admin password: "))
    return user, pw


def run_server(label, client, rows, role_ids, district_ids, language, dry_run):
    """Process one server's rows. Returns (ok, skip, fail)."""
    ok = skip = fail = 0
    for r in rows:
        tag = r["username"] or "(blank)"
        prefix = f"[{label}] {r['_line']:<4} {tag:<14}"
        try:
            if user_exists(client, r["username"]):
                skip += 1
                print(f"{prefix} SKIP (already exists)")
                continue
        except RuntimeError as e:
            fail += 1
            print(f"{prefix} FAIL (existence check: {e})")
            continue
        if dry_run:
            print(f"{prefix} would CREATE")
            continue
        try:
            success, err = create_user(client, r, role_ids, district_ids, language)
            if success:
                ok += 1
                print(f"{prefix} CREATED")
            else:
                fail += 1
                print(f"{prefix} FAIL: {err}")
        except RuntimeError as e:
            fail += 1
            print(f"{prefix} FAIL: {e}")
    return ok, skip, fail


def run_multi(args, servers):
    rows = validate(load_rows(args.csv, {c: getattr(args, f"col_{c}") for c in COLS + ("phone", "team")
                                          if getattr(args, f"col_{c}")}),
                    args.max_username, args.password_min_length)
    # every row needs a team that maps to a known server
    for r in rows:
        if not r.get("team"):
            r["_errors"].append("missing team")
        elif r["team"].lower() not in servers:
            r["_errors"].append(f"unknown team '{r['team']}' (no matching server)")

    by_team = {}
    invalid = 0
    for r in rows:
        if r["_errors"]:
            invalid += 1
            print(f"{r['_line']:<5} {r['username'] or '(blank)':<14} INVALID: {'; '.join(r['_errors'])}")
            continue
        by_team.setdefault(r["team"].lower(), []).append(r)

    totals = {"ok": 0, "skip": 0, "fail": 0}
    for team, srv in servers.items():
        team_rows = by_team.get(team, [])
        print(f"\n=== server '{team}' ({srv['url']}) — {len(team_rows)} user(s) ===")
        if not team_rows:
            print("  (no users for this team)")
            continue
        client = GraphQLClient(srv["url"], insecure=srv["insecure"])
        try:
            client.login(*creds_for(team, args))
        except RuntimeError as e:
            print(f"  [login] FAILED: {e} — skipping this server ({len(team_rows)} users not created).")
            totals["fail"] += len(team_rows)
            continue
        # role ids are per-deployment: use the explicit servers.csv override if given,
        # else resolve by name ('IMIS Administrator') on THIS server.
        try:
            role_ids = srv["role_ids"] or [resolve_role_id(client, args.role_name)]
        except RuntimeError as e:
            print(f"  [role] FAILED: {e} — skipping this server ({len(team_rows)} users not created).")
            totals["fail"] += len(team_rows)
            continue
        print(f"  role -> {role_ids} ('{args.role_name}')   district -> {srv['district_ids'] or 'none (optional)'}")
        o, s, fl = run_server(team, client, team_rows, role_ids, srv["district_ids"], args.language, args.dry_run)
        totals["ok"] += o; totals["skip"] += s; totals["fail"] += fl

    routed = sum(len(v) for v in by_team.values())
    print("\n--- overall summary ---")
    print(f"servers: {len(servers)}   routed users: {routed}   invalid/unrouted: {invalid}")
    if args.dry_run:
        print("dry-run: nothing was created.")
    else:
        print(f"created: {totals['ok']}   skipped(existing): {totals['skip']}   failed: {totals['fail']}")


def main():
    ap = argparse.ArgumentParser(description="Bulk-create openIMIS UAT users from a CSV (single or multi-server).")
    ap.add_argument("--url", help="Single-server base URL, e.g. http://localhost:8080 (omit when using --servers)")
    ap.add_argument("--servers", help="CSV mapping team,url,role_ids,district_ids[,insecure] — fans out to all servers")
    ap.add_argument("--csv", help="Path to the responses CSV")
    ap.add_argument("--role-name", default="IMIS Administrator", help="Role to assign, looked up by name per server (default 'IMIS Administrator')")
    ap.add_argument("--role-id", type=int, action="append", default=[], help="Explicit role id override (repeatable); skips the name lookup")
    ap.add_argument("--district-id", type=int, action="append", default=[], help="Optional district (type-D location) id (repeatable). District is NOT required by the backend.")
    ap.add_argument("--language", default="en")
    ap.add_argument("--max-username", type=int, default=12, help="Max username length (openIMIS username_code_length, default 12)")
    ap.add_argument("--password-min-length", type=int, default=8, help="Min password length for pre-flight check (default 8)")
    ap.add_argument("--admin-user", default=os.environ.get("OIMIS_ADMIN_USER"))
    ap.add_argument("--admin-password", default=os.environ.get("OIMIS_ADMIN_PASSWORD"))
    ap.add_argument("--insecure", action="store_true", help="Skip TLS verification (self-signed certs)")
    ap.add_argument("--dry-run", action="store_true", help="Validate + report only; create nothing")
    ap.add_argument("--list-roles", action="store_true", help="Print role ids and exit")
    for c in COLS + ("phone",):
        ap.add_argument(f"--col-{c.replace('_','-')}", dest=f"col_{c}", help=f"CSV header for '{c}'")
    args = ap.parse_args()

    if args.servers:
        if not args.csv:
            sys.exit("--csv is required with --servers.")
        run_multi(args, load_servers(args.servers))
        return
    if not args.url:
        sys.exit("Provide --url (single server) or --servers (multi-server routing).")

    client = GraphQLClient(args.url, insecure=args.insecure)

    # Auth (read-only list-roles still needs a session).
    admin_user = args.admin_user or input("Admin username: ").strip()
    admin_pw = args.admin_password or getpass.getpass("Admin password: ")
    try:
        client.login(admin_user, admin_pw)
    except RuntimeError as e:
        sys.exit(f"[login] {e}")
    print(f"[login] OK as {admin_user} @ {args.url}")

    if args.list_roles:
        list_roles(client)
        return

    if not args.csv:
        sys.exit("--csv is required (or use --list-roles).")
    colmap = {c: getattr(args, f"col_{c}") for c in COLS + ("phone",) if getattr(args, f"col_{c}")}
    rows = validate(load_rows(args.csv, colmap), args.max_username, args.password_min_length)

    # Resolve the role id for THIS server: explicit --role-id wins, else look up --role-name.
    role_ids = list(args.role_id)
    if not role_ids:
        try:
            role_ids = [resolve_role_id(client, args.role_name)]
        except RuntimeError as e:
            sys.exit(f"[role] {e}")
    print(f"[role] using role id(s) {role_ids} for '{args.role_name}'   "
          f"district -> {args.district_id or 'none (optional)'}")

    ok = fail = skip = invalid = 0
    print(f"\n{'LINE':<5} {'USERNAME':<14} RESULT")
    for r in rows:
        tag = r["username"] or "(blank)"
        if r["_errors"]:
            invalid += 1
            print(f"{r['_line']:<5} {tag:<14} INVALID: {'; '.join(r['_errors'])}")
            continue
        try:
            if user_exists(client, r["username"]):
                skip += 1
                print(f"{r['_line']:<5} {tag:<14} SKIP (already exists)")
                continue
        except RuntimeError as e:
            fail += 1
            print(f"{r['_line']:<5} {tag:<14} FAIL (existence check: {e})")
            continue
        if args.dry_run:
            print(f"{r['_line']:<5} {tag:<14} would CREATE")
            continue
        try:
            success, err = create_user(client, r, role_ids, args.district_id, args.language)
            if success:
                ok += 1
                print(f"{r['_line']:<5} {tag:<14} CREATED")
            else:
                fail += 1
                print(f"{r['_line']:<5} {tag:<14} FAIL: {err}")
        except RuntimeError as e:
            fail += 1
            print(f"{r['_line']:<5} {tag:<14} FAIL: {e}")

    print("\n--- summary ---")
    if args.dry_run:
        would = sum(1 for r in rows if not r["_errors"] and r["username"])
        print(f"valid rows: {would - skip}   invalid: {invalid}   already-exists (skip): {skip}")
        print("dry-run: nothing was created.")
    else:
        print(f"created: {ok}   skipped(existing): {skip}   invalid: {invalid}   failed: {fail}")


if __name__ == "__main__":
    main()
