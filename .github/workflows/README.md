# CI/CD Workflows

Single workflow file: `pipeline.yml`
Triggers: `pull_request → main`, `push → main`, `workflow_dispatch`

---

## Job Matrix by Event

| Job | Pull Request | Push to main | workflow_dispatch |
|-----|:---:|:---:|:---:|
| `versioner` | `pr-{N}` | `1.0.{run_number}` | override or `1.0.{run_number}` |
| `lint` | yes | yes | yes |
| `unit-tests` | yes — coverage comment on PR | yes — coverage in job summary | yes |
| `build-windows` | yes — PR artifact, 7d | yes — release artifact, 30d | yes |
| `build-linux` | skipped | yes | yes |
| `integration-tests` | skipped | yes | yes |
| `release` | skipped | yes (integration must pass) | yes |

---

## Job Details

### versioner
Determines the build version string passed to all downstream jobs via output.

| Event | Output |
|-------|--------|
| `pull_request` | `pr-{pull_request.number}` |
| `push` | `1.0.{run_number}` |
| `workflow_dispatch` with `version` input | the supplied value |
| `workflow_dispatch` without input | `1.0.{run_number}` |

### lint — `Lint & Security`
Runs on every event. Four steps, each independently reported:

| Step | Tool | Config | Fails build? |
|------|------|--------|:---:|
| Format check | `black --check` | `[tool.black]` in `pyproject.toml` | yes |
| Code quality | `pylint clod.py` | `[tool.pylint]` in `pyproject.toml` (min score 7.0) | yes |
| Security scan | `bandit -ll` (MEDIUM+) | `[tool.bandit]` in `pyproject.toml` | yes |
| Dependency CVEs | `pip-audit` | n/a | no (`continue-on-error`) |

**Bandit skips** (intentional — clod is a shell executor by design):
- `B404` — `import subprocess`
- `B602` — Popen with `shell=True`
- `B605` — start process with a shell

`pip-audit` uses `continue-on-error: true` so CVEs in transitive dependencies
surface in logs without blocking releases.

### unit-tests
Runs on every event. Executes `tests/unit/` with line-level coverage.

**Coverage reporting differs by event:**

| Event | Where coverage goes |
|-------|-------------------|
| `pull_request` | PR comment posted by `MishaKav/pytest-coverage-comment` |
| `push` / `workflow_dispatch` | `$GITHUB_STEP_SUMMARY` (visible in the Actions run summary tab) |

Also uploads `coverage.xml` to Codecov (flags: `unit`).

Requires job-level `permissions: pull-requests: write` for PR comments.

### build-windows
Runs after `versioner` + `unit-tests`. Builds `clod.exe` via `clod.spec` (PyInstaller).

| Event | Artifact name | Retention |
|-------|--------------|-----------|
| `pull_request` | `clod-pr-{number}` | 7 days |
| `push` / `workflow_dispatch` | `clod-windows-{version}` | 30 days |

Artifact name set with a single ternary expression — no duplicate upload steps:
```yaml
name: ${{ github.event_name == 'pull_request'
  && format('clod-pr-{0}', github.event.pull_request.number)
  || format('clod-windows-{0}', needs.versioner.outputs.version) }}
```

### build-linux
Skipped on `pull_request`. Builds a Linux AppImage via PyInstaller + linuxdeploy.
Artifact: `clod-linux-{version}`, retained 30 days.

### integration-tests
Skipped on `pull_request`. Runs `tests/integration/` against mock HTTP servers.

On failure: downloads the Windows EXE artifact and re-uploads it as
`clod-integration-failure-{run_number}` (14-day retention) for debugging.

### release
Skipped on `pull_request`. Only runs when `integration-tests` result is `success`.
Gathers both binaries, signs them with GPG, then creates a GitHub Release tagged
`v{version}` with `clod.exe`, `clod.AppImage`, and their `.asc` detached signatures.

**Signing flow:**
1. Import `GPG_PRIVATE_KEY` secret into the runner's GPG keyring
2. `gpg --detach-sign --armor` each binary → produces `clod.exe.asc` / `clod.AppImage.asc`
3. All four files uploaded together in the release
4. If `GPG_PRIVATE_KEY` is not set, signing is skipped with a `::warning::` annotation
   (no build failure — allows releases before keys are configured)

**Required secrets:** `GPG_PRIVATE_KEY`, `GPG_PASSPHRASE`
Run `generate-gpg-key.yml` once via `workflow_dispatch` to generate the key pair.

**Public key:** commit the downloaded `clod-signing-key.asc` to the repo root so users
can verify downloads with `gpg --import clod-signing-key.asc && gpg --verify clod.exe.asc clod.exe`.

---

## Config Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | `black`, `pylint`, `bandit`, `pytest`, `coverage` settings |
| `requirements-dev.txt` | Dev dependencies: `pytest`, `pytest-cov`, `coverage[toml]`, `bandit[toml]`, `pip-audit`, `responses` |
| `.github/dependabot.yml` | Automated dependency update PRs (pip + github-actions, weekly on Mondays) |

## Dependabot

Dependabot opens weekly PRs on Mondays for:

| Ecosystem | Scope | Grouping |
|-----------|-------|---------|
| `pip` | `requirements.txt` + `requirements-dev.txt` | Dev tools (pytest, black, pylint, bandit, etc.) batched as minor/patch; production deps individual |
| `docker` | `docker-compose.yml` | All image bumps batched into one weekly PR |
| `github-actions` | `.github/workflows/` | All action version bumps (individual PRs) |

> **Docker + floating tags:** images using `:latest` or `:main` are pinned to SHA digests
> (`image: nginx:alpine@sha256:abc…`) and Dependabot updates the digest weekly when the
> upstream image changes. This makes builds reproducible and surfaces upstream changes as PRs.

PRs are labelled `dependencies` + ecosystem name for easy filtering.
The CI pipeline runs automatically on each Dependabot PR (lint, unit tests, build preview EXE).

---

## Permissions

| Permission | Scope | Used by |
|------------|-------|---------|
| `contents: write` | workflow level | `release` job (create GitHub Release) |
| `contents: read` | `unit-tests` job level | re-declared because any job-level `permissions` block resets all workflow-level permissions to none for that job |
| `pull-requests: write` | `unit-tests` job level | post coverage comment on PR |

> **GitHub Actions gotcha:** when you define a `permissions` block at the job level,
> it **replaces** the workflow-level permissions for that job — it does not inherit them.
> Always re-declare `contents: read` on any job that defines its own permissions and uses `checkout`.

---

## Adding a New Job

1. Decide if it should run on PRs or only on `push`/`dispatch`
2. Gate with `if: github.event_name != 'pull_request'` if main-only
3. Add `needs: [versioner, ...]` if you need the version string
4. Update the job matrix table above
