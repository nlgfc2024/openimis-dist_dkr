# UAT bulk user import (disposable)

One-off tool to create the ~40 UAT users in openIMIS from the Google Form responses.
It calls the same `createUser` GraphQL mutation the admin UI uses — **nothing is added
to the openIMIS image, database schema, or modules.** To remove it later: delete this
folder (and optionally deactivate the users in the admin UI). No migration, no fork.

## The CSV is never uploaded to any server

The tool runs **on your machine**, reads the CSV **locally**, and calls each server's
GraphQL API over HTTPS. There is no file transfer to the servers. "5 servers" just means
the tool targets 5 URLs — see **Multiple servers** below.

## Google Form → sheet columns

Create the form with these questions, then in the responses Google Sheet **rename the
columns** (or use `--col-*` to map) to exactly:

| Column       | Required | Notes |
|--------------|----------|-------|
| `first_name` | yes      | maps to openIMIS *otherNames* (≤50) |
| `last_name`  | yes      | ≤50 |
| `username`   | yes      | **≤12 chars**, letters/digits/`_.-` only, unique (openIMIS hard limit) |
| `email`      | yes      | valid + unique (backend rejects duplicates / missing email) |
| `password`   | yes      | user-chosen, policy below. **Treat the sheet/CSV as a secret** |
| `team`       | multi    | required only in multi-server mode; must match a `team` in `servers.csv` |
| `phone`      | no       | optional |

Everyone gets the **same role** — resolved by **name** (`IMIS Administrator` by default,
`--role-name`), so the form needs no role question. Not asked either: a **district** is
**auto-assigned** (see below), so the form only needs the columns above.

### District — auto-assigned (why it matters)

The `/front/admin/users` grid filters listed users by **region membership** (`regionIds`).
A user with **no district belongs to no region and is invisible in that grid** — even though
a national admin is allowed to see them. So by default the tool **auto-assigns a district**
to each created user (the first type-D/TA on the server, or `--district-name "<TA>"`), giving
them a "home region" so they appear.

This is **safe for IMIS Administrator**: the national role keeps full access — verified live,
a district-assigned IMIS-Admin user still sees all users and all regions; the district only
adds visibility, it does not restrict.

- `--district-id N` / `servers.csv` `district_ids` — explicit override (wins over auto-assign).
- `--district-name "<TA>"` — auto-assign a specific TA by name instead of the first one.
- `--list-districts` — print the type-D/TA ids/names on a server.
- `--no-district` — opt out entirely (users stay district-less and won't show in the grid).

### Password requirements (openIMIS default policy)

The backend validates every password on create (`validate_password`), so the pre-flight
mirrors it. A password must be:

- **≥ 8 characters**, with **≥ 1 uppercase**, **≥ 1 lowercase**, and **≥ 1 digit**
- not too similar to the person's username / name / email (server-side check)

Tell form-fillers this up front, or many rows will be rejected. Show these rules in the
form's password question. (These thresholds are server-config — `PASSWORD_MIN_LENGTH` etc.;
adjust the pre-flight with `--password-min-length` if a server differs.)

> **Security note:** collecting passwords in a Google Form means plaintext passwords sit
> in the responses sheet and any CSV export. Restrict sheet sharing, delete the export
> after import, and consider forcing a password change on first login. (An alternative is
> to not collect passwords and have the script generate them — ask if you want to switch.)

## Steps (single server)

1. Export the responses sheet: **File → Download → CSV**, save as `users.csv` here.
2. **Dry-run** — validates every row (username, email, password policy, duplicates), shows
   which users are new vs already-exist, resolves the role by name, creates nothing:
   ```bash
   export OIMIS_ADMIN_USER=Admin
   export OIMIS_ADMIN_PASSWORD='...'        # not echoed
   python3 import_users.py --url http://localhost:8080 --csv users.csv --dry-run
   ```
3. Fix any `INVALID` rows in the sheet, re-export, then run for real (drop `--dry-run`).
   Re-running is safe — existing usernames are skipped (idempotent).

The role defaults to **`IMIS Administrator`**, looked up by name on the server (so a
different role id per deployment doesn't matter). Override with `--role-name "Some Role"`,
or force a specific id with `--role-id N`. `--list-roles` prints what's available. A district
is **auto-assigned** by default (so users appear in the admin grid — see above); override with
`--district-id N` / `--district-name "<TA>"`, or opt out with `--no-district`.

`--url` is the deployment base (`http://localhost:8080`, or `https://uat.hyena.malawiubr.org`);
add `--insecure` only for self-signed certs. Admin credentials come from
`OIMIS_ADMIN_USER` / `OIMIS_ADMIN_PASSWORD` (or you'll be prompted) — never pass them where
they'd land in shell history.

## Multiple servers (users grouped by team)

One `users.csv` (with a `team` column) + one `servers.csv` mapping each team to its server,
and a **single command** fans out — each team's users go only to that team's server.

`servers.csv` (no passwords in it):

```
team,url,role_ids,district_ids,insecure
alpha,https://alpha.uat.example.org,,,false
beta,https://beta.uat.example.org,,,false
...
```
Only `team,url` are required. Leave **`role_ids` blank** to resolve `--role-name`
(`IMIS Administrator`) on each server — this is the point of name-based lookup, since role
ids differ per deployment. Leave **`district_ids` blank** to **auto-assign** a district per
server (or set `--no-district` to skip). Both accept several `;`-separated ids as an override.
`insecure=true` skips TLS verification for that server.

Run:
```bash
export OIMIS_ADMIN_USER=Admin
export OIMIS_ADMIN_PASSWORD='...'          # shared admin across servers
python3 import_users.py --servers servers.csv --csv users.csv --dry-run   # then drop --dry-run
```

- Rows whose `team` matches no server are reported as **unrouted** (never sent anywhere).
- If a server's login fails, only that server is skipped; the others still run.
- **Per-server credentials:** if the servers have different admin logins, set
  `OIMIS_ADMIN_USER_<TEAM>` / `OIMIS_ADMIN_PASSWORD_<TEAM>` (team upper-cased, e.g.
  `OIMIS_ADMIN_PASSWORD_ALPHA`); they override the shared vars.
- The role is resolved by **name** on each server, so you don't need to look up per-server
  ids. Override per server via `servers.csv` `role_ids` only if a team needs a different role.

**Speed:** ~40 users total is seconds; the Sheets API wouldn't make it faster (same per-user
API calls), so CSV + no dependencies is the right call.

## Finding a district id (GraphQL)

The `districts` field expects an openIMIS **type-D** location id. In Malawi's hierarchy
that is the **TA** level (District=R, TA=D). Grab it from the admin Location tree, or query:

```graphql
query { locations(type: "D", first: 200) { edges { node { id name code } } } }
```

## What this is NOT

Not a permanent feature. If bulk user provisioning becomes a real requirement, it should be
a proper backend command/module on the `core` fork — not this script. This exists only to
unblock UAT.
