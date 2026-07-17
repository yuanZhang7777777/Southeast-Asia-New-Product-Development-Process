# 刊登与观察已确认差距收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 在不重做现有工作台、不增加运行时依赖的前提下，补齐已经确认的刊登与观察差距，并只部署到公网开发环境 `139.224.2.166:18081`。

**Architecture:** 继续复用现有 FastAPI + SQLAlchemy 服务、`ListingRecord` / `ItemObservationPeriod` / `AuditLog` / `NotificationLog` 表和 React 单表工作台。跨业务期承接使用 `ListingRecord.source_claim_ids` 追加来源关联，不新增表；观察期进入淘汰款使用 `AuditLog` 记录转换事件；浏览器草稿使用原生 `localStorage`。后端与前端分别测试先行，最后做契约整合、文档同步和开发环境部署。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy、pytest、React、TypeScript、Vite、Node `node:test`、Docker Compose。

## Global Constraints

- [x] 不访问、不修改、不重启、不部署生产服务器 `101.132.26.138`，不连接生产库 `workflow_prod_20260715`。
- [x] 只部署开发服务器 `139.224.2.166` 的公网端口 `18081`，使用 SSH 别名 `hz-new-product-dev`，不把密码、Token 或 `.env` 写入仓库、计划、日志或提交。
- [x] 不接入尚未提供的真实周 Item 接口，不猜测账号、鉴权、调度或返回格式；本轮只收口 `apply_week_metrics(...)` 现有边界。
- [x] 不增加数据库表、服务端草稿接口、状态库、表格组件或新 npm / Python 依赖。
- [x] Listing 负责人保持来源任务锁定，不增加负责人转交能力。
- [x] 同一主 SKU 下每条刊登记录仍由运营手填“店铺 + Item + 刊登策略 + 第一周起始周期”，Item 继续全局唯一。
- [x] 二次调研来源的多个子 SKU 定位一致时才提供第 1 周默认值；若来源定位不一致，默认留空并要求运营人工选择，禁止任取一条子 SKU 定位。

---

## Task 1: 用失败测试锁定后端复盘、指标冻结与淘汰转换规则

**Files:**

- Modify: `backend/tests/test_listing_observations.py`
- Modify: `backend/tests/test_notification_jobs.py`

- [x] 将旧测试 `test_period_review_rejects_completed_or_inactive_rows_atomically` 拆成三个验收测试：`test_completed_period_can_be_edited_by_owner_and_manager`、`test_stopped_listing_can_complete_already_fetched_pending_review`、`test_voided_listing_period_cannot_be_reviewed_atomically`。

  断言已完成周期保存后仍为 `completed`，三项自动指标和 `metrics_fetched_at` 不变，人工字段更新，新增一条 `observation.reviewed` 审计；其他运营仍被拒绝；停止前已经取数的 `pending_review` 可提交；已作废 Listing 仍拒绝且整批零修改。

- [x] 将现有指标通知测试扩成 `test_apply_week_metrics_freezes_first_success`：第一次写入 A，第二次传入不同的 B，断言 A、`source_snapshot`、`metrics_fetched_at` 保持不变，运营通知只有一条，`observation.metrics_applied` 审计只有一条。

- [x] 增加 `test_observation_elimination_events_only_on_transitions`，覆盖利润款 → 淘汰款 → 淘汰款 → 稳定款 → 淘汰款只产生两条 `observation.elimination_entered` 审计；同批提交相邻周时也按 Item 周次计算前态。

- [x] 将主管日汇总测试改为 `test_elimination_daily_summary_sends_each_observation_transition_once`：观察期数据从 `AuditLog.action == "observation.elimination_entered"` 读取，按审计事件 ID 去重；成功后不重复，失败仍可重试。二次调研淘汰款现有扫描逻辑继续保留。

