# Selection1 Remaining Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不向真实人员发送通知的测试阶段，完成选品1从业务期数导入、多人责任看板、PLM 到货承接、二次调研、待刊登到 1-4 周观察期的闭环，并把钉钉正式发送能力做成可审计、可去重、可开关的独立层。

**Architecture:** 保留 `NewProductOpportunity` 作为源商品记录，使用现有 `SalesClaimForecast` 作为“子 SKU + 国家 + 销售员”的责任记录；商品级 `current_status` 只服务前半段公共流程，认领后的进度统一从责任记录投影。PLM 全量到货先落独立批次/明细，再按三项精确匹配已复核通过的责任记录；老品和系统外商品只进入钉钉通知批次。所有定时流程均通过数据库去重，不依赖 scheduler 进程内内存。

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, TypeScript, Vite, openpyxl, pytest, Docker Compose.

---

## 0. 执行边界

- 最新业务口径只以 `docs/2026-07-09-已确认需求记录.md` 为准。旧到货设计和旧四周总结设计有冲突时，不沿用旧文档。
- 当前工作区有大量未提交的有效改动。执行模型不得 `git reset`、`git checkout --`、清理未跟踪文件或在不包含当前改动的新 worktree 中直接开发。
- 预发布仍处于测试阶段：`DINGTALK_CARD_AUTOSEND_ENABLED=false`，新增的 `WORKFLOW_AUTOMATION_ENABLED=false`。没有用户再次明确确认，不得向真实运营/主管发送卡片，不得由预发布定时器自动创建真实二次调研任务。
- 不提交 `.env`、PLM/钉钉凭证、服务器密码、人员全量 Excel/JSON、下载的 PLM 文件或手机号等敏感信息。
- 不为未来功能提前建设通用工作流引擎。复用当前模型、路由、通知日志和 scheduler。

## 1. 当前完成度盘点

| 模块 | 状态 | 结论 |
|---|---|---|
| 分配推荐：站点隔离、主 SKU 组、重点品类同级、按组负载、计入未完成任务 | 已完成 | 已有规则和服务层测试。 |
| 人员默认优先级 0、新增追加末尾、同负载按高优先级分配 | 已完成 | `assignment_priority`、`display_order` 已进入模型、迁移、接口和测试。 |
| 超级管理员停用/恢复单 SKU、主 SKU 组、整次导入 | 已完成 | 最终口径采用软停用和审计，不做物理删除。 |
| 商品看板紧凑分页 | 已完成，需最终回归 | 不再作为独立开发项。 |
| 待认领全屏详情工作台、子 SKU 行内填写、图片、主 SKU 上下组切换 | 已完成，需最终回归 | 已有前端草稿测试；保留“第一个认领、第二个不认领”的验收用例。 |
| 钉钉全公司 userId 首次拉取 | 已完成 | 已完成 1066 人、23 字段的私有缓存；敏感文件不入库。 |
| PLM 老导出、新 open 接口、文件解析预览 | 部分完成 | 下载和预览已有；新 open 数据没有销售员，不能用于个人通知。 |
| 二次调研工作台 | 部分完成 | 已有每责任记录字段、全宽表格、来源模块、图片、草稿和整组提交，但字段校验、首次同步、期数筛选和顶部信息未完全符合最终口径。 |
| 业务期数与数据 Sheet 分离、增量重导 | 未完成 | 当前仍复用 `source_sheet`，且按文件/Sheet/行号更新。 |
| 多人责任商品看板 | 未完成 | 看板仍主要读取商品全局 `current_status`。 |
| PLM 精确匹配与自动到货承接 | 未完成 | 尚未持久化 PLM 批次、精确关联责任、生成到货记录或二次调研承接。 |
| 到货/淘汰/周四复核钉钉汇总 | 未完成 | 当前主管卡片仍可能在单次认领提交时触发，scheduler 仍有每周人员同步。 |
| 待刊登、已刊登、自动 1-4 周观察期 | 未完成且部分字段待确认 | 状态和页面尚未实现；多店铺及周记录字段未最终确认。 |
| 选品2历史库存全量匹配 | 明确延期 | 等选品1闭环稳定后再单独规划。 |

