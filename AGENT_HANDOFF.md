# Agent Handoff

## Active Work

### Codex

- Mode: paused / implementation only after user approval
- Task: Keep the workspace stable, maintain Git checkpoints, and implement only after Claude/user planning is accepted.
- Files: no active coding target
- Started: 2026-06-29
- Status: A technical prototype exists in `backend/`, `frontend/`, `deploy/`, and `docker-compose.yml`; treat it as an early experiment, not final product direction.

### Claude

- Mode: read-only planning/review
- Task: Re-plan the Southeast Asia new-product workflow from the operations department perspective.
- Files: original business files in the project root, current `docs/*.md`, and optional reference outputs under `outputs/`.
- Status: pending Claude review

## Current Collaboration Rule

- Claude should not write code, deploy, connect to the server, or read secrets.
- Codex should not continue implementation until the business chain, phase boundaries, and document corrections are agreed.
- If Claude later needs to edit files, use a separate Git worktree or explicitly pause Codex writes first.
