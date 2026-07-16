# Assignment Workbench Compact Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将分配台改为紧凑单屏工作台，同时保留现有推荐、筛选、配置和提交能力。

**Architecture:** 复用 `AssignView`、`ListControls`、现有人员配置表和 API，只调整 React 组合结构与 CSS。新增的状态仅为运营配置抽屉开关，不改后端接口、数据库或分配算法。

**Tech Stack:** React 19、TypeScript、CSS、Node test runner、Vite。

## Global Constraints

- 与运营认领提交状态、历史图片恢复和选品1来源隔离改动一起发布。
- 不新增依赖，不改分配算法和权限。
- 桌面宽屏保持紧凑单行；窄屏允许自然换行且不能溢出。
- 运营配置必须由按钮打开，关闭不自动保存。

---

### Task 1: 布局验收测试

**Files:**
- Modify: `frontend/tests/reviewLayout.test.ts`
- Modify: `frontend/tests/assignmentFilters.test.ts`

**Interfaces:**
- Consumes: `frontend/src/App.tsx` 和 `frontend/src/styles.css`。
- Produces: 合并导航、配置抽屉、单列指标和运营卡片紧凑展示的回归约束。

- [ ] **Step 1: 写失败测试**

断言源码包含 `assignment-commandbar`、`assignment-config-drawer`、`priority-badge`，运营卡不再调用拼接站点和优先级的 `operatorProfileBrief`；断言 `.side .metrics` 为单列。

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test`

Expected: FAIL，因为新布局类名和抽屉结构尚不存在。

- [ ] **Step 3: 提交测试**

Run: `git add frontend/tests && git commit -m "test: define compact assignment workbench"`

### Task 2: 分配台结构与交互

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `profilePanelOpen: boolean`、合并导航、紧凑命令栏、配置抽屉和优先级徽标。

- [ ] **Step 1: 合并顶部导航**

将 `hub` 和 `flow` 合并为一个 `workflow-nav`，保留全部按钮、箭头和测试阶段提示。

- [ ] **Step 2: 重排分配命令栏**

将标题、统计、筛选、清空和 `ListControls` 放入一个 `assignment-commandbar`，增加带 `Users` 图标的“运营配置”按钮。

- [ ] **Step 3: 将配置表移入抽屉**

使用现有配置表 JSX，外层改为 `assignment-config-overlay` 和 `assignment-config-drawer`；关闭按钮只关闭面板，保存按钮调用现有 `onSaveProfiles`。

- [ ] **Step 4: 压缩运营负载卡**

优先级大于 0 时在姓名前显示 `优先 N` 徽标；站点只保留右侧标签；两个品类改为带 `title` 的短标签。

- [ ] **Step 5: 运行测试确认通过**

Run: `npm test`

Expected: PASS。

### Task 3: 响应式样式

**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 2 新增的类名。
- Produces: 约 `170px` 统计栏、单列指标、桌面单行命令栏、紧凑运营卡和响应式配置抽屉。

- [ ] **Step 1: 添加桌面样式**

设置 `.layout` 右栏宽度、`.side .metrics` 单列、`.assignment-commandbar` 横向布局、`.operator-category-tags` 省略和抽屉遮罩层。

- [ ] **Step 2: 添加窄屏回退**

在现有 `1180px` / 移动端媒体查询中让命令栏换行、抽屉全宽、导航保持横向滚动。

- [ ] **Step 3: 运行生产构建**

Run: `npm run build`

Expected: TypeScript 和 Vite 构建成功。

### Task 4: 文档、回归和发布

**Files:**
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/06-部署与服务器准备.md`
- Append: `C:/Users/86173/.codex/work-logs/2026-W29.md`

**Interfaces:**
- Produces: 与代码、生产容器版本一致的交接记录。

- [ ] **Step 1: 更新功能状态**

记录分配台紧凑工具栏、单列主管指标、配置抽屉和运营卡片去重展示。

- [ ] **Step 2: 运行完整验证**

Run: `npm test && npm run build`

Run: `python -m pytest -q`

Expected: 全部通过；若后端全量超时，拆分测试文件执行并汇总结果。

- [ ] **Step 3: 提交并推送**

只提交本轮代码、测试和文档，不包含环境文件或构建产物。

- [ ] **Step 4: 滚动发布**

构建候选 API 和前端容器，先健康检查，再原子切换 Caddy；不重启 PostgreSQL、Redis、worker 或 scheduler。

- [ ] **Step 5: 生产验证**

确认外部 `/api/health`、登录页、静态资源哈希、容器状态和 Caddy 持久配置均指向新版本。