上次完整验证基线为：后端 `143 passed`，前端 `5 passed`，前端生产构建通过，数据库迁移头为 `e5a9b0c1d234`。执行第一步必须重新跑基线，不能直接引用该结果。

## 2. 目标流程与状态解释

```text
数据 Sheet + 业务期数导入
  -> 新品机会池
  -> 主管分配
  -> 运营认领/不认领
  -> 主管复核
  -> 待导出
  -> 待到货
  -> PLM 精确匹配成功
  -> 待二次调研
  -> 整组提交
     -> 淘汰款：已停用
     -> 引流款/利润款：待刊登
  -> 已刊登
  -> 自动进入 1-4 周观察期（最后一环）
```

- “二次调研完成”按最新提交规则作为审计里程碑，不作为需要停留和再次点击的独立当前状态；提交成功后直接进入 `待刊登` 或 `已停用`。
- “部分认领”“多人认领”只做看板标签。
- PLM 新品/老品判定使用“首次上架日期 == 最后一次入库日期”。不使用库存数量判定。
- 老品补货和系统外商品只生成到货通知明细，不进入商品看板。

## 3. 文件结构决策

### 后端

- `backend/app/models.py`: 只增加业务期数批次字段、PLM 到货批次/明细、刊登/观察记录；责任状态继续保存在 `SalesClaimForecast`。
- `backend/app/workflow_status.py`: 统一责任状态常量和展示映射，避免散落字符串。
- `backend/app/selection1_importer.py`: 负责数据 Sheet 读取、业务期数身份和增量 upsert。
- `backend/app/services.py`: 保留现有前半段服务；新增责任看板投影、精确匹配和状态转换。若文件继续增长，新增的 PLM 处理放入 `backend/app/plm_processing.py`，不要再塞进 `services.py`。
- `backend/app/plm_download.py`: 只负责 PLM 鉴权、异步导出、分页和缓存，不承担业务匹配。
- `backend/app/plm_arrivals.py`: 只负责 Excel 字段解析和新品/老品分类。
- `backend/app/plm_processing.py`: 新建，负责持久化批次、精确匹配、去重和开启二次调研。
- `backend/app/dingtalk_card_sender.py`: 增加到货卡片构建/发送；不耦合数据库查询。
- `backend/app/notification_jobs.py`: 新建，负责到货、淘汰、周四复核三类汇总任务。
- `backend/app/scheduler.py`: 只判断何时调用作业，不保存唯一业务状态。
- `backend/app/routers/product_board.py`: 新建责任看板只读查询接口。
- `backend/app/routers/listing.py`: 待刊登和确认已刊登接口。

### 前端

- `frontend/src/App.tsx`: 保留外壳、导入、前半段页面；移除独立到货导航并接入新商品看板。
- `frontend/src/SecondaryResearchView.tsx`: 收口二次调研交互，不再增加新业务模块。
- `frontend/src/secondaryResearchDrafts.ts`: 放首次同步、默认时间和提交完整性纯函数。
- `frontend/src/ProductBoardView.tsx`: 新建责任看板，避免继续放大 `App.tsx`。
- `frontend/src/ListingView.tsx`: 待刊登/已刊登/观察期页面；等 Task 8 决策闸门通过后实现。

---

### Task 0: 保护当前基线并建立验收数据

**Files:**
- Read: `docs/2026-07-09-已确认需求记录.md`
- Read: `git status --short`
- Test: `backend/tests/`
- Test: `frontend/tests/`

- [ ] **Step 1: 确认测试开关关闭**

检查预发布配置但不打印值，只确认以下布尔值：

```text
DINGTALK_CARD_AUTOSEND_ENABLED=false
WORKFLOW_AUTOMATION_ENABLED=false
```

