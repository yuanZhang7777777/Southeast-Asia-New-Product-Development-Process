# 前后半段统一开发分支设计

日期：2026-07-17
状态：用户已确认，待执行

## 1. 目标

把生产前半段代码线 `lxc/pricing-review-edit@fbf574c` 与后半段代码线 `lxc/listing-observation-workbench` 合并为唯一后续开发分支 `lxc/integrated-workflow`。合并完成后只更新开发环境 `139.224.2.166:18081`，不连接、不重启、不部署生产服务器 `101.132.26.138`。

## 2. 已核实基线

- 两条分支共同基点为 `8d40d11`。
- 前半段分支在共同基点后有 43 个提交，HEAD 为 `fbf574c`；生产实际运行提交为 `b373d65`，其后的重复导出功能尚未部署。
- 后半段分支在共同基点后有 50 个提交；本设计提交前 HEAD 为 `5c73719`，开发环境运行代码提交为 `83c6460`。
- 两个工作树均干净；`lxc/pricing-review-edit` 有 12 个本地提交尚未推送。

## 3. 合并方式

从 `fbf574c` 创建 `lxc/integrated-workflow`，使用普通非快进合并把完整后半段分支接入。保留两条历史，不逐个 cherry-pick，不重写旧提交，也不删除旧分支。

合并后：

- `lxc/integrated-workflow` 是唯一后续开发基线。
- `lxc/pricing-review-edit` 与 `lxc/listing-observation-workbench` 冻结保留，只作追溯和回滚参考。
- `main` 暂不移动；生产发布仍需单独批准和维护窗口。

## 4. 冲突处理原则

已探测到 5 个文本冲突：

- `AGENT_HANDOFF.md`
- `docs/02-功能实现状态.md`
- `docs/06-部署与服务器准备.md`
- `frontend/package.json`
- `frontend/src/App.tsx`

处理规则：

1. 前半段现有功能以 `lxc/pricing-review-edit` 为准，保留分配、认领、主管复核、分期重复导出和生产运行事实。
2. 后半段新增功能以 `lxc/listing-observation-workbench` 为准，保留二次调研、刊登与观察工作台、周指标、周期复盘和商品详情汇总。
3. `frontend/package.json` 合并两边现有测试文件，不新增依赖。
4. `frontend/src/App.tsx` 同时保留前半段导航/页面与“刊登与观察”入口；复用现有角色与运营范围状态，不创建第二套路由或鉴权。
5. 部署文档同时写清生产实际版本 `b373d65`、统一分支未部署生产，以及开发环境的最终统一版本，禁止把开发部署写成生产上线。

即使 Git 自动合并成功，也必须人工审查共享热点：`backend/app/services.py`、`backend/app/schemas.py`、`frontend/src/api.ts`、`frontend/src/styles.css`、商品看板和二次调研文件，防止语义冲突。

## 5. 验收标准

- Git 合并提交同时包含 `fbf574c` 与后半段最终文档提交两个父系历史。
- 后端全量测试、前端全量测试、TypeScript/Vite 构建和 `git diff --check` 全部通过。
- Alembic 只有一个当前 head，开发数据库可升级到该 head。
- 前半段测试数量不因合并丢失，后半段刊登与观察测试也继续执行。
- 开发环境首页与 `/api/health` 可访问，运行统一提交；生产环境未连接、未改变。
- 权威功能状态、部署说明、文档索引和交接记录与合并后的代码一致。
