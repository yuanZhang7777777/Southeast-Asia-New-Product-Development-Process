# Agent Handoff

> Updated: 2026-07-17 17:35 Asia/Shanghai

## Start Here

The canonical development branch is `lxc/integrated-workflow`. It merges the complete production front-stage line `lxc/pricing-review-edit@fbf574c` and the listing/observation line `lxc/listing-observation-workbench@a4a61e4` in merge commit `1aae41e`.

Read these files before changing behavior:

1. `docs/2026-07-09-已确认需求记录.md` — highest-priority confirmed business rules.
2. `docs/02-功能实现状态.md` — implementation, verification and open work.
3. `docs/20-项目推进总控.md` — current delivery order.
4. `docs/06-部署与服务器准备.md` — production/development separation and rollback.
5. `docs/21-后半段需求领导对齐问题清单.md` — later-stage confirmed rules and remaining external inputs.

Do not infer current behavior from old plans or prototypes when they conflict with the confirmed record.

## Environment Boundary

| Environment | Address | Current code | Rule |
|---|---|---|---|
| Production | `http://101.132.26.138:8080` | `b373d65` | In use. Do not connect, deploy or restart without a separately approved non-working-time release window. |
| Development | `http://139.224.2.166:18081` | `b564815` | Unified branch validation and business UAT only. SSH alias: `hz-new-product-dev`. |

Production database is `workflow_prod_20260715`; development database is `workflow_dev_20260715`. Databases, Redis, uploads, volumes, ports and environment variables are isolated. Never commit passwords, tokens, cookies, private keys or `.env` files.

PLM arrival endpoint settings and credentials are stored separately in both server `.env` files. `PLM_SYNC_ENABLED` remains `false` in both environments; do not enable it or restart production without explicit approval.

`caigen-arrival-notifier` is a separate service co-hosted with the workflow production environment on `101.132.26.138`. It is the only sender of arrival cards; neither workflow environment sends arrival cards. The workflow still owns its elimination-summary reminder. Development must not receive a persistent feed from the production notifier. Its current arrival/summary card template is selected through `DINGTALK_ARRIVAL_CARD_TEMPLATE_ID`; never commit the environment value.

## Verified Baseline

- Branch: `lxc/integrated-workflow`.
- Merge commit: `1aae41ef6b5b86ba086b43f1e61ae0b9ee3c7d83` with parents `fbf574c` and `a4a61e4`.
- Backend: full baseline `249 passed`; latest secondary-research/listing/notification/card regression `67 passed`.
- Frontend: `95 passed` and production build passed for the deployed image-upload baseline.
- TypeScript/Vite production build: passed.
- Alembic: one head, `a8d4e6f7b901`.
- Development deployment: public and server-side health returned `environment=development`; frontend bundle contains the front-stage export center, secondary research and listing/observation workbench.
- Development PostgreSQL and Redis containers were preserved during deployment; both remain at `RestartCount=0`.
- Real development PLM E2E processed 2,263 rows and 22 salesperson groups, proved same-file idempotency, and completed one controlled Item through secondary research, listing, weeks 1-5 and the week-4 summary. Arrival cards were a one-time test redirected to 刘学城; persistent autosend remains disabled.

## Implemented Scope

Front stage:

- Import the two approved internal feedback workbooks with source file/sheet/row/snapshot traceability.
- Supervisor assignment by main-SKU group, operator claim/not-claim, supervisor review and audit history.
- Stocking and central traceability exports, including repeatable business-period export with independent batches and no workflow-state rollback.
- Product board, opportunity pool, assignment filters, operator configuration and pricing/percentage display rules.

Later stage:

- Secondary research with five positions: 引流款、利润款、淘汰款、稳定款、清仓款.
- 引流款、利润款、稳定款 enter listing; 淘汰款 and 清仓款 skip listing; only entering 淘汰款 creates the daily supervisor reminder event.
- One main SKU can have multiple manually entered shop + globally unique Item listing records.
- Each Item selects its own first Thursday-to-Wednesday period and observes four independent weeks; later periods are manually added.
- Weekly metrics are read-only; product positioning and optimization action are required; week 4 also requires a summary.
- Completed reviews remain editable with audit; stopped Items may finish already-fetched periods; only explicit stop pauses future fetches and reminders.
- Product detail is read-only for listing/observation history and groups records by source business period.

Detailed field, state, permission and API rules stay in the confirmed requirement and architecture documents; do not duplicate them here.

## Still Open

- Operators and supervisors must complete development-environment UAT with controlled data.
- The real weekly Item endpoint, authentication method and unfiltered aggregate response sample are not provided. Do not guess them. The integration point is the existing `apply_week_metrics(...)` boundary.
- Real scheduling, retry monitoring and operator message delivery for weekly Item metrics remain unconnected.
- Production release of the unified branch is not approved.

## Next Session Checklist

1. Confirm the active branch is based on `lxc/integrated-workflow` and inspect `git status` before editing.
2. Preserve the production/development boundary; normal development and deployment target only `hz-new-product-dev`.
3. Run backend tests, frontend tests/build and Alembic head verification before every release.
4. Update `docs/02-功能实现状态.md`, `docs/20-项目推进总控.md` and `docs/06-部署与服务器准备.md` when implementation or deployment state changes.
5. Use `neat-freak` at milestones; do not delete or archive historical requirement documents without explicit user approval.