- [ ] **Step 2: 重新跑完整基线**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm test
npm run build
```

Expected: 后端全部通过，前端 5 个及以上测试通过，`tsc && vite build` 成功。

- [ ] **Step 3: 建立一份不含真实人员通知的验收场景**

在测试代码中固定以下场景，不把临时 Excel 写入仓库：

```text
业务期数：TEST-2026-W29
主 SKU MAIN-A：SUB-A1、SUB-A2，同一国家、同一运营
主 SKU MAIN-B：SUB-B1，同一国家、运营 A 和运营 B 均复核通过
二次调研：SUB-A1 引流款、SUB-A2 淘汰款
PLM：一条新品精确匹配、一条老品、一条销售员不匹配
```

- [ ] **Step 4: 保存基线证据**

把测试命令和结果追加到本计划最下方“执行记录”，不得写入凭证或真实手机号。不要在基线未通过时开始 Task 1。

---

### Task 1: 分离数据 Sheet 与业务期数并实现增量重导

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/selection1_importer.py`
- Modify: `backend/app/routers/opportunities.py`
- Modify: `backend/app/services.py`
- Create: `backend/alembic/versions/f6b0c2d3e456_separate_business_period.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Test: `backend/tests/test_selection1_import.py`
- Test: `backend/tests/test_mvp_flow.py`
- Test: `backend/tests/test_traceability_export.py`

- [ ] **Step 1: 先写失败测试，证明 Sheet 与期数独立**

测试请求必须同时包含：

```json
{
  "source_sheet": "选品1原始数据",
  "business_period": "2026年第29期"
}
```

断言 `source_sheet == "选品1原始数据"`、`batch == "2026年第29期"`，快照仍保留真实文件、Sheet、行号。

- [ ] **Step 2: 写失败测试，证明增量更新身份不依赖行号和文件名**

第一次导入 `SUB-A` 在第 3 行，第二次换文件并移动到第 8 行，同时修改商品名并新增 `SUB-B`。断言：

```text
NewProductOpportunity 总数 = 2
SUB-A 的源字段已更新
SUB-A 的 id、认领、复核和 downstream_status 未改变
第二次文件缺失的旧 SKU 不被删除或停用
两次 SourceRecordSnapshot 均保留
```

- [ ] **Step 3: 最小化模型改动**

使用现有 `NewProductOpportunity.batch` 存业务期数；只给 `ImportBatch` 增加：

```python
business_period: Mapped[str | None] = mapped_column(String(128), index=True)
```

删除旧的 `source_type + source_file + source_sheet + source_row` 唯一约束，保留普通来源追溯索引。MVP 导入由单个主管串行操作，应用层按下列身份查询，不新增复杂锁表：

```python
source_type + business_period + normalized_site + main_sku + sub_sku
```

迁移固定使用 `revision = "f6b0c2d3e456"`、`down_revision = "e5a9b0c1d234"`，保证接在当前二次调研迁移之后。

- [ ] **Step 4: 更新请求和上传接口**

`Selection1ImportRequest` 和 multipart 上传同时接收 `source_sheet`、`business_period`。`business_period` 为空时默认等于已选 Sheet 名；自定义值不影响工作簿读取。

- [ ] **Step 5: 更新期数查询和导出**

新增 `business_period` 查询参数，前端停止把 `source_sheet` 当期数。为已有调用保留一个版本的 `source_sheet` 兼容读取，但新代码和页面统一发送 `business_period`。

- [ ] **Step 6: 更新导入 UI**

同一行展示“数据 Sheet”下拉框和“业务期数”输入框；业务期数默认跟随 Sheet，用户手动修改后不再被切换 Sheet 覆盖。文案不再写“选择要导入的期数”。

- [ ] **Step 7: 运行聚焦测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_selection1_import.py backend\tests\test_mvp_flow.py backend\tests\test_traceability_export.py -q
```

Expected: 全部通过，重复导入不新增重复业务记录。

---

