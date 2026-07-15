# 前半段生产稳定性修复实施计划

> **For Codex:** Use `superpowers:executing-plans` and complete each task with test-first red/green verification.

**Goal:** 修复选品 1 漏导、认领单销和复核前编辑流程，并补齐分配筛选、运营排序和竞品区分，最后无中断滚动发布到生产。

**Architecture:** 保留现有 FastAPI + SQLAlchemy + React 状态模型，复用 `claim_daily_sales`、`display_order` 和现有 API。前端新增的筛选和排序规则放在可单测的纯函数中，组件只负责渲染和触发已有接口。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest, React 19, TypeScript, Node test runner, Vite, Docker Compose, Caddy, PostgreSQL.

---

## Task 1: 修复选品 1 汇总行误判和上传目录

**Files:**
- Modify: `backend/tests/test_selection1_import.py`
- Modify: `backend/app/selection1_importer.py`
- Modify: `backend/app/routers/opportunities.py`

1. 增加回归测试：合法商品行的开品理由包含“月销合计”仍被导入，精确汇总行和重复表头仍跳过。
2. 增加上传目录断言：`UPLOAD_ROOT` 必须位于后端根目录 `.private_uploads/source-workbooks`。
3. 运行 `pytest backend/tests/test_selection1_import.py -q`，确认新测试按预期失败。
4. 收紧 `is_summary_row`，只检查身份/标题列的精确汇总标记；把 `UPLOAD_ROOT` 修正到 Compose 持久卷对应路径。
5. 重跑同一测试文件并确认通过。

## Task 2: 补齐最新认领单销和可编辑认领 API

**Files:**
- Modify: `backend/tests/test_review_flow.py`
- Modify: `backend/tests/test_assignment_flow.py`
- Modify: `backend/tests/test_mvp_flow.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/opportunities.py`
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/services.py`

1. 增加 API 测试：机会列表返回 `latest_claim_daily_sales`。
2. 增加流程测试：所属运营首次提交后可在主管复核前修改，保留首次提交时间，只保留一个待复核任务。
3. 增加权限测试：其他运营不能修改；主管产生任何复核记录后不能修改。
4. 增加任务测试：本人已提交但未复核的认领任务继续出现在 `/tasks/my`。
5. 运行相关 pytest，确认失败原因分别是字段缺失、任务查找仅限 pending 和复核任务重复风险。
6. 最小修改 schema、摘要填充、任务查询和认领提交服务以满足测试，不新增数据库迁移。
7. 重跑相关 pytest 并确认通过。

## Task 3: 修复前端业务分组和认领编辑状态

**Files:**
- Modify: `frontend/tests/claimDrafts.test.ts`
- Create: `frontend/tests/opportunityGroups.test.ts`
- Modify: `frontend/src/claimDrafts.ts`
- Create: `frontend/src/opportunityGroups.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/package.json`

1. 先写纯函数测试：相同主 SKU 在不同期数或站点不得合组；最新平台认领可初始化认领/不认领草稿和单销。
2. 运行前端定向测试，确认新行为失败。
3. 把分组键改为来源类型、业务期数、标准化站点、主 SKU；从 API 最新认领字段初始化草稿。
4. 将用户可见“认领日销”统一为“认领单销”，包括二次调研页面。
5. 重跑前端测试。

## Task 4: 增加运营认领期数与状态筛选

**Files:**
- Create: `frontend/tests/operatorClaimFilters.test.ts`
- Create: `frontend/src/operatorClaimFilters.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/package.json`

1. 写测试：按 `created_at` 选择最新有效期数，按待填写、已认领待复核、不认领待复核、退回补充筛选。
2. 运行测试确认失败。
3. 实现纯筛选函数，并在运营认领台增加期数和状态控件；默认最新期，保留已提交未复核项目。
4. 重跑测试并执行 `npm run build`。

## Task 5: 补齐商品看板和详情展示

**Files:**
- Modify: `frontend/tests/productBoard.test.ts`
- Modify: `frontend/src/ProductBoardView.tsx`
- Modify: `frontend/src/App.tsx`

1. 更新测试，要求主行直接包含去重后的已分配运营文本，并保留责任明细认领单销。
2. 运行测试确认主行展示能力缺失。
3. 增加“已分配运营”主列；在子 SKU 责任、商品详情和主管复核卡片显示认领单销。
4. 重跑前端测试和构建。

## Task 6: 第二批分配筛选和运营排序

**Files:**
- Create: `frontend/tests/assignmentFilters.test.ts`
- Create: `frontend/src/assignmentFilters.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/package.json`

1. 写测试：关键词空格分词后任一命中，站点/一级类目/运营/关键词之间同时满足；运营匹配推荐或手动选择。
2. 写测试：运营按站点、`display_order`、姓名稳定排序；上下移动只改变同站点顺序。
3. 运行测试确认失败。
4. 实现纯函数和分配台四类筛选控件；人员配置增加上下移动图标按钮并复用批量保存接口。
5. 重跑测试和构建。

## Task 7: 第二批竞品分组样式

**Files:**
- Create: `frontend/tests/competitorGroups.test.ts`
- Create: `frontend/src/competitorGroups.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/package.json`

1. 写测试固定五组竞品字段到样式键和文字标签的映射。
2. 运行测试确认失败。
3. 在运营矩阵列和商品详情竞品位置使用统一的克制色彩，同时保留文字标签和短域名链接。
4. 重跑测试和构建。

## Task 8: 全量验证和文档同步

**Files:**
- Modify authoritative docs identified by `neat-freak`
- Append: `C:/Users/86173/.codex/work-logs/2026-W29.md`

1. 运行后端定向测试，再运行 `pytest backend/tests -q`。
2. 在 `frontend` 运行 `npm test` 和 `npm run build`。
3. 运行 `git diff --check` 并人工审查任务相关 diff，确认没有秘密、迁移或无关重构。
4. 使用 `neat-freak` 合并更新需求、实现状态、架构、部署、实测字段、总控、决策、README 和交接文档；不恢复已删除的过期文档。
5. 写工作日志，记录代码、测试、部署和剩余风险，不写凭据。

## Task 9: 生产数据修复和无中断滚动发布

**Files/Targets:**
- Production: `/opt/hengzhe-new-product/app`
- Production DB: existing production database
- Production URL: `http://101.132.26.138:8080`

1. 只读核对当前容器、数据库、上传文件和活动连接；创建数据库备份。
2. 从旧 API 容器复制源表到持久卷，核对文件数量和 SHA-256。
3. 在隔离环境用生产源表副本重导，确认仅补出 `BGQHG7801`、`BGQHG7901` 且保留历史认领/复核。
4. 部署新 API 绿色实例并等待健康；热重载 Caddy，把新请求切到绿色实例，旧实例保留已有连接。
5. 部署前端静态构建，不重启数据库。
6. 生产执行备份后的幂等重导，核对 BGQHG78/79 子 SKU、总数、认领和复核记录变化范围。
7. 冒烟验证登录、机会列表、运营任务、商品看板、提交认领和主管列表；不在生产执行并发压测。
8. 观察日志无 5xx、连接池耗尽和重复复核任务后，记录发布版本与回滚点。
