# Agent Handoff

> Updated: 2026-06-29 — single at-a-glance state for whoever picks up next.

## Current State (read this first)

- **Phase**: business planning done for MVP v1 → Codex build kickoff.
- **Framework (confirmed by user)**: “两段主流程 + 一座外部桥” — two platform-owned segments + one external bridge.
  - **Front segment (= MVP v1)**: 入池 → 分配/自领 → 销售认领 → 主管审核 → **出可备货清单**.
  - **External bridge (NOT platform todos)**: 备货 / 采购 / 供应链 / 下单 — platform only exports the list + logs status + waits for 到货通知 回流.
  - **Back segment (later phases)**: 到货承接 → 刊登 → 二次调研 → 推品(周度复盘≥4周) → 四周总结.
- **Roles**: 销售 = 运营; 主管 = 运营负责人.
- **MVP v1 decision**: drive the whole front segment with **ONE source table** — 选品1 (开发部门认领-反馈).
  Spec = `docs/09-MVP第一版-选品1单表跑通规格.md`.
- **Docs corrected (2026-06-29)**: `README` + `docs/00/01/02/03/04/08` reframed to 两段+一桥 (备货 = external bridge, not a platform phase; 到货刊登 moved up to back-segment Phase 2). docs/01 §13 logs change v0.4.
- **Meeting aid**: `outputs/field_confirmation_20260629/新品流程字段责任确认操作台.html` (offline field-responsibility console).

## Active Work

### Codex
- **Mode: UNPAUSED — implement MVP v1 per spec `docs/09`.**
- **Task — build `docs/09-MVP第一版-选品1单表跑通规格.md` end to end:**
  1. **Importer** for 选品1 (one sheet, default `开发0623期`; two-row header; data from row 3):
     map `A:L`→`NewProductOpportunity`, `Z:AN`→`MarketResearchItem`, `AO:AV`→pricing snapshot, `CC:CH`→claim/assignment;
     **skip `M:Y`, `AW:CA` (incl `BO:BX`), `CB`**; dedupe by `source_file+sheet+row`; idempotent; skip empty/subtotal rows.
  2. **Front flow** 入池→(分配/自领)→认领→审核; AND change the auto “审核通过按 `单销×30` 建 `stocking_request`”
     (`backend/app/services.py:182` `create_stocking_draft_from_claim`) → mark opportunity “可备货” and feed the export instead.
  3. **Export** 可备货清单 Excel: 备货量 = 认领单销 × 30; 成本/体积/货值 columns left **empty** (cost cols were dropped); include 开品邮件 status columns.
- **Acceptance**: see `docs/09` §6. Claude reviews against it before sign-off.
- **Red lines**: no other source tables; no DingTalk; no write-back to online sheets; no deploy; no new external deps; do not touch `M:Y / AW:CA / CB`.
- **Files**: `backend/` (importer + flow + export). Frontend/deploy not required to demonstrate the v1 run.

### Claude
- **Mode: planner / reviewer.**
  - May directly create/modify **planning docs** (`docs/`, `outputs/`) and meeting-aid artifacts (HTML, field mappings), including correcting prior plans; logs rule changes in each doc’s 变更记录.
  - For **platform code**: writes the spec for Codex and reviews the output — does **not** write platform code, deploy, or read secrets.
- **Done**: framework + MVP scope, doc corrections (7 docs), field-confirmation HTML, `docs/09` spec.
- **Next**: review Codex’s `docs/09` implementation against §6; produce field-responsibility mappings for the remaining source tables once business confirms.

## Collaboration Rule

- Claude owns `docs/` + `outputs/` (planning); Codex owns `backend/`/`frontend/`/`deploy/` (platform code) and implements only against an agreed spec (currently `docs/09`).
- **Secrets**: never commit `.env`, server/DingTalk/ERP credentials, cookies, tokens, keys. The 选品1 source filename contains an OSS signature — `*.xlsx` is gitignored; **do not commit any source xlsx**.
- **Traceability**: every imported record keeps source file / sheet / row + snapshot.
- Prefer explicit workflow states + audit logs over spreadsheet color/status conventions.

## Open Questions (do NOT block MVP v1)

- 认领必填字段细则、认领单销周期(日销?)、各张表“哪列谁填” — confirm per-table later (use the field-confirmation console).
- 写回钉钉在线表 yes/no.
- Remaining source tables (财根 / 直发热销 / 销售调研 / 销售反推) — after 选品1 runs.
- 后段(到货后)字段: 到货触发点、ItemID/链接回填来源、二次调研/复盘字段 — when reaching back-segment phases.