### Task 2: 收口二次调研最终规则

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/app/routers/secondary_research.py`
- Modify: `backend/app/schemas.py`
- Modify: `frontend/src/secondaryResearchDrafts.ts`
- Modify: `frontend/src/SecondaryResearchView.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/styles.css`
- Test: `backend/tests/test_secondary_research.py`
- Test: `frontend/tests/secondaryResearchDrafts.test.ts`

- [ ] **Step 1: 修正 AL-AM 必填口径的失败测试**

新增后端测试：AM 为空、AN/AO 完整时可提交；AL 未传时由服务端写入提交时间。再测用户传入 AL 时保留用户值。

- [ ] **Step 2: 修正提交校验**

整组提交只校验：

```python
secondary_conclusion is not blank
product_positioning in {"引流款", "利润款", "淘汰款"}
```

`secondary_competitor_url` 选填；`secondary_research_at` 为空时在提交事务内写 `datetime.now(timezone.utc)`。

- [ ] **Step 3: 实现首次填写同步纯函数**

给 `secondaryResearchDrafts.ts` 增加一个纯函数，规则为：第一条开始填写时，补丁同步到同组仍为空且未被单独编辑的子 SKU；某行被直接编辑后，该行不再接受其他行同步。

测试序列：

```text
编辑 SUB-A1 的结论 -> SUB-A2/SUB-A3 获得相同结论
直接修改 SUB-A2 -> SUB-A2 标记独立
继续编辑 SUB-A1 的定位 -> SUB-A3 同步，SUB-A2 保持自己的值
```

- [ ] **Step 4: 默认填写时间并保留可编辑**

新建空草稿时显示浏览器本地当前时间；服务端仍是最终兜底。不要把“查看历史记录”触发成草稿写入。

- [ ] **Step 5: 增加业务期数切换**

接口返回可用期数列表或前端从同一响应提取；默认选择最新期数，支持历史期数和“全部期数”。主 SKU 分组键必须包含来源、业务期数、站点、主 SKU、销售员。

- [ ] **Step 6: 补齐顶部压缩信息**

顶部一行或两行紧凑展示主 SKU、商品名、业务期数、站点、负责人、到货时间、类目、关键词、开品理由。子 SKU 仍在表格左侧，不恢复狭窄左右分栏。

- [ ] **Step 7: 保持提交分流**

整组提交后逐责任记录设置：

```text
淘汰款 -> disabled
引流款/利润款 -> waiting_listing
```

同时写审计事件 `secondary_research.completed`；不要增加一个需要再次操作的“二次调研完成”停留状态。

- [ ] **Step 8: 运行测试和构建**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_secondary_research.py -q
Set-Location frontend
npm test
npm run build
```

Expected: AM 为空可提交；首次同步和后续独立修改测试通过。

---

### Task 3: 建立责任状态投影和商品看板接口

**Files:**
- Modify: `backend/app/workflow_status.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services.py`
- Create: `backend/app/routers/product_board.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_product_board.py`

- [ ] **Step 1: 先写多人认领失败测试**

同一机会创建运营 A、运营 B 两条已复核认领责任；A 为 `waiting_secondary_research`，B 为 `waiting_listing`。断言：

```text
owner=A 只返回 A 且状态为待二次调研
owner=B 只返回 B 且状态为待刊登
manager 不传 owner 时两条都返回
一人的状态变化不覆盖另一人
```

- [ ] **Step 2: 定义唯一状态映射函数**

先新增 `CLAIM_WAITING_EXPORT = "waiting_export"`。主管复核通过时责任进入 `waiting_export`；该责任进入任意一次导出批次后改为 `waiting_arrival`。PLM 精确到货允许从两者任一状态直接进入 `waiting_secondary_research`，因为实际点击导出不是后续资格条件。

新增 `responsibility_visible_status(opportunity, claim, review)`，按以下优先级返回：

```text
claim.downstream_status 存在 -> 使用责任状态
已复核通过但旧数据尚无 downstream_status -> 待导出
未进入责任阶段 -> 使用前半段 opportunity.current_status 映射
```

- [ ] **Step 3: 新建只读看板接口**

`GET /product-board` 支持：

```text
owner
business_period
visible_status
arrival_date_from
arrival_date_to
site
query
```

运营身份强制 `owner = 当前运营`；主管和超级管理员可看全部。接口仍返回主 SKU 分组、子 SKU、责任数组和“多人认领/部分认领”派生标签，但主表展示不得按销售员拆行；销售员维度只用于筛选、汇总标签、展开行和详情。

- [ ] **Step 4: 保持严格期数隔离**

同一主 SKU/子 SKU 出现在两期时，接口返回两个业务期数组，不合并。测试必须覆盖这一点。

- [ ] **Step 5: 运行接口测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_product_board.py backend\tests\test_review_flow.py backend\tests\test_export_batch.py -q
```

Expected: 多人、多期、导出前后状态均正确。

---

### Task 4: 重做商品看板为“我的责任商品”视图

**Files:**
- Create: `frontend/src/ProductBoardView.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Create: `frontend/tests/productBoard.test.ts`
- Modify: `frontend/package.json`

