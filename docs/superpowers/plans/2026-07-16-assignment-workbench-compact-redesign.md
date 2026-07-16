# Assignment Workbench Compact Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将分配台改为紧凑单屏工作台，同时保留现有推荐、筛选、配置和提交能力。

**Architecture:** 复用 `AssignView`、`ListControls`、现有人员配置表和 API，只调整 React 组合结构、同站点排序辅助函数与 CSS。新增状态仅用于配置抽屉和拖拽中的临时标识，不改后端接口、数据库或分配算法。

**Tech Stack:** React 19、TypeScript、CSS、Node test runner、Vite。

## Global Constraints

- 与运营认领提交状态、历史图片恢复和选品1来源隔离改动一起发布。
- 不新增依赖，不改分配算法和权限。
- 桌面宽屏保持紧凑单行；窄屏允许自然换行且不能溢出。
- 运营配置必须由按钮打开，关闭不自动保存。
- 配置入口不能被搜索或分页挤出；下滚分配列表时必须持续看到实时运营负载。

---

### Task 1: 布局验收测试

**Files:**
- Modify: `frontend/tests/reviewLayout.test.ts`
- Modify: `frontend/tests/assignmentFilters.test.ts`

**Interfaces:**
- Consumes: `frontend/src/App.tsx` 和 `frontend/src/styles.css`。
- Produces: 合并导航、配置抽屉、单列指标和运营卡片紧凑展示的回归约束。

- [x] **Step 1: 写失败测试**

断言源码包含 `assignment-commandbar`、`assignment-config-drawer`、`priority-badge`，运营卡不再调用拼接站点和优先级的 `operatorProfileBrief`；断言 `.side .metrics` 为单列。

- [x] **Step 2: 运行测试确认失败**

Run: `npm test`

Expected: FAIL，因为新布局类名和抽屉结构尚不存在。

- [x] **Step 3: 提交测试**

Run: `git add frontend/tests && git commit -m "test: define compact assignment workbench"`

### Task 2: 分配台结构与交互

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `profilePanelOpen: boolean`、合并导航、紧凑命令栏、配置抽屉和优先级徽标。

- [x] **Step 1: 合并顶部导航**

将 `hub` 和 `flow` 合并为一个 `workflow-nav`，保留全部按钮、箭头和测试阶段提示。

- [x] **Step 2: 重排分配命令栏**

将标题、统计、筛选、清空和 `ListControls` 放入一个 `assignment-commandbar`，增加带 `Users` 图标的“运营配置”按钮。

- [x] **Step 3: 将配置表移入抽屉**

使用现有配置表 JSX，外层改为 `assignment-config-overlay` 和 `assignment-config-drawer`；关闭按钮只关闭面板，保存按钮调用现有 `onSaveProfiles`。

- [x] **Step 4: 压缩运营负载卡**

优先级大于 0 时在姓名前显示 `优先 N` 徽标；站点只保留右侧标签；两个品类改为带 `title` 的短标签。

- [x] **Step 5: 运行测试确认通过**

Run: `npm test`

Expected: PASS。

### Task 3: 响应式样式

**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 2 新增的类名。
- Produces: 约 `170px` 统计栏、单列指标、桌面单行命令栏、紧凑运营卡和响应式配置抽屉。

- [x] **Step 1: 添加桌面样式**

设置 `.layout` 右栏宽度、`.side .metrics` 单列、`.assignment-commandbar` 横向布局、`.operator-category-tags` 省略和抽屉遮罩层。

- [x] **Step 2: 添加窄屏回退**

在现有 `1180px` / 移动端媒体查询中让命令栏换行、抽屉全宽、导航保持横向滚动。

- [x] **Step 3: 运行生产构建**

Run: `npm run build`

Expected: TypeScript 和 Vite 构建成功。

### Task 4: 文档、回归和发布

**Files:**
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/06-部署与服务器准备.md`
- Append: `C:/Users/86173/.codex/work-logs/2026-W29.md`

**Interfaces:**
- Produces: 与代码、生产容器版本一致的交接记录。

- [x] **Step 1: 更新功能状态**

记录分配台紧凑工具栏、单列主管指标、配置抽屉和运营卡片去重展示。

- [x] **Step 2: 运行完整验证**

Run: `npm test && npm run build`

Run: `python -m pytest -q`

Expected: 全部通过；若后端全量超时，拆分测试文件执行并汇总结果。

- [x] **Step 3: 提交并推送**

只提交本轮代码、测试和文档，不包含环境文件或构建产物。

- [x] **Step 4: 滚动发布**

构建候选 API 和前端容器，先健康检查，再原子切换 Caddy；不重启 PostgreSQL、Redis、worker 或 scheduler。

- [x] **Step 5: 生产验证**

确认外部 `/api/health`、登录页、静态资源哈希、容器状态和 Caddy 持久配置均指向新版本。

### Task 5: 配置入口、拖拽排序与吸顶负载跟进

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/assignmentFilters.ts`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/tests/assignmentFilters.test.ts`
- Modify: `frontend/tests/reviewLayout.test.ts`

- [x] **Step 1: 先补失败测试**

约束配置入口必须位于 `ListControls` 之前；负载容器必须吸顶、单行并内部横向滚动；同站点拖拽必须改变 `display_order`，跨站点拖拽必须保持原样。

- [x] **Step 2: 调整命令栏与运营负载**

把配置入口移到伸缩搜索和分页之前；命令栏按实际空间换行；负载卡改为吸顶横条并继续使用现有实时预览计数。

- [x] **Step 3: 增加同站点拖拽排序**

使用浏览器原生拖拽事件和现有 `display_order` 字段，不新增依赖；保留上下按钮作为键盘和兼容回退。

- [x] **Step 4: 完整验证**

`npm test` 通过 41 项，`npm run build` 通过；Playwright/Edge 验证 2048px、1366px、390px，无页面横向溢出，吸顶位置正确，分配计数即时变化，真实鼠标拖拽可调整同站点顺序。