- [x] 运行失败测试并确认失败原因只来自尚未实现的规则：

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest backend\tests\test_listing_observations.py backend\tests\test_notification_jobs.py -q
  ```

## Task 2: 实现后端复盘状态、首次指标冻结与淘汰转换事件

**Files:**

- Modify: `backend/app/services.py`
- Modify: `backend/app/notification_jobs.py`

- [x] 在 `apply_week_metrics(...)` 找到周期后、校验本次指标前增加首次成功保护：

  ```python
  if period.metrics_fetched_at is not None:
      return period
  ```

  `metrics is None` 仍保持 `pending_data` 并允许以后重试；已停止、已作废 Listing 仍不得获取新数据。

- [x] 将 `review_observation_periods(...)` 的状态校验调整为：Listing `status` 必须为 `active`；周期状态允许 `pending_review` 或 `completed`；不再因 `tracking_status == "stopped"` 拒绝停止前已取数周期。`pending_data` 仍不可复盘。

- [x] 修改前保存 `old_status` 和 `old_positioning`；已完成周期重编时以本行旧定位判断“非淘汰 → 淘汰”，首次复盘时按同 Item 更早周次的有效定位判断，并让同一批次中较早周的新值参与较晚周判断。

- [x] 仅在进入淘汰款时追加事件审计：

  ```python
  audit(
      db,
      "observation.elimination_entered",
      "item_observation_period",
      period.id,
      {
          "listing_record_id": listing.id,
          "week_number": period.week_number,
          "previous_positioning": previous_positioning,
          "product_positioning": "淘汰款",
      },
      actor_name,
      actor_user_id,
  )
  ```

  连续保持淘汰款不产生事件；改成其他定位后再次进入淘汰款产生新事件；清仓款不触发。

- [x] 在 `notification_jobs._pending_elimination_rows(...)` 中保留二次调研淘汰记录；观察期部分改为查询 `AuditLog.action == "observation.elimination_entered"`，通过 `AuditLog.entity_id` 关联周期和 Listing，并用 `AuditLog.id` 作为 `_EliminationRow.id`。继续复用现有发送、失败重试和 `_mark_elimination_rows_notified(...)`。

- [x] 运行 Task 1 的窄测试，全部通过后再运行：

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest backend\tests\test_secondary_research.py backend\tests\test_workflow_models.py -q
  ```

## Task 3: 用失败测试锁定跨业务期承接、来源期数和定位默认值

**Files:**

- Modify: `backend/tests/test_listing_observations.py`
- Modify: `backend/app/schemas.py`

- [x] 给工作台读契约增加字段并在测试中先断言：

  ```python
  class PendingListingTaskRead(BaseModel):
      requires_confirmation: bool = False
      reusable_listing_ids: list[str] = Field(default_factory=list)

  class ListingRecordRead(BaseModel):
      business_period: str | None = None
      source_business_periods: list[str] = Field(default_factory=list)

  class ObservationPeriodRead(BaseModel):
      business_period: str | None = None
      default_product_positioning: str | None = None

  class ListingBatchRequest(BaseModel):
      task_key: str
      rows: list[ListingBatchRow] = Field(default_factory=list)
      reuse_listing_ids: list[str] = Field(default_factory=list)
  ```

- [x] 增加 `test_later_business_period_reuses_active_items_and_links_new_claims_without_duplicates`：后一期相同主 SKU、标准化站点和负责人返回旧 Listing ID；复用提交不复制 Listing/周期，给旧 `source_claim_ids` 追加新 claim，后一期 claim 进入 `listing_observation`；复用和新增行可以同一事务提交。

- [x] 增加 `test_reuse_and_new_rows_are_atomic_when_reused_listing_is_invalid` 与 `test_cross_period_reuse_does_not_match_other_site_owner_or_main_sku`：已作废、停止跟踪、不同主 SKU/站点/负责人不能沿用；任一复用 ID 或新增行不合法时全部零修改。

- [x] 增加 `test_summary_exposes_source_business_periods_for_frontend_grouping`：`business_period` 返回 Listing 创建期，`source_business_periods` 从全部 `source_claim_ids` 对应机会的业务期去重排序，跨期来源不丢失。

- [x] 增加四个默认定位测试并断言默认值不写入 `ItemObservationPeriod.product_positioning`：`test_workbench_returns_week_one_secondary_positioning_default_without_persisting_it`、`test_later_week_defaults_to_latest_earlier_nonempty_positioning`、`test_later_week_falls_back_to_secondary_positioning_when_history_is_empty`、`test_mixed_secondary_positions_do_not_choose_an_arbitrary_default`。

- [x] 运行 `backend/tests/test_listing_observations.py` 并确认新增测试先失败。

## Task 4: 实现跨期承接、来源上下文和默认定位响应

**Files:**

- Modify: `backend/app/services.py`
- Modify: `backend/app/routers/listing_workbench.py`