- [ ] **Step 1: 先写前端纯函数测试**

测试主 SKU 分组不跨期、状态筛选读取责任状态、主表一行仍代表一个主 SKU 组、多人认领标签只在责任数大于 1 时出现。

- [ ] **Step 2: 实现紧凑筛选栏**

一行优先展示：搜索、业务期数、负责人、业务状态、到货日期、站点、清空。运营负责人固定为“我”；主管显示负责人下拉。

- [ ] **Step 3: 实现主 SKU 表格和责任展开**

主表用于扫视，一个主 SKU 组只展示一行；展开后显示每个子 SKU 下每位销售员的状态、到货时间、二次调研定位和下一步。不要把每个字段做成独立装饰卡片。

- [ ] **Step 4: 移除独立到货业务入口**

从 `FLOW_STEPS`、`VIEW_COPY` 和页面渲染移除“到货预览”。后端 `/arrival/plm-preview` 暂时保留为主管诊断接口，不再进入主流程导航。

- [ ] **Step 5: 连接动作入口**

责任状态为待二次调研时进入二次调研工作台；待刊登时进入刊登页。看板详情只读，不在详情里重复建设二次调研表单。

- [ ] **Step 6: 桌面和移动端验收**

使用浏览器截图检查 `1440x900`、`1920x1080`、`390x844`：筛选栏不穿模，表格文字不覆盖，移动端允许表格内部横向滚动。

- [ ] **Step 7: 运行测试和构建**

Run:

```powershell
Set-Location frontend
npm test
npm run build
```

Expected: 所有测试和构建通过。

---

### Task 5: 持久化 PLM 到货批次并精确匹配责任

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/plm_arrivals.py`
- Create: `backend/app/plm_processing.py`
- Modify: `backend/app/routers/arrival.py`
- Modify: `backend/app/config.py`
- Create: `backend/alembic/versions/a7c1d3e4f567_add_plm_arrival_batches.py`
- Modify: `backend/tests/test_plm_arrivals.py`
- Create: `backend/tests/test_plm_processing.py`

- [ ] **Step 1: 先写解析与分类失败测试**

用内存工作簿验证按表头读取 `销售员、集团、国家、主 SKU、子 SKU、商品名、首次上架时间、最后一次入库时间`。AM/AL 只是用户说明的当前列位置，代码不得硬编码列号。

- [ ] **Step 2: 新增最小持久化模型**

新增：

```text
PlmArrivalBatch: arrival_date, source_file, source_hash, status, processed_at, row_count
PlmArrivalItem: batch_id, arrival_type, salesperson_name, country, main_sku,
                sub_sku, product_name, first_listing_time, latest_storage_time,
                matched_claim_record_id, match_status
```

`source_hash` 唯一，避免同一文件重复处理。`ArrivalRecord` 继续只记录成功关联平台责任的到货事实。

迁移固定使用 `revision = "a7c1d3e4f567"`、`down_revision = "f6b0c2d3e456"`。

- [ ] **Step 3: 写精确匹配失败测试**

只匹配同时满足以下条件的复核通过责任：

```python
normalized(plm.sub_sku) == normalized(opportunity.sub_sku)
normalize_site_code(plm.country) == normalize_site_code(opportunity.site or opportunity.country)
plm.salesperson_name.strip() == claim.salesperson_name.strip()
review.review_status == "approved"
```

销售员不一致、未复核、已确认不认领均为 `unmatched`，不做纠错、不做人工匹配列表。

- [ ] **Step 4: 处理多期和多人**

同一三项精确组合若在多个业务期都有有效责任，分别开启各期责任；同一期多人时只开启姓名精确相同的人。每个批次/责任只能创建一条 `ArrivalRecord`。

- [ ] **Step 5: 执行内部状态流转**

当 `WORKFLOW_AUTOMATION_ENABLED=true` 时，匹配成功调用现有 `open_secondary_research`，写 `arrival_detected_at` 和 `ArrivalRecord`；测试环境可直接测试服务函数。配置为 false 时只计算 dry-run 报告，不修改责任状态。

- [ ] **Step 6: 老品和系统外商品边界**

所有 PLM 明细都落 `PlmArrivalItem`，但以下记录不创建平台后续：

```text
arrival_type == restock
精确匹配不到系统责任
集团不是集团八部
```

- [ ] **Step 7: 增加 dry-run 接口**

主管接口返回：批次行数、新品/老品数、精确匹配数、不匹配数、将开启的责任列表。不得提供手工纠错或确认匹配按钮。

- [ ] **Step 8: 明确数据源**

自动个人通知继续使用 7878 异步导出的 Excel，因为现有 open `listDetail` 没有销售员。open 接口只保留诊断/未来备用，不作为当前自动承接源。

- [ ] **Step 9: 运行 PLM 测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_plm_download.py backend\tests\test_plm_arrivals.py backend\tests\test_plm_processing.py -q
```

