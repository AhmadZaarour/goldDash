# Continuous integration

The [CI workflow](../.github/workflows/ci.yml) runs on pull requests, pushes to
`test`, `main` or `master`, and manual dispatch. New commits cancel older runs for
the same branch or pull request. All jobs use read-only repository permissions;
no deployment credentials or shop data are needed.

## Checks

| Job | Verification |
| --- | --- |
| Backend (Python 3.12 and 3.13) | Locked Python dependencies, syntax/fatal-error checks, migrations, model consistency, and the full backend suite with at least 80% coverage |
| Frontend tests and build | Node.js 24, `npm ci`, unit tests, TypeScript checks, and the Vite production build |
| Browser tests (desktop and mobile) | Playwright Chromium checks using the existing desktop and mobile profiles |
| CI passed | Succeeds only when both Python versions, frontend checks, and browser checks succeed |

Each backend matrix job gets fresh PostgreSQL 17 and Redis 8 containers.
`goldshop_ci` and `goldshop_ci_test` are separate databases, and Redis databases 0
and 1 separate application and test state. The PostgreSQL service user can create
and drop databases because migration replay checks exercise disposable databases.
The committed service password and signing key are disposable CI values.

Migration commands explicitly target `TEST_DATABASE_URL`. Pytest also rejects
an equal application/test URL, clears only its test state, and includes empty
schema upgrade, downgrade and replay checks. Gold-API requests are mocked by the
backend tests; browser tests use a mocked application API. These checks complement
the separate staging acceptance tests once hosting is available.

## Results and debugging

Open the commit's **Checks** tab or the repository's **Actions → CI** run. Backend
jobs upload JUnit and coverage XML. Browser jobs upload an HTML report, JUnit XML,
custom screenshots and retained traces/screenshots for failures. Reports and the
frontend validation build are retained for seven days.

Download `browser-reports` to inspect a failed flow. Open a trace locally with
`npx playwright show-trace <trace.zip>` from `frontend/`, or use the HTML report.
Focused `.only` browser tests are rejected in CI so they cannot silently exclude
other tests.

The `frontend-build` artifact validates compilation without a deployment-specific
API address. The later hosting build must supply its staging API configuration or
same-origin routing.

## Activating the merge and deployment gate

1. Commit and push the workflow, then inspect its first GitHub Actions run.
2. On branches that receive pull requests (normally `main`), require **CI passed**
   in the GitHub ruleset/protection and require pull requests before merging.
   For direct pushes to `test`, the later deployment uses CI as its gate. The
   workflow provides the status; adding the file does not change repository rules
   automatically.
3. When staging hosting is ready, configure deployments to wait for CI on
   the exact commit being deployed. Disable any independent deployment trigger
   that could publish a commit before its checks finish. Release migrations run
   once against staging during deployment, separately from CI's test migrations.

There is no deployment job in this workflow. Connecting CD is the next hosting
step after the staging services, credentials and release procedure are prepared.
The official actions are pinned to verified release commits; update the pins
intentionally when upgrading CI dependencies.