- [x] `list_pending_listing_tasks(...)` 对真实 `waiting_listing` claim 分组设置 `requires_confirmation=True`；仅由已有 Listing 重建的上下文设置 `False`。为待确认组寻找 `status == "active"`、`tracking_status == "active"` 且主 SKU、标准化站点/国家、负责人相同的 Listing，返回 `reusable_listing_ids`。

- [x] `create_listing_batch(...)` 接收 `reuse_listing_ids`，要求 `rows` 与 `reuse_listing_ids` 至少有一项；先完成全部新增行、复用记录、权限和自然键校验，再做任何写入。复用成功时用新 list 赋值追加来源：

  ```python
  listing.source_claim_ids = list(dict.fromkeys([
      *(listing.source_claim_ids or []),
      *task["claim_record_ids"],
  ]))
  ```

  然后统一把本期 claim 的 `downstream_status` 设为 `listing_observation`。不修改旧 Listing 的 Item、店铺、周期、负责人和创建业务期，不复制观察周期。

- [x] 在一次批量查询中读取所有 Listing `source_claim_ids` 对应的 `SalesClaimForecast` 和 `NewProductOpportunity`，生成：

  - `source_business_periods`：非空业务期去重排序；
  - `secondary_positioning`：来源 claim 中只有一个唯一非空定位时取该值，存在多个不同定位时返回空。

- [x] `listing_record_read(...)` 返回 `business_period` 和 `source_business_periods`；`observation_period_read(...)` 返回 `business_period` 和只读 `default_product_positioning`。后者按“本周期已保存值由原字段返回；默认值取最近更早非空历史定位，否则取一致的二次调研定位”计算，绝不落库。

- [x] 路由将 `payload.reuse_listing_ids` 传给服务；保留现有 actor、权限和事务边界。

- [x] 运行 Task 3 全部测试，再运行后端刊登、二次调研与通知窄测试。

## Task 5: 用失败测试锁定前端历史、可编辑性、默认定位、跨期分组和本地草稿

**Files:**

- Modify: `frontend/tests/listingObservation.test.ts`
- Modify: `frontend/src/api.ts`

- [x] 同步 TypeScript 契约：`PendingListingTask` 增加 `requires_confirmation` / `reusable_listing_ids`；`ListingRecord` 增加 `business_period` / `source_business_periods`；`ObservationPeriodRow` 增加 `business_period` / `default_product_positioning`；`ListingBatchPayload` 增加可选 `reuse_listing_ids`。

- [x] 增加“待复盘业务筛选保留命中 Item 的全部历史并排除无待办 Item”测试：只要 active Listing 存在 `pending_review`，该 Item 的 completed、pending_review 和 pending_data 历史均保留；显式高级周期筛选仍可收窄。

- [x] 增加“已完成周期和停止后已取数周期可编辑，待取数与作废记录不可编辑”测试，目标纯函数签名：

  ```ts
  canEditObservationPeriod(
    row: Pick<ObservationPeriodRow, "status">,
    listing?: Pick<ListingRecord, "status">
  ): boolean
  ```

- [x] 增加“周期默认定位优先服务端已保存值，其次最近前序定位，最后后端二次调研默认值”测试，目标函数：

  ```ts
  createObservationReviewDraft(row: ObservationPeriodRow): ObservationReviewDraft
  ```

  后端已经计算 `default_product_positioning`，前端不再重复猜测来源 claim；合法本地草稿恢复值始终优先，包括用户主动清空的字段。

- [x] 增加跨期测试：待确认组展示 `reusable_listing_ids` 指向的旧 Item、不复制到原上下文；复用提交 payload 同时允许 `rows` 和 `reuse_listing_ids`；商品详情帮助函数按 `source_business_periods` 分组，当前业务期排在最前。

- [x] 增加原生 Storage fake，测试版本化草稿 helpers：

  ```ts
  listing-observation:v1:<userId>:listing:<taskKey>
  listing-observation:v1:<userId>:period:<periodId>
  ```

  合法草稿可恢复；登录用户、任务和周期互相隔离；JSON 损坏、版本不兼容或字段结构非法时删除该键并回退服务端数据；Storage get/set/remove 抛错不得阻塞页面。

- [x] 运行并确认新增测试先失败：

  ```powershell
  $env:PATH='C:\Users\86173\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
  Set-Location frontend
  node --test tests/listingObservation.test.ts
  ```

## Task 6: 实现前端单表历史、复盘编辑、跨期沿用与浏览器草稿

**Files:**

- Modify: `frontend/src/listingObservation.ts`
- Modify: `frontend/src/ListingObservationView.tsx`
- Modify: `frontend/src/App.tsx`