Expected: 新品、老品、不匹配、多人、多期、重复文件全部通过。

---

### Task 6: 实现到货卡片、淘汰款汇总和周四复核汇总

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/dingtalk_card_sender.py`
- Create: `backend/app/notification_jobs.py`
- Modify: `backend/app/scheduler.py`
- Modify: `backend/app/services.py`
- Modify: `backend/app/routers/claims.py`
- Modify: `backend/app/routers/reviews.py`
- Modify: `backend/app/routers/admin.py`
- Modify: `backend/app/dingtalk_user_sync.py`
- Test: `backend/tests/test_dingtalk_card_sender.py`
- Test: `backend/tests/test_dingtalk_auto_notifications.py`
- Modify: `backend/tests/test_scheduler.py`
- Create: `backend/tests/test_notification_jobs.py`

- [ ] **Step 1: 写到货卡片参数测试**

到货卡片使用后端固定模板常量，不再通过环境变量配置。参数只能包含：

```text
card_title, summary_text, left_label, left_count,
sku_markdown, action_text, action_url
```

`sku_markdown` 先新品后老品，每条显示主 SKU、子 SKU 数、商品名。

- [ ] **Step 2: 每位销售员每天一张到货卡片**

从 `PlmArrivalItem` 按 `arrival_date + salesperson_name` 汇总，使用 `NotificationLog.dedupe_key` 保证成功记录不重发。销售员为空或没有 userId 时记录 `skipped_no_receiver`，不猜姓名。

- [ ] **Step 3: 每日 09:00 淘汰款汇总**

扫描 `product_positioning=淘汰款`、已提交且尚无成功通知日志的责任记录。按运营、业务期数、主 SKU 组织 `sku_markdown`；所有启用的 `manager` 和 `super_admin` 每人最多一张，不使用硬编码姓名白名单。

- [ ] **Step 4: 每周四 09:00 复核汇总**

移除 `POST /claims` 中单次提交立即通知主管的调用。周四作业统计实时待复核认领数和不认领数，给所有启用主管/超级管理员各一张新品待办卡片。

- [ ] **Step 5: 保留退回补充即时提醒**

主管退回时立即给对应运营发送待补充卡片；测试证明该行为不等待周四。

- [ ] **Step 6: 取消每周全量人员同步**

删除 `dingtalk_user_sync_due` 及 scheduler 周期调用。新增人员时先查私有缓存；缓存无该姓名时才刷新一次公司通讯录并绑定唯一姓名。重名时不自动选择，保留未绑定并在人员配置页提示。

- [ ] **Step 7: scheduler 使用持久化去重**

每天 08:00 下载前一天文件；09:00 后文件未成功时继续每 5 分钟重试，成功后处理并补发一次。进程重启后通过 PLM 批次和通知日志判断是否已经完成，不能依赖 `completed_date` 内存变量。

- [ ] **Step 8: 测试期硬闸门**

`WORKFLOW_AUTOMATION_ENABLED=false` 时不执行责任状态流转；`DINGTALK_CARD_AUTOSEND_ENABLED=false` 时不调用钉钉 HTTP。允许通过 fake sender 和测试接收人验证完整 payload。

- [ ] **Step 9: 运行通知测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_dingtalk_card_sender.py backend\tests\test_dingtalk_auto_notifications.py backend\tests\test_notification_jobs.py backend\tests\test_scheduler.py -q
```

Expected: 无即时主管提交卡片；周四/每日汇总、动态接收人、失败重试和去重均通过。

---

### Task 7: 对齐字段流转和市场监控导出

