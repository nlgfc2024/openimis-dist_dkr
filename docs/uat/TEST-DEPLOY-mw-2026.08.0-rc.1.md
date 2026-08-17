# Shared test deployment — `mw-2026.08.0-rc.1`

Use this candidate for shared test only. Its exact repository composition is
recorded in [`RELEASE-mw-2026.08.0-rc.1.lock.md`](./RELEASE-mw-2026.08.0-rc.1.lock.md).

## 1. Back up and record the current deployment

Before changing the test server:

1. Record the currently deployed distribution, backend, and frontend tags.
2. Record the running backend and frontend image IDs.
3. Back up the database and verify that the backup file is non-empty.
4. Keep the existing environment files; do not commit credentials.

## 2. Check out the coordinated candidate

```bash
git clone --branch mw-2026.08.0-rc.1 --depth 1 \
  https://github.com/nlgfc2024/openimis-dist_dkr.git openimis-test
cd openimis-test

git clone --branch mw-2026.08.0-rc.1 --depth 1 \
  https://github.com/nlgfc2024/openimis-be_py.git
git clone --branch mw-2026.08.0-rc.1 --depth 1 \
  https://github.com/nlgfc2024/openimis-fe_js.git
```

The two hub directories must be named `openimis-be_py` and `openimis-fe_js`
because those are the Compose build contexts.

## 3. Configure the test environment

Use the server's secured `.env` and `.env.openSearch` files. Confirm at least:

```ini
BE_TAG=mw-2026.08.0-rc.1
FE_TAG=mw-2026.08.0-rc.1
DB_TAG=26.04
MODE=Prod
```

Also verify the test hostname, trusted CSRF origin, database credentials,
secret key, Redis settings, and OpenSearch credentials. Do not copy local
development overrides to the server.

## 4. Build the candidate

```bash
docker compose build --no-cache backend frontend
docker image inspect openimis-be-ml:mw-2026.08.0-rc.1 --format '{{.Id}}'
docker image inspect openimis-fe-ml:mw-2026.08.0-rc.1 --format '{{.Id}}'
```

Save the two image IDs in the deployment record. If a team registry is used,
push these exact tested images and record their immutable registry digests.

## 5. Deploy and verify

```bash
docker compose up -d
docker compose ps
docker compose logs migrations
docker compose logs backend
docker compose logs worker
docker compose logs scheduler
```

The `migrations` service must exit successfully before testing. Then verify:

- backend GraphQL responds through the configured hostname;
- the frontend loads and login succeeds;
- workers report ready and the scheduler remains healthy;
- Malawi project/location selection works;
- grievance configuration resolves;
- enrollment and other release-scope workflows pass the agreed smoke tests.

Record failures against this candidate. Fixes must go through the release
branch and produce `mw-2026.08.0-rc.2`; do not patch the server checkout or
move the RC tag.

## 6. Promotion and rollback

Promote the same recorded images to UAT only after shared-test acceptance.
For rollback, restore the previous application images and use the pre-deploy
database backup when migrations or data changes are not backward-compatible.