- [x] 修改 `filterListingWorkbenchGroups(...)`：`pending_review` 先找存在待复盘的 active Listing ID，再返回这些 Item 的全部历史周期；排序优先级不要求 tracking active。普通显式筛选仍在 `visibleGroups` 阶段只显示命中行。

- [x] 新增并使用 `canEditObservationPeriod(...)`：Listing active 且周期不是 `pending_data` 即可编辑。表头“一键全选”只勾选 `pending_review`，completed 通过行内复选框单独选择；停止前已取数行显示“停止跟踪 · 待复盘”并使用待办颜色。

- [x] 使用 `createObservationReviewDraft(...)` 恢复服务端已保存值或 `default_product_positioning`；默认只存在浏览器 state，不自动提交、不落库。

- [x] `buildListingWorkbenchGroups(...)` 用 `requires_confirmation` 判断待刊登，用 `reusable_listing_ids` 把可沿用旧 Item 放进新业务期待确认组，并避免同时生成旧 task 的重复分组。待确认组提供“确认沿用现有 Item”，可与新增行一次原子提交；普通已有组继续提供“新增店铺 + Item”。

- [x] 在 `App.tsx` 传入：

  ```tsx
  <ListingObservationView
    key={authSession.user.id}
    draftUserId={authSession.user.id}
    role={activeRole}
    operatorName={activeOperator}
    canManage={canManage}
    onStatus={setStatusMessage}
  />
  ```

  以登录用户 ID 隔离组件 state 和 Storage；禁止用主管当前切换的运营姓名作为草稿身份。

- [x] 刊登草稿的新增、修改、删除每次同步对应 task key；周期人工字段每次修改同步对应 period key。`loadWorkbench()` 先恢复合法本地草稿，否则使用服务端值/默认定位。刊登或复盘成功后只清本次提交的键和 state；失败不清；清除后再 reload，防止旧 state 覆盖服务器新值。

- [x] 商品详情按 `source_business_periods` 构造业务期分组，当前业务期优先展开，其余可展开；只读复用现有表格和指标格式化，不建设第二套编辑器。

- [x] 运行：

  ```powershell
  npm test
  npm run build
  ```

## Task 7: 全量验证、文档收口、提交和开发环境部署

**Files:**

- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/20-项目推进总控.md`
- Modify: `AGENT_HANDOFF.md`
- Modify only if affected by final code: `docs/01-需求文档-东南亚新品流程.md`
- Append: `C:\Users\86173\.codex\work-logs\2026-29.md`

- [x] 运行完整后端测试：

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest backend\tests -q
  ```

- [x] 运行完整前端测试与生产构建：

  ```powershell
  $env:PATH='C:\Users\86173\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
  Set-Location frontend
  npm test
  npm run build
  ```

- [x] 运行 `git diff --check`，审阅只包含本计划范围；检查 `.env`、密码、Token、私钥和生产地址没有进入 diff。

- [x] 使用 `neat-freak` 对照代码同步功能状态、总控和交接文档；不删除、重命名或合并旧文档。将“真实周 Item 接口、自动调度和真实运营消息发送链路”继续保留为未完成，不虚报。

- [x] 追加 Asia/Shanghai 工作日志，记录实现、测试、提交和开发环境部署，不记录任何秘密。

- [x] 提交本地变更后，对开发机做只读环境检查和备份；确认目标为开发库、开发上传目录、开发 Redis 和端口 `18081`，再按仓库现有 Docker Compose 部署说明重建受影响服务。不得执行任何指向 `101.132.26.138` 的命令。

- [x] 部署后验证：

  ```powershell
  curl.exe -fsS http://139.224.2.166:18081/api/health
  ```

  已验证刘学城开发账号配置、真实鉴权后的工作台读取、公网页面和新前端包；容器日志没有迁移、权限或前端运行错误。当前开发库后半段为 0 条记录，跨期沿用、复盘编辑和草稿刷新恢复由自动化测试覆盖。

- [ ] 由运营 / 主管在开发环境使用实际业务数据完成新增刊登、跨期沿用、复盘重编和刷新恢复草稿的人工 UAT；该项不阻塞本轮代码部署，但完成后才可安排生产窗口。

- [x] 在最终交接中明确：开发访问地址、提交号、部署服务、测试结果、备份位置、剩余未接的真实周 Item 接口与调度；再次声明生产未触碰。
