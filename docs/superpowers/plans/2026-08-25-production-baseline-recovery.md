# Production Baseline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve every local Git state and create one local branch/tag whose deployable source exactly matches the verified production runtime on 2026-08-25.

**Architecture:** Work only in the isolated `lxc/production-baseline-20260825` worktree based on `917d382`. Back up Git refs and dirty-worktree patches outside the repository, then overlay a strict allow-list of production source files read-only via SSH. Verify hashes against host and running containers, run the local test/build gates, and commit/tag locally without pushing or deploying.

**Tech Stack:** Git worktrees/bundles, PowerShell, OpenSSH/SCP, Python/pytest, Node.js/npm/Vite, Docker runtime metadata.

**Spec:** `E:\Project\work-logs\2026-35.md`, section `2026-08-25 Asia/Shanghai - 新品流程 Git 与生产源码只读一致性审计`.

## Global Constraints

- Production is read-only: no remote file, container, database, configuration, scheduler, or DingTalk mutation.
- Never copy `.env`, credentials, databases, uploads, source workbooks, backups, outputs, logs, caches, or business data into Git.
- Do not delete, prune, reset, switch, or overwrite any existing branch, worktree, stash, or user change.
- Do not push, merge, deploy, restart, or alter traffic.
- The production source allow-list is `backend/app/**/*.py`, `backend/alembic/**/*.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/.gitkeep`, `backend/alembic.ini`, backend requirement/Docker files, `frontend/src/**`, frontend package/build/nginx files, `docker-compose.yml`, and non-secret deploy configuration already tracked by Git.
- A production file is authoritative only after its host hash matches the running container where applicable.

---

### Task 1: Create recoverable local safety snapshots

**Files:**
- Create outside Git: `E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline\repository.bundle`
- Create outside Git: `E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline\worktrees\*.patch`
- Create outside Git: `E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline\worktrees\*-untracked.txt`

**Interfaces:**
- Consumes: all current refs, stashes, tracked worktree diffs, and untracked path names.
- Produces: a bundle verified by `git bundle verify` plus one patch/inventory pair per dirty worktree.

- [x] **Step 1: Resolve and validate the backup target**

```powershell
$backupRoot = 'E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline'
New-Item -ItemType Directory -Force -Path $backupRoot, "$backupRoot\worktrees" | Out-Null
(Resolve-Path $backupRoot).Path
```

- [x] **Step 2: Capture all committed refs and stashes**

```powershell
git bundle create "$backupRoot\repository.bundle" --all
git bundle verify "$backupRoot\repository.bundle"
```

- [x] **Step 3: Capture every existing worktree's tracked patch and untracked inventory**

For each path from `git worktree list --porcelain`, run `git -C <path> diff --binary HEAD` into a uniquely named `.patch` and `git -C <path> ls-files --others --exclude-standard` into `-untracked.txt`. Do not copy the untracked payloads.

- [x] **Step 4: Verify the safety snapshot**

```powershell
Get-FileHash "$backupRoot\repository.bundle" -Algorithm SHA256
Get-ChildItem "$backupRoot\worktrees" | Select-Object Name,Length
```

### Task 2: Capture the sanitized production source

