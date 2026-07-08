# Project Agent Rules

This project follows the global Karpathy-inspired and Ponytail-style engineering rules from `C:\Users\86173\.codex\AGENTS.md`.

## Claude Code 八荣八耻

Treat these as project-level agent ground rules:

- 以瞎猜接口为耻，以认真查询为荣：不猜接口，先查文档。
- 以模糊执行为耻，以寻求确认为荣：不糊里糊涂干活，先把边界问清。
- 以臆想业务为耻，以人类确认为荣：不臆想业务，先跟人类对齐需求并留痕。
- 以创造接口为耻，以复用现有为荣：不造新接口，先复用已有。
- 以跳过验证为耻，以主动测试为荣：不跳过验证，先写用例再跑。
- 以破坏架构为耻，以遵循规范为荣：不动架构红线，先守规范。
- 以假装理解为耻，以诚实无知为荣：不装懂，坦白不会。
- 以盲目修改为耻，以谨慎重构为荣：不盲改，谨慎重构。

Project-specific rules:

- Keep the MVP narrow: `入池 -> 分配 -> 认领 -> 审核 -> 备货草稿 -> 到货提醒 -> 四周总结`.
- Do not treat Ponytail, OpenClaw-style platforms, or other external agent tooling as business runtime dependencies.
- Do not commit secrets, server passwords, DingTalk credentials, ERP credentials, cookies, or `.env` files.
- Preserve source-table traceability: every imported record should keep source file, sheet, row, and snapshot metadata.
- Prefer explicit workflow states and audit logs over hidden spreadsheet color/status conventions.
- Business docs should remain complete and readable; Ponytail minimalism applies to code implementation, not to requirements traceability.
- Ponytail source reference for this project is `git@github.com:DietrichGebert/ponytail.git`; use it as a development/review discipline only. Do not add it to `requirements.txt`, `package.json`, or Docker runtime services.
