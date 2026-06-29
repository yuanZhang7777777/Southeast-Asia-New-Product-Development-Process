# Project Agent Rules

This project follows the global Karpathy-inspired and Ponytail-style engineering rules from `C:\Users\86173\.codex\AGENTS.md`.

Project-specific rules:

- Keep the MVP narrow: `入池 -> 分配 -> 认领 -> 审核 -> 备货草稿 -> 到货提醒 -> 四周总结`.
- Do not treat Ponytail, Hermes, or other agent tooling as business runtime dependencies.
- Do not commit secrets, server passwords, DingTalk credentials, ERP credentials, cookies, or `.env` files.
- Preserve source-table traceability: every imported record should keep source file, sheet, row, and snapshot metadata.
- Prefer explicit workflow states and audit logs over hidden spreadsheet color/status conventions.
- Business docs should remain complete and readable; Ponytail minimalism applies to code implementation, not to requirements traceability.
- Ponytail source reference for this project is `git@github.com:DietrichGebert/ponytail.git`; use it as a development/review discipline only. Do not add it to `requirements.txt`, `package.json`, or Docker runtime services.
