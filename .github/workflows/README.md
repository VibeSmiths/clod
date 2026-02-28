# CI/CD Workflows

Single workflow file: `pipeline.yml`
Triggers: `pull_request → main`, `push → main`, `workflow_dispatch`

---

## Job Matrix by Event

| Job | Pull Request | Push to main | workflow_dispatch |
|-----|:---:|:---:|:---:|
| `versioner` | `pr-{N}` | `1.0.{run_number}` | override or `1.0.{run_number}` |
| `lint` | yes | yes | yes |
| `unit-tests` | yes | yes | yes |
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

### lint
Runs on every event. Checks:
- `black --check` (line length 100) on `clod.py` and `tests/`
- `pylint` on `clod.py` with minimum score 7.0

### unit-tests
Runs on every event. Executes `tests/unit/` with coverage report uploaded to Codecov.

### build-windows
Runs after `versioner` + `unit-tests`. Builds `clod.exe` via `clod.spec` (PyInstaller).

| Event | Artifact name | Retention |
|-------|--------------|-----------|
| `pull_request` | `clod-pr-{number}` | 7 days |
| `push` / `workflow_dispatch` | `clod-windows-{version}` | 30 days |

Artifact name is set with a single expression — no duplicate upload steps:
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
Creates a GitHub Release tagged `v{version}` with both `clod.exe` and `clod.AppImage`.

---

## Secrets / Permissions

| Secret | Used by | Purpose |
|--------|---------|---------|
| `GITHUB_TOKEN` (auto) | `release` | Create GitHub Release and upload assets |

`permissions: contents: write` is set at the workflow level for the release job.

---

## Adding a New Job

1. Decide if it should run on PRs or only on `push`/`dispatch`
2. Gate with `if: github.event_name != 'pull_request'` if main-only
3. Add `needs: [versioner, ...]` if you need the version string
4. Update the job matrix table above