**Files:**
- Modify: `backend/app/services.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/market_monitor.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_traceability_export.py`
- Create: `backend/tests/test_market_monitor_export.py`

- [ ] **Step 1: 写选品1字段映射测试**

生成市场监控导出行并断言：

```text
AD <- 选品1 K
AE <- 选品1 AJ
AF <- 选品1 AL
AG <- 选品1 AM
AH <- 选品1 AO
AI <- 选品1 AP
AJ <- 认领日销
AK <- 首次调研结论
AL <- 二次调研时间
AM <- 二次竞对链接
AN <- 二次调研结论
AO <- 产品定位
```

- [ ] **Step 2: A-AC 使用表头语义匹配**

优先按源表表头映射，列字母只作兼容回退；不得假设列位置永远不变。所有输出仍附来源文件、真实 Sheet、业务期数、行号和快照 id。

- [ ] **Step 3: 每条责任独立导出**

同一子 SKU 被两位运营认领时，AJ-AO 按各自责任记录输出两行，不相互覆盖。不同业务期数同样分行。

- [ ] **Step 4: 运行导出测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_market_monitor_export.py backend\tests\test_traceability_export.py -q
```

Expected: 映射、多人、多期均通过。

---

### Task 8: 刊登和 1-4 周观察期决策闸门

这一阶段不能靠开发侧盲猜。执行 Task 8 前必须由用户确认以下三点，并把答案追加到 `docs/2026-07-09-已确认需求记录.md`：

1. 同一“子 SKU + 国家 + 销售员”能否有多条刊登记录（多店铺/多个 Item ID），还是只保留一条。
2. 确认已刊登时的必填字段。旧讨论里出现过 Item ID、刊登链接、店铺、刊登价格、刊登时间，但尚未形成最新最终口径。
3. 每周观察记录具体填写哪些字段；当前只确认“可填、不强制、不催办、观察期是最后一环”。

在未确认前，下一模型可以完成 Task 0-7，但不得创造刊登/观察字段。

确认后按以下不变规则实施：

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/workflow_status.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/listing.py`
- Create: `backend/alembic/versions/b8d2e4f5a678_add_listing_observation.py`
- Create: `backend/tests/test_listing_observation.py`
- Create: `frontend/src/ListingView.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 按确认字段写失败测试**

测试必须覆盖责任独立、期数隔离、淘汰款不可刊登、非待刊登状态不可重复确认。

迁移固定使用 `revision = "b8d2e4f5a678"`、`down_revision = "a7c1d3e4f567"`；Task 8 延期时不创建该迁移，不留下空 revision。

- [ ] **Step 2: 确认已刊登即自动进入观察期**

同一事务保存刊登记录、`listed_at`，并把责任状态改为 `observation_1_4_weeks`；不增加“手动开启观察期”按钮。

- [ ] **Step 3: 按 7 天计算周次**

```python
week_number = min(4, max(1, (today - listed_at.date()).days // 7 + 1))
```

周记录选填，缺失不阻塞，不生成通知。第 4 周结束后仍保持观察期最后状态，不进入四周总结或流程完成。

- [ ] **Step 4: 移除旧四周总结入口**

停止注册 `backend/app/routers/summary.py` 的业务路由，前端移除 `api.summary`。历史表先保留只读数据，不在本次迁移中物理删除。

- [ ] **Step 5: 运行聚焦测试与构建**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests\test_listing_observation.py -q
Set-Location frontend
npm test
npm run build
```

---

### Task 9: 全链路回归、迁移和预发布部署

**Files:**
- Modify: `docs/2026-07-09-已确认需求记录.md`
- Modify: `docs/superpowers/plans/2026-07-13-selection1-remaining-workflow.md`

- [ ] **Step 1: 跑全量测试**

Run:

```powershell
.\.venv312\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend
npm test
npm run build
```

Expected: 全部通过，不接受“聚焦测试通过但全量失败”。

- [ ] **Step 2: 本地迁移演练**

在临时测试数据库执行：

```powershell
alembic upgrade head
alembic current
```

Expected: current revision 等于新的 head；重复执行 upgrade 不产生错误。

- [ ] **Step 3: 预发布备份和部署**

使用现有 SSH 别名和服务器环境变量，不把密码写进命令或文档。先备份 PostgreSQL，再重建：

```text
migrate -> api -> worker -> scheduler -> frontend -> reverse-proxy
```

持久服务应看到 7 个健康/运行容器：`postgres`、`redis`、`api`、`worker`、`scheduler`、`frontend`、`reverse-proxy`；`migrate` 是一次性成功退出任务。

- [ ] **Step 4: 保持真实发送关闭**

部署后再次确认两个开关仍为 false。不要调用真实发送接口；只做 dry-run、测试接收人或 fake sender 验收。

- [ ] **Step 5: 公网验收**

检查健康接口、登录、业务期数导入、分配推荐、认领矩阵、主管复核、商品看板、二次调研、PLM dry-run。使用测试期数据完成：

```text
第一个子 SKU 认领，第二个子 SKU 不认领
同一商品两位运营各自可见且状态互不覆盖
二次调研首次同步后可逐行改写
AM 为空仍能提交
引流款进入待刊登，淘汰款进入已停用
PLM 销售员不匹配不关联
重复处理同一 PLM 文件不重复创建记录
```

- [ ] **Step 6: 更新执行记录**

记录测试数量、迁移 head、部署时间、健康结果和未执行的 Task 8 决策项。不要记录服务器密码、Token、手机号或人员清单路径。

---

## 4. 明确延期范围

- 选品2整套后半段流程。
- 选品2及系统接入前历史库存的 PLM 全量匹配；其切入时点、去重和首次提醒策略未确认。
- PLM open 接口直接做个人通知；当前响应无销售员。
- 人工匹配列表、姓名纠错、模糊匹配。
- 四周总结待复核、流程完成、周记录催办。
- 在线表格自动回写；当前继续以可追溯导出为准。

## 5. 阶段验收顺序

1. Task 0-2：先把现有二次调研和期数身份做正确。
2. Task 3-4：再让商品看板真实表达多人责任进度。
3. Task 5：PLM 只做 dry-run 和测试数据库承接。
4. Task 6-7：完成通知批次和市场监控数据流，但真实发送继续关闭。
5. Task 8：用户补齐刊登/观察字段后实施。
6. Task 9：全量回归并部署预发布。

不要并行修改 `models.py`、`services.py`、`App.tsx` 或 Alembic head；这些是共享热点。可以并行的只有互不写同一文件的前端纯函数测试、PLM 解析测试和需求文档核对。

## 6. 执行记录

- 计划创建：2026-07-13。
- 当前状态：Task 0-7 已完成本地开发和验证；Task 8 刊登/观察字段仍待业务确认；预发布部署因当前机器 SSH 公钥未被服务器接受而阻塞。
- Task 0 基线验证：2026-07-13，已确认 `.env` 与 `.env.example` 中 `DINGTALK_CARD_AUTOSEND_ENABLED=false`、`WORKFLOW_AUTOMATION_ENABLED=false`，未记录任何凭证。
- Task 0 测试结果：`.\.venv312\Scripts\python.exe -m pytest backend\tests -q` -> 143 passed；`npm.cmd test` -> 5 passed；`npm.cmd run build` -> tsc && vite build 成功。
- Task 1-7 执行结果：业务期数分离、二次调研规则、多人责任商品看板、商品看板前端、PLM 到货持久化/精确匹配、钉钉汇总通知、市场监控导出均已完成聚焦测试。
- Task 7 聚焦验证：`.\.venv312\Scripts\python.exe -m pytest backend\tests\test_market_monitor_export.py backend\tests\test_traceability_export.py -q` -> 9 passed。
- Task 9 本地全量验证：`.\.venv312\Scripts\python.exe -m pytest backend\tests -q` -> 170 passed；`npm.cmd test` -> 9 passed；`npm.cmd run build` -> tsc && vite build 成功。
- Task 9 迁移演练：临时 SQLite 数据库执行 `alembic upgrade head` 成功，`alembic current` -> `a7c1d3e4f567 (head)`；重复执行 `upgrade head` 无错误。
- Task 9 部署状态：尝试使用本机 SSH 公钥连接 `101.132.26.138:2323`，服务器返回 `Permission denied (publickey,...)`；未使用或记录服务器密码，未执行远端备份、迁移、重建或健康检查。
