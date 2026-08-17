# openIMIS Malawi — Release Candidate `mw-2026.08.0-rc.1`

Immutable composition for deployment to the Malawi shared test server.
This candidate supersedes `26.07-uat.2` and is cut from
`release/mw/2026.08` in the Malawi distribution, hubs, and custom module
forks.

## Distribution and hubs

| Repository | Commit | Purpose |
|---|---|---|
| `openimis-dist_dkr` | tag target containing this lock; source baseline `7ca7227409c51bcf53478a4f01ccc18ba0aaaa2a` | Compose and deployment configuration |
| `openimis-be_py` | `19772498cc7d87dbb469e73c354c607e0e55c4ae` | Exact backend module pins |
| `openimis-fe_js` | `34aeb065d2956b16a485b04316de54d89a4b183a` | Exact frontend module pins |

## Backend Malawi modules

| Repository | Commit |
|---|---|
| `openimis-be-core_py` | `2759c3af0e29c38df6e60efd3271af1beb29a5ac` |
| `openimis-be-individual_py` | `503142b8502fa7a281629c6aa99d3ae1b9209bf0` |
| `openimis-be-location_py` | `e7e3d2ea02d2ee21105e0d22a07c49d4452843ab` |
| `openimis-be-social_protection_py` | `3c8c726ffc2e3c93b59db4e8392c87b876e609cf` |
| `openimis-be-project_social_protection_py` | `a56028f6934fec6fdaa4593a87d77ef876b5a0cf` |
| `openimis-be-calcrule_timesheet_py` | `aaa8b67d2c4aca50c5719fbcf51a996d480c9ef5` |
| `openimis-be-grievance_social_protection_py` | `ae25ee23f89dc7276070f4097d69c291d69a0912` |
| `openimis-be-deduplication_py` | `1198055c94e92126a29636af9cc51339e34f8b04` |
| `openimis-be-msr_etl_py` | `5feb29ed86628e20fefc4f848b0acda150ca9c8c` |
| `openimis-be-household_validation_py` | `e869b99aa1d7aeff987f70b5c10f023ab2785264` |

## Frontend Malawi modules

| Repository | Commit |
|---|---|
| `openimis-fe-core_js` | `cd75ab60cc0f8c88a1f780253aada82629ea6ef4` |
| `openimis-fe-individual_js` | `78a246fec392d575e531d5515b9a74c3e6fdae2d` |
| `openimis-fe-social_protection_js` | `088744e2e93fd9a1edb0f529fb7d3ab0406db4ed` |
| `openimis-fe-project_social_protection_js` | `c103e25969ef2c00482ebea3c7e45526c9f94cc1` |
| `openimis-fe-location_js` | `459ed52c7d8dfdf884514815c0796b89c7305cf3` |
| `openimis-fe-household_validation_js` | `a44cfaa3fa78f5bb64cb1ba603c32b0e36b83d6a` |
| `openimis-fe-grievance_social_protection_js` | `5cc420e472ce93f1cd559d842b1cacd6bf7f0e21` |
| `openimis-fe-deduplication_js` | `542b95d9222a3bb241bdc822c02911e2ec808c0d` |
| `openimis-fe-msr_etl_js` | `6b91d1abb1a335d1f55872a225aff1da92ccabbc` |
| `openimis-fe-coremis_language_pack_js` | `a0173193ae059f73c09674312ef3c7e8cee1dbd5` |

## Upstream and database baseline

- Non-customized backend and frontend modules remain on upstream openIMIS
  `release/26.04` as declared in the hub manifests.
- Deploy with `DB_TAG=26.04`.
- Database migrations and tracked module configuration are applied by the
  `migrations` service. Back up the test database before deployment.

## Build validation

Validated on 2026-08-17 from clean hub build contexts with no local module
overrides:

| Artifact | Candidate tag | Local validation image ID |
|---|---|---|
| Backend | `openimis-be-ml:mw-2026.08.0-rc.1` | `sha256:c2d3d13ddf04c06295279649119d81be4b5ad4a4156234be0647bb278b4120f1` |
| Frontend | `openimis-fe-ml:mw-2026.08.0-rc.1` | `sha256:ffff273b7e51da806227a16ccad70a8e52e7c00df9c05bed3b6230374981904a` |

The backend was validated with core source tree
`83f8190b2ec3884c22fef3ae610fd843f9f70046`. The merged core commit
`2759c3af0e29c38df6e60efd3271af1beb29a5ac` has that exact tree.

These image IDs are local validation evidence, not registry digests. If images
are built on or pushed for the shared test server, record their resulting IDs
or registry digests in the deployment record. Do not promote a later rebuild
to UAT as though it were the same artifact.

## Candidate gates

- The coordinated Git tag is `mw-2026.08.0-rc.1`.
- Deploy only from the coordinated tag and this frozen manifest.
- Record the database backup, migration result, smoke-test result, deployment
  time, and deployed image IDs/digests.
- Any code, manifest, or deployment configuration change requires
  `mw-2026.08.0-rc.2`; never move this tag.

