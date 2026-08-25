# Git Single-Branch Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve every current recoverable state outside the repository, fast-forward the verified feature onto `main`, and leave exactly one long-lived Git branch and one main worktree.

**Architecture:** Treat `prod-2026-08-25-baseline` and an independently verified external bundle as rollback anchors. Perform all destructive operations only after manifests, binary patches, staged patches, and untracked payloads are captured and checked. Move `main` only with fast-forward operations, verify it, then remove obsolete worktrees/branches locally and remotely.

**Tech Stack:** Git, PowerShell, SHA-256 manifests, Git bundles/worktrees.

**Spec:** `docs/superpowers/specs/2026-08-25-manual-product-routing-design.md`, section 10.

## Global Constraints

- Final maintained branch is exactly `main`; the production baseline tag remains.
- Do not merge or tag `lxc/history-data-plan` or `lxc/report-video-20260824`.
- Do not deploy, restart, mutate production, or interpret a Git push as deployment.
- Do not delete a dirty worktree until its tracked/staged patches and untracked payloads have a verified external recovery copy.
- Stop deletion for any worktree whose suspicious secret path cannot be safely handled.
- Resolve and validate every recursive/remove target under the intended repository or external backup root before operating.
- Never force-push `main`; all main movement must be fast-forward.

---

### Task 1: Create and verify a complete external recovery package

**Files:**
- Create outside Git: `E:/Project/Hengzhe-New-Product-Workflow-backups/20260825-single-branch-convergence/`
- Create outside Git: `repository-before-convergence.bundle`
- Create outside Git: `worktrees/<safe-name>/tracked.patch`
- Create outside Git: `worktrees/<safe-name>/staged.patch`
- Create outside Git: `worktrees/<safe-name>/untracked/`
- Create outside Git: `manifest.sha256`

**Interfaces:**
- Consumes: `git worktree list --porcelain`, every local ref/stash, each worktree HEAD/index/working tree.
- Produces: a checksumed package sufficient to recover committed refs, tracked changes, staged changes, and untracked payloads.

- [ ] **Step 1: Resolve roots and inventory exact targets**

Use explicit variables, resolve both roots, and require the backup root to be outside the repository:

```powershell
$repoRoot = (Resolve-Path -LiteralPath 'E:\Project\Hengzhe-New-Product-Workflow').Path
$backupRoot = 'E:\Project\Hengzhe-New-Product-Workflow-backups\20260825-single-branch-convergence'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$resolvedBackup = (Resolve-Path -LiteralPath $backupRoot).Path
if ($resolvedBackup.StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'backup root must be outside repository' }
git -C $repoRoot worktree list --porcelain
git -C $repoRoot status --short --branch
git -C $repoRoot branch --all --verbose --no-abbrev
```

- [ ] **Step 2: Scan untracked path names before copying**

For each worktree path, collect `git ls-files --others --exclude-standard`. If a path name matches `(^|[\\/])(\.env($|\.)|credentials?|secrets?|cookies?|tokens?|private[_-]?keys?)`, do not remove that worktree; record the exact path in `blocked-sensitive-paths.txt` without reading or copying its contents.

- [ ] **Step 3: Capture refs and each non-blocked worktree state**

```powershell
git -C $repoRoot bundle create "$resolvedBackup\repository-before-convergence.bundle" --all
git -C $repoRoot bundle verify "$resolvedBackup\repository-before-convergence.bundle"
```

For each worktree, create a filesystem-safe directory name, record its resolved path, branch, HEAD and porcelain status, then use native Git output files:

```powershell
git -C $worktreePath diff --binary HEAD --output="$worktreeBackup\tracked.patch"
git -C $worktreePath diff --cached --binary --output="$worktreeBackup\staged.patch"
```

Copy each non-sensitive untracked file with `Copy-Item -LiteralPath` after resolving its source under that worktree and its destination under `$worktreeBackup\untracked`. Preserve relative paths and do not use shell-built copy commands.

- [ ] **Step 4: Verify package readability and hashes**

Require `git bundle verify` success, parse every non-empty patch with `git apply --numstat`, and hash every backup file:

```powershell
Get-ChildItem -LiteralPath $resolvedBackup -File -Recurse |
  Sort-Object FullName |
  Get-FileHash -Algorithm SHA256 |
  ForEach-Object { "$($_.Hash.ToLowerInvariant())  $($_.Path.Substring($resolvedBackup.Length + 1).Replace('\','/'))" } |
  Set-Content -LiteralPath "$resolvedBackup\manifest.sha256" -Encoding utf8NoBOM
```

Read back the manifest, bundle ref count, worktree count, patch count, and copied untracked count. If any expected worktree is absent, stop.

- [ ] **Step 5: Record the verified backup result**

Append the backup root, bundle SHA-256, worktree count, untracked file count, and any blocked sensitive paths to the Asia/Shanghai work-log entry before deleting anything.

---

### Task 2: Fast-forward and verify `main`

**Files:**
- Modify Git ref: `refs/heads/main`
- Modify remote ref after local verification: `refs/heads/main`

**Interfaces:**
- Consumes: verified external package, `prod-2026-08-25-baseline`, and the clean feature tip.
- Produces: clean local/remote `main` at the verified feature tip.

- [ ] **Step 1: Capture the exact feature tip and verify ancestry**

```powershell
$featureTip = (git -C $featureWorktree rev-parse HEAD).Trim()
git -C $featureWorktree merge-base --is-ancestor prod-2026-08-25-baseline $featureTip
git -C $featureWorktree status --short --branch
```

