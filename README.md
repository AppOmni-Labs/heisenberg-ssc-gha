
# Heisenberg Dependency Health Check (GitHub Action)

A lightweight PR guardrail for dependency updates.  
It scans new or changed dependencies only (from your lock/manifest), pulls health and risk signals (deps.dev + heuristics), flags fresh publishes, comments a report on the PR, optionally labels it for security review, and can fail the job on policy hits.

**Ecosystems supported:** PyPI (`poetry.lock`, `requirements.txt`, `uv.lock`), npm/yarn (`package-lock.json`, `yarn.lock`), Go (`go.mod`).

## What it does
-   Detects only the deps you added or changed in the PR (no full graph scan).
-   Looks up:
    -   deps.dev health score and advisory count
    -   Popularity signals (stars/forks), maintenance, dependents
    -   Fresh publish check (published < 24h)
    - And for npm - potential post-install scripts
-   Posts a **Dependency Health Report** as a PR comment with quick links (deps.dev / Snyk Advisor / Socket)
-   If risky, adds the **`security review`** label and **runs in WARNING MODE** (CI stays green to keep lower level of annoyance).
    
> **Non-blocking by default:** It is not a hard block just a speedbump so you can be alerted if something suspicious detected. Your CI pipeline won't fail, but dependency risks will be surfaced in the comment. You can comment `accept-risk` on the PR to suppress future notifications for the flagged packages until you do another commit to the manifest.

## Quick start

Minimal workflow for a repo that uses Poetry / npm / Yarn / Go:

```yaml
name: Heisenberg Health Check
on:
  pull_request:
    paths:
      - "**/poetry.lock"
      - "**/uv.lock"
      - "**/package-lock.json"
      - "**/yarn.lock"
      - "**/requirements.txt"
      - "**/go.mod"

permissions:
  contents: read
  pull-requests: write   # PR comment
  issues: write          # create label (only needed if add_security_label is true)

jobs:
  deps-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Detect changed manifest
        id: detect
        run: |
          git fetch origin ${{ github.base_ref }} --depth=1
          LOCK_PATH=$(git diff --name-only origin/${{ github.base_ref }} | \
            grep -E 'poetry.lock$|uv.lock$|package-lock.json$|yarn.lock$|requirements.txt$|go.mod$' | head -n1 || true)
          echo "lock_path=$LOCK_PATH" >> $GITHUB_OUTPUT

      - name: Heisenberg Dependency Health Check
        uses: AppOmni-Labs/heisenberg-ssc-gha@v1
        with:
          package_file: ${{ steps.detect.outputs.lock_path }}
```

### Disable the security review label

If you don't want the action to add the `Security Review` label to PRs with flagged dependencies, set `add_security_label` to `"false"`:

```yaml
      - name: Heisenberg Dependency Health Check
        uses: AppOmni-Labs/heisenberg-ssc-gha@v1
        with:
          package_file: ${{ steps.detect.outputs.lock_path }}
          add_security_label: "false"
```
