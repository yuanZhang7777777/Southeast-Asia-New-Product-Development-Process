# 运营认领 UAT 易用性修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans with test-driven development. This worktree is already isolated; do not create another worktree or delegate without user instruction.
>
> **执行结果：** `f26eae8` 完成四项修复，`24f601f` 补强 Esc 关闭；99 个前端测试、生产构建和开发环境真实浏览器冒烟通过。

**Goal:** 修复开发 UAT 暴露的四个认领/导出界面问题，并仅部署开发环境继续二次调研及后半段验收。

**Architecture:** 保留现有认领、复核和导出数据流，只调整 `App.tsx` 结构与 `styles.css` 布局。原因选择器继续复用现有字符串解析函数，使用定制样式原生 `<dialog>` 承载临时选择；不增加依赖、接口或数据库迁移。

**Tech Stack:** React 19、TypeScript、原生 `<dialog>`、CSS、Node test runner、Vite、Docker Compose。

## Global Constraints

- 只修改 `lxc/integrated-workflow` 和开发环境 `139.224.2.166:18081`。
- 不连接、不读取、不部署、不重启生产服务器 `101.132.26.138`。
- 不改变主管复核后的回改权限，不改变导出、到货、二次调研或刊登状态机。
- 不新增 UI 依赖、后端接口、数据库字段或迁移。

---

### Task 1: 用失败测试锁定四项界面行为

**Files:**
- Modify: `frontend/tests/claimDrafts.test.ts`
- Modify: `frontend/tests/reviewLayout.test.ts`

1. 更新原因选择器源码契约：两个入口继续复用同一组件；组件使用 `<dialog>`、`showModal()`、完成/取消/关闭；旧 `<details>` 与 `:has(...[open])` 扩展规则必须消失。
2. 更新详情矩阵状态契约：普通列表编辑器保留 `ClaimSubmissionBadge`，矩阵编辑器不再渲染该标签，顶部仍统计 `dirtyCount`。
3. 增加组导航契约：`ClaimMatrixTable` 后存在 `claim-group-nav-row`，上一组和下一组按钮位于该行内；CSS 不再绝对定位。
4. 增加导出中心契约：源码不再包含“查看明细”，业务期数仍调用 `viewPeriod(period.business_period)` 切换明细。
5. 运行 `node --test tests/claimDrafts.test.ts tests/reviewLayout.test.ts`，确认测试因旧实现失败。

---

### Task 2: 实现最小前端修复

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

1. 在导出期数表中删除“查看明细”，将业务期数单元格改为可点击期数按钮，保留默认最新期和其他期切换。
2. 从 `ClaimMatrixDraftEditor` 移除逐行 `ClaimSubmissionBadge`；普通认领列表不变。
3. 将上一组/下一组移到 `ClaimMatrixTable` 下方正常文档流导航行，删除侧边绝对定位和多余左右内边距。
4. 将 `RejectReasonPicker` 改为定制样式 `<dialog>`：打开时复制现值到临时状态，完成时提交，取消/关闭/遮罩/Esc 放弃未确认变化。
5. 保留固定原因、多选、自定义文本、组内同步和现有 `reject_reason` 格式。
6. 运行聚焦测试，确认转绿。

---

### Task 3: 完整验证、文档与提交

**Files:**
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/10-前端UX与功能测试验收清单.md`（仅在实现与确认设计存在偏差时）
- Modify: `docs/20-项目推进总控.md`
- Modify: `AGENT_HANDOFF.md`

1. 运行：
   - `node --test tests/claimDrafts.test.ts tests/reviewLayout.test.ts`
   - `npm test`
   - `npm run build`
   - `git diff --check`
2. 对照设计验收标准逐项审查 diff；不修改无关代码。
3. 更新实现状态、实际测试数和“尚未部署”状态。
4. 提交前端、测试和文档，提交信息使用 `fix: improve claim UAT usability`。

---

### Task 4: 仅部署开发环境并继续 UAT

**Targets:**
- SSH alias: `hz-new-product-dev`
- App path: `/opt/hengzhe-new-product-dev/app`
- Public URL: `http://139.224.2.166:18081`

1. 确认 SSH 别名解析为开发服务器，并检查开发 Compose 项目和当前提交；不得使用生产地址。
2. 备份开发应用目录或保留当前 `48b3639` 前端回滚镜像/包。
3. 上传已验证提交，仅重建并替换开发 `frontend` 容器；不重启 API、worker、scheduler、PostgreSQL、Redis 或 reverse-proxy。
4. 验证服务器内外 `/api/health` 返回 `status=ok`、`environment=development`；验证首页和新静态资源 200。
5. 浏览器冒烟验证四项交互，并记录开发部署提交。
6. 使用现有 UAT 数据继续：
   - GZMO078：验证主管复核前修改并重新提交。
   - GZMO075/076/079：从待到货继续验证 PLM 到货、二次调研、刊登及 Item 独立周期观察。
7. 更新部署与交接文档、工作日志；不修改生产。