Require exit 0 and a clean feature worktree.

- [ ] **Step 2: Preview and validate main-root cleanup targets**

```powershell
$mainRoot = (Resolve-Path -LiteralPath 'E:\Project\Hengzhe-New-Product-Workflow').Path
git -C $mainRoot status --short --branch
git -C $mainRoot clean -nd
```

Confirm every previewed path resolves under `$mainRoot`, exists in the external recovery package where required, and does not include the ignored `.worktrees` directory.

- [ ] **Step 3: Restore the main worktree to its recorded HEAD**

The user approved discarding the backed-up intermediate state. After Step 2 passes:

```powershell
git -C $mainRoot reset --hard HEAD
git -C $mainRoot clean -fd
git -C $mainRoot status --short --branch
```

Require a clean worktree before branch movement.

- [ ] **Step 4: Fast-forward main in two explicit steps**

```powershell
git -C $mainRoot merge --ff-only prod-2026-08-25-baseline
git -C $mainRoot merge --ff-only $featureTip
git -C $mainRoot rev-parse HEAD
```

Require main HEAD to equal `$featureTip`; do not rebase, merge with a commit, or force-update a ref.

- [ ] **Step 5: Re-run final local verification on main**

Run the focused backend/frontend tests, frontend build, Alembic heads, `git diff --check`, and status checks from the main worktree. Compare full-suite results with the feature verification evidence.

- [ ] **Step 6: Push only fast-forwarded main**

```powershell
git -C $mainRoot fetch origin --prune
git -C $mainRoot merge-base --is-ancestor origin/main main
git -C $mainRoot push origin main
git -C $mainRoot ls-remote --heads origin main
```

Require the remote hash to equal local main. No tag push is needed unless the existing production tag is absent remotely and the user separately requests it.

---

### Task 3: Remove obsolete worktrees and branches

**Files:**
- Delete Git-managed worktrees under the exact paths from Task 1.
- Delete local branch refs other than `main`.
- Delete remote branch refs other than `main`.

**Interfaces:**
- Consumes: verified main and recovery package.
- Produces: one main worktree, one local branch, and one remote branch.

- [ ] **Step 1: Re-inventory before deletion**

```powershell
git -C $mainRoot worktree list --porcelain
git -C $mainRoot for-each-ref --format='%(refname:short)' refs/heads/
git -C $mainRoot ls-remote --heads origin
```

Compare every non-main worktree/branch with the Task 1 manifest. Abort if a new worktree or new dirty state appeared after backup.

- [ ] **Step 2: Remove each non-main worktree by exact literal path**

For each path from the verified inventory, first resolve it under the repository's `.worktrees` directory or the exact externally managed worktree path, then run:

```powershell
git -C $mainRoot worktree remove --force $exactWorktreePath
```

Do not recursively delete computed paths with `Remove-Item`; let Git remove its own worktrees. Run `git worktree prune` after all exact removals.

- [ ] **Step 3: Delete all local branches except main**

Generate the exact local branch list, exclude only `main`, print it, then pass those exact names directly to `git branch -D`. This includes the production baseline branch, the feature branch, `lxc/history-data-plan`, and `lxc/report-video-20260824`; the production tag remains.

- [ ] **Step 4: Delete all remote branches except main**

Parse exact branch names from `git ls-remote --heads origin`, exclude `main`, print the deletion list, and call `git push origin --delete` with those exact names. Re-read remote heads after deletion.

- [ ] **Step 5: Verify the single-branch invariant**

```powershell
git -C $mainRoot branch --format='%(refname:short)'
git -C $mainRoot worktree list --porcelain
git -C $mainRoot ls-remote --heads origin
git -C $mainRoot show-ref --verify refs/tags/prod-2026-08-25-baseline
git -C $mainRoot status --short --branch
```

Expected: local and remote branch lists contain only `main`; the worktree list contains only the main root; the production tag resolves; status is clean.

---

### Task 4: Final recovery/readback record

**Files:**
- Modify outside repository: `E:/Project/work-logs/2026-35.md`

**Interfaces:**
- Consumes: final Git invariants, remote readback, external backup hashes, and verification results.
- Produces: a durable operational record without preserving discarded intermediate branch content in final Git history.

- [ ] **Step 1: Append the final work-log result**

Record Asia/Shanghai time, project, Git cleanup type, final main hash, remote hash, retained tag, deleted local/remote branch counts, removed worktree count, backup root/hash, verification results, known stale tests, and explicit `production deployment: not performed`.

- [ ] **Step 2: Run final readback**

Re-run the single-branch invariant commands from Task 3 and verify the external `manifest.sha256` still hashes the bundle and recovery artifacts correctly.

- [ ] **Step 3: Report recoverability and deletion truthfully**

State that obsolete worktrees/branches were deleted from Git and are recoverable only from the external bundle/patch package. State that no production deployment or production mutation occurred.

## Self-Review

- Spec coverage: external recovery, main fast-forward, feature integration, local/remote branch deletion, worktree cleanup, retained production tag, and no deployment are all explicit.
- Destructive safety: every delete follows exact-target inventory, external capture, hash/readability verification, and a second drift check.
- Windows safety: paths are resolved and checked in one PowerShell process; Git owns worktree deletion; no cross-shell path piping is used.
- Final-state consistency: all verification commands require one main branch/worktree and retain `prod-2026-08-25-baseline` as the immutable recovery tag.