**Files:**
- Create outside Git: `E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-production-baseline\production-source\`
- Modify in isolated worktree: `backend/app/**`, `backend/alembic/**`, `backend/alembic.ini`, `frontend/src/**`, and the explicit build/config files in Global Constraints.

**Interfaces:**
- Consumes: read-only production path `hz-new-product-preprod:/opt/hengzhe-new-product/app`.
- Produces: an exact local copy of the allow-listed deployable source and no runtime data.

- [x] **Step 1: Audit the remote allow-list before copying**

```powershell
ssh hz-new-product-preprod "cd /opt/hengzhe-new-product/app && find backend/app backend/alembic frontend/src -type f | sort"
ssh hz-new-product-preprod "cd /opt/hengzhe-new-product/app && find backend/app backend/alembic frontend/src -type f ! -name '*.py' ! -name '*.ts' ! -name '*.tsx' ! -name '*.css' ! -name '*.d.ts' ! -name '*.pyc' | sort"
```

- [x] **Step 2: Copy only the audited source trees and explicit build files to local staging**

Use `scp -r` for the three audited source trees and individual `scp` calls for the explicit files. Do not recursively copy the production application root.

- [x] **Step 3: Reject prohibited staged paths**

Search staged paths case-insensitively for `.env`, password/token/cookie/key names, database dumps, workbooks, uploads, backups, outputs, logs, caches, and `__pycache__`; stop before overlay if any prohibited payload is present.

- [x] **Step 4: Overlay the audited staging files into this isolated worktree**

Copy the allow-listed files with their relative paths, leaving local tests and documentation untouched.

### Task 3: Record and compare immutable manifests

**Files:**
- Create: `docs/production-baseline-20260825.md`
- Create: `docs/production-baseline-20260825.sha256`

**Interfaces:**
- Consumes: production host/container SHA-256 manifests and the isolated worktree.
- Produces: durable provenance and a machine-checkable runtime-source manifest.

- [x] **Step 1: Generate the sorted production manifest**

Generate SHA-256 entries for the exact allow-list relative to `/opt/hengzhe-new-product/app`; do not include absolute host paths.

- [x] **Step 2: Generate the local manifest with the same relative paths**

Use `Get-FileHash -Algorithm SHA256`, lowercase hashes, forward-slash paths, and ordinal path sorting.

- [x] **Step 3: Require exact manifest equality**

Compare remote and local maps and require zero differing, remote-only, or local-only allow-listed files.

- [x] **Step 4: Record provenance and exclusions**

Document the production alias, audit date, stale `RELEASE_COMMIT=c2fe6f8`, running frontend asset, source/container hash result, base commit `917d382`, exclusions, and the fact that no production write occurred.

### Task 4: Run the smallest sufficient verification gates

**Files:**
- No tracked file required unless a production/local mismatch needs a focused test correction.

**Interfaces:**
- Consumes: reconstructed production baseline.
- Produces: backend test result, frontend test/build result, Alembic head, and production hash proof.

- [x] **Step 1: Install isolated dependencies using existing lock files**

```powershell
python -m pip install -r backend\requirements.txt -r backend\requirements-dev.txt
npm ci --prefix frontend
```

- [x] **Step 2: Run backend verification** — 683 passed, 18 failed; retained as evidence of stale tests.

```powershell
Push-Location backend
python -m pytest -q
python -m alembic heads
Pop-Location
```

- [x] **Step 3: Run frontend verification** — build passed; 245 tests passed and 6 stale assertions failed.

```powershell
npm test --prefix frontend -- --run
npm run build --prefix frontend
```

- [x] **Step 4: Compare the built frontend entry assets with production evidence** — CSS exact; JS difference traced to excluded build-time Corp ID.

Record whether the local Vite asset names/hashes equal the running production `/assets/index-BJBf5msH.js` and CSS asset. A mismatch blocks any claim of reproducible frontend runtime but does not change production.

### Task 5: Commit and tag the local baseline

**Files:**
- Modify: `docs/production-baseline-20260825.md` with final verification results.
- Modify: `E:\Project\work-logs\2026-35.md` with the completed local baseline result.

**Interfaces:**
- Consumes: verified source, manifest, plan, and verification evidence.
- Produces: one local commit on `lxc/production-baseline-20260825` and local annotated tag `prod-2026-08-25-baseline`.

- [x] **Step 1: Run pre-commit safety checks**

```powershell
git status --short
git diff --check
git diff --name-only | Select-String -Pattern '(^|/)(\.env|backups?|outputs?|logs?|uploads?|\.private_uploads)(/|$)'
```

- [x] **Step 2: Review the full scoped diff and stage only the baseline files**

Stage the audited source/build files, plan, provenance document, and manifest. Do not use `git add -A`.

- [x] **Step 3: Commit locally**

```powershell
git commit -m "chore: capture verified production baseline"
```

- [x] **Step 4: Tag locally and verify**

```powershell
git tag -a prod-2026-08-25-baseline -m "Verified production source baseline 2026-08-25"
git show --stat --oneline HEAD
git show-ref --verify refs/tags/prod-2026-08-25-baseline
git status --short --branch
```

- [x] **Step 5: Confirm external state remains unchanged**

Read back production health, container IDs, `RELEASE_COMMIT`, and the runtime manifests. Confirm no push occurred by comparing `git ls-remote --heads origin` with the pre-task remote-head inventory.

## Self-Review

- Spec coverage: preserves Git refs/stashes/dirty patches, captures real production source, excludes secrets/data, verifies runtime equality, and creates only a local branch/tag.
- Placeholder scan: no deferred implementation placeholders are present; operational stop conditions are explicit.
- Type consistency: remote/local manifests share `SHA-256 + repository-relative path`; the same allow-list drives capture, comparison, staging, and documentation.
