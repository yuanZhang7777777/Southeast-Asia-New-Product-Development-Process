# 刊登与观察工作台 UI 实施计划

> 日期：2026-07-21
>
> 依据：`docs/superpowers/specs/2026-07-21-listing-observation-workbench-ui-design.md`
> 范围：开发环境；不新增业务状态、数据表或抓数规则，不连接、部署或重启生产环境

## 验收路径

- 前端单元与源码契约测试：`npm test`
- 前端类型检查与构建：`npm run build`
- 后端聚焦测试：`python -m pytest backend/tests/test_secondary_research.py -q`
- 后端全量回归：`python -m pytest backend/tests -q`
- 开发环境冒烟：健康检查、登录、刊登观察工作台、商品详情二次调研与刊登观察只读历史

## 任务 1：锁定周期可见性规则

**文件**

- 修改：`frontend/src/listingObservation.ts`
- 修改：`frontend/tests/listingObservation.test.ts`

**步骤**

1. 先增加失败测试，覆盖未来周期隐藏、当前周期进行中、已结束待取数、已取数可复盘和结束后次日预计取数日期。
2. 增加最小纯函数返回周期展示类型和预计取数日期。
3. 运行 `node --test tests/listingObservation.test.ts`，确认测试通过。

## 任务 2：重构刊登与观察工作台

**文件**

- 修改：`frontend/src/ListingObservationView.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`frontend/tests/listingObservation.test.ts`

**步骤**

1. 先增加源码契约测试，锁定批量按钮文案、主 SKU 完整折叠、当前周期提示和不再使用 1900px 宽表。
2. 将标题、筛选、结果数量与批量提交放入固定区，下方结果区独立纵向滚动。
3. 将结果改为“主 SKU 组 → Item 卡片 → 周记录”；主 SKU 收起时不渲染 Item、表单或周记录。
4. Item 的纠错、停止/恢复和作废收进“更多”菜单；新增时自动展开该组。
5. 未来周期不渲染；当前周期显示预计取数提示；数据入库后才渲染定位、优化操作和四周总结表单。
6. 删除常驻的重复“已有刊登记录”区和说明；保留现有原子提交、校验和编辑能力。

## 任务 3：补齐商品详情后段只读历史

**文件**

- 修改：`frontend/src/api.ts`
- 新增：`frontend/src/SecondaryResearchSummary.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/ListingObservationView.tsx`
- 修改：`frontend/src/styles.css`
- 修改：`frontend/tests/productDetailNavigation.test.ts`
- 修改：`backend/app/routers/secondary_research.py`
- 修改：`backend/tests/test_secondary_research.py`

**步骤**

1. 先增加测试，锁定商品详情存在“二次调研”和“刊登与观察”两个只读入口，以及主管可查询全部运营历史、普通运营仍只能读取本人记录。
2. 复用现有二次调研查询接口，增加可选下游状态参数；不复制数据，不新建汇总接口。
3. 商品详情按主 SKU、国家和来源业务期展示已提交二次调研；刊登观察汇总改成自适应 Item/周期卡片并遵循相同周期可见性规则。
4. 运行聚焦前后端测试。

## 任务 4：回归、开发部署与文档收口

**文件**

- 按实际完成情况更新：`docs/02-功能实现状态.md`
- 按实际完成情况更新：`docs/20-项目推进总控.md`
- 按实际完成情况更新：`docs/AGENT_HANDOFF.md`
- 追加：`C:\Users\86173\.codex\work-logs\2026-W30.md`

**步骤**

1. 运行前端全量测试与构建、后端聚焦测试与全量回归，审查 `git diff`。
2. 运行 `neat-freak` 文档影响检查，只更新受本次实现影响的权威文档，不删除或合并候选文档。
3. 提交代码与文档；仅在开发服务器重建 API 和前端服务。
4. 验证开发服务健康、容器状态、版本标记和关键页面；确认生产环境没有被连接或改动。
