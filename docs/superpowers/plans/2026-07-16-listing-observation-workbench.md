# 刊登与观察工作台实施计划

> 实施方式：按 TDD 小步完成；后端和前端可并行，主线程负责契约、迁移、整合和验证。

**目标：** 在现有二次调研之后交付可用的刊登与观察工作台，并删除无数据的旧四周总结实现。

**架构：** 复用现有 FastAPI、SQLAlchemy、React 和原生 Node 测试模式。新增 `listing_record` 与 `item_observation_period` 两表；待刊登任务继续从现有责任记录派生，不增加任务表。前端新增一个独立 View 和一个纯函数 helper，不引入路由、状态库、表格组件或新依赖。

**技术栈：** Python 3、FastAPI、SQLAlchemy、Alembic、pytest、React、TypeScript、Vite、node:test。

## 任务 1：修正二次调研五种定位分流

**文件：**

- 修改 `backend/tests/test_secondary_research.py`
- 修改 `backend/app/schemas.py`
- 修改 `backend/app/services.py`
- 修改 `frontend/src/secondaryResearchDrafts.ts`
- 修改 `frontend/src/SecondaryResearchView.tsx`
- 修改对应前端测试

**步骤：**

1. 先增加失败测试：稳定款可提交并进入 `waiting_listing`，清仓款可提交并进入 `disabled`，淘汰款仍进入 `disabled`。
2. 运行相关后端 / 前端测试确认失败。
3. 将定位集合统一扩为五种，明确三种进入刊登、两种跳过刊登。
4. 运行相关测试确认通过。

## 任务 2：建立新表并删除旧四周总结

**文件：**

- 修改 `backend/app/models.py`
- 新增 `backend/alembic/versions/<revision>_add_listing_observation.py`
- 删除 `backend/app/routers/summary.py`
- 修改 `backend/app/main.py`
- 修改 `backend/app/schemas.py`
- 修改 `backend/tests/test_auth.py`

**步骤：**

1. 增加模型和迁移验收测试 / 断言，覆盖新表约束与旧路由消失。
2. 新增 `ListingRecord`、`ItemObservationPeriod`，Item 使用数据库全局唯一约束。
3. 新迁移创建两表并删除 `four_week_summary`；降级反向恢复旧空表。
4. 删除旧模型、Schema、路由注册和前端 `api.summary`。
5. 运行模型、鉴权和迁移相关测试。

## 任务 3：实现后端刊登与周期服务

**文件：**

- 新增 `backend/tests/test_listing_observations.py`
- 新增 `backend/app/routers/listing_workbench.py`
- 修改 `backend/app/main.py`
- 修改 `backend/app/schemas.py`
- 修改 `backend/app/services.py`
- 修改 `backend/app/workflow_status.py`

**步骤：**

1. 先写周期纯函数测试：周四至周三、当前 / 下一周期限制、首轮四周日期。
2. 写批量创建失败测试：漏填、批内重复、库内重复、越权均零落库并返回行级错误。
3. 写批量创建成功测试：同一主 SKU 多条“店铺 + Item”，每条生成独立四周。
4. 写低频跨期兜底测试：同一主 SKU、国家 / 站点和负责人在新业务期重现时沿用已有 Item，不复制记录，仍可新增新店铺和 Item。
5. 写列表与权限测试：运营强制本人、主管查看全部并筛选。
6. 写周期复盘测试：定位和优化必填，第 4 周总结必填，整批原子。
7. 写定位与跟踪解耦回归：第 N 周提交淘汰款后 Item 仍正常跟踪，第 N+1 周继续取数和复盘并可改回其他定位；第 4 周淘汰款仍要求总结。
8. 写淘汰提醒状态变化回归：利润款 -> 淘汰款 -> 淘汰款 -> 稳定款 -> 淘汰款只生成两次主管提醒事件，失败可重试、成功不重复。
9. 写停止 / 恢复、首轮完成和手动新增后续周期测试。
10. 最小实现 Schemas、服务和路由，所有 actor 从认证上下文取得并写 AuditLog。
11. 运行 `pytest backend/tests/test_listing_observations.py -q`。

## 任务 4：实现周 Item 数据落库边界

**文件：**

- 修改 `backend/tests/test_listing_observations.py`
- 修改 `backend/app/services.py`

**步骤：**

1. 先写失败测试：无源记录保持待取数，真实零进入待复盘，非零毛利率计算正确。
2. 实现 `apply_week_metrics`，按 Item + 周期更新唯一记录并保留来源追溯。
3. 复用 NotificationLog 去重键预留数据入库后的运营提醒，不创建猜测性接口配置。
4. 运行相关测试。

## 任务 5：实现前端纯逻辑与 API 契约

**文件：**

- 新增 `frontend/src/listingObservation.ts`
- 新增 `frontend/tests/listingObservation.test.ts`
- 修改 `frontend/src/api.ts`
- 修改 `frontend/package.json`

**步骤：**

1. 先写失败测试：四个刊登必填、trim 后批内重复、组合筛选、百分比格式、无数据与真实 0、服务端行错误映射。
2. 实现最小纯函数 helper。
3. 增加工作台类型和单请求批量 API；不复制 fetch 封装。
4. 运行 `npm test`。

## 任务 6：实现工作台页面

**文件：**

- 新增 `frontend/src/ListingObservationView.tsx`
- 修改 `frontend/src/App.tsx`
- 修改 `frontend/src/styles.css`

**步骤：**

1. 在 App 的现有 `ViewKey` 导航中增加 `listing`，不引入 React Router。
2. 实现待刊登主 SKU 行内多条新增和一次批量提交。
3. 实现待取数、待复盘、首轮观察完成、全部分栏和常用 / 高级筛选。
4. 实现原生横向 table、sticky 关键列、同主 SKU 分组、表内定位 / 优化编辑。
5. 第 4 周使用现有 overlay 样式填写总结；不增加 UI 依赖。
6. 运行 `npm test` 与 `npm run build`。

## 任务 7：商品详情只读汇总

**文件：**

- 修改 `frontend/src/App.tsx` 中现有 `ProductDetailView`
- 修改 `frontend/src/api.ts`
- 修改后端工作台汇总接口和测试

**步骤：**

1. 增加按主 SKU、国家、负责人读取全部刊登 / 周期历史的后端测试，并断言响应透出刊登记录已保存的来源业务期。
2. 在商品详情增加只读区，复用工作台响应类型和格式化函数；按来源业务期分组、默认展开当前业务期，不建设第二套编辑器。
3. 增加跨业务期不混组的前端窄测试，再运行相关后端测试和前端构建。

## 任务 8：完整验证、文档与开发环境部署

**步骤：**

1. 运行新增窄测试，再运行完整 `pytest -q`、`npm test`、`npm run build`。
2. 运行 Alembic 在一次性开发测试库执行 `upgrade head`，确认新表存在、旧表不存在。
3. 复查 `git diff --check`、敏感信息和 `.env` 未提交。
4. 使用 neat-freak 更新需求、架构、功能状态和交接文档。
5. 仅部署到新开发服务器 `139.224.2.166:18081`，验证健康检查和工作台；不得连接或重启 `101.132.26.138`。
