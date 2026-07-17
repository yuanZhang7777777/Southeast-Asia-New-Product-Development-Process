# 前后半段统一开发分支 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 合并生产前半段与刊登观察后半段代码线，形成唯一开发分支并只部署到 `139.224.2.166:18081`。

**Architecture:** 从前半段完整 HEAD `fbf574c` 建立 `lxc/integrated-workflow`，非快进合并后半段分支，人工处理 5 个文本冲突并审查自动合并热点。复用现有 FastAPI、SQLAlchemy、React、Docker Compose 和部署方式，不新增依赖或兼容层。

**Tech Stack:** Git、Python 3、FastAPI、SQLAlchemy、Alembic、pytest、React、TypeScript、Vite、Docker Compose。

## Global Constraints

- [ ] 不连接、不修改、不重启、不部署生产服务器 `101.132.26.138`。
- [ ] 不提交密码、Token、SSH 私钥、`.env` 或生产数据。
- [ ] 不删除或重写两条源分支；合并后冻结保留。
- [ ] 不增加依赖、数据库表或业务行为；本任务只整合两边已经完成的能力。
- [ ] 最终只部署开发环境 `139.224.2.166:18081`。

---

### Task 1: 固化源分支并建立统一分支

**Files:**

- Modify: `docs/superpowers/specs/2026-07-17-unified-development-branch-design.md`
- Modify: `docs/superpowers/plans/2026-07-17-unified-development-branch.md`

**Interfaces:**

- Consumes: `lxc/pricing-review-edit@fbf574c`、`lxc/listing-observation-workbench` 当前 HEAD。
- Produces: `lxc/integrated-workflow`。

- [ ] **Step 1: 确认两个工作树干净且提交指针未漂移**

  ```powershell
  git -C E:\Project\Hengzhe-New-Product-Workflow\.worktrees\pricing-review-edit status --short --branch
  git status --short --branch
  git rev-parse lxc/pricing-review-edit lxc/listing-observation-workbench
  ```

- [ ] **Step 2: 在现有隔离工作树切换到统一分支**

  ```powershell
  git switch -c lxc/integrated-workflow lxc/pricing-review-edit
  ```

- [ ] **Step 3: 非快进合并完整后半段历史**

  ```powershell
  git merge --no-ff lxc/listing-observation-workbench
  ```

  预期：只出现设计中列出的文本冲突；不得使用 `ours` 或 `theirs` 整文件覆盖。

### Task 2: 解决冲突并审查自动合并热点

**Files:**

- Modify: `AGENT_HANDOFF.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/06-部署与服务器准备.md`
- Modify: `frontend/package.json`
- Modify: `frontend/src/App.tsx`
- Review: `backend/app/services.py`
- Review: `backend/app/schemas.py`
- Review: `frontend/src/api.ts`
- Review: `frontend/src/styles.css`
- Review: `frontend/src/ProductBoardView.tsx`
- Review: `frontend/src/SecondaryResearchView.tsx`

**Interfaces:**

- Consumes: 两边既有 API、页面入口、测试脚本和部署事实。
- Produces: 同时可运行的前半段与后半段应用，不改变任何现有接口契约。

- [ ] **Step 1: 按设计逐块解决 5 个文本冲突**

  ```powershell
  git diff --name-only --diff-filter=U
  rg -n "^(<<<<<<<|=======|>>>>>>>)" AGENT_HANDOFF.md docs frontend
  ```

- [ ] **Step 2: 审查自动合并共享文件的两侧差异**

  ```powershell
  git diff 8d40d11..lxc/pricing-review-edit -- backend/app/services.py backend/app/schemas.py frontend/src/api.ts frontend/src/styles.css
  git diff 8d40d11..lxc/listing-observation-workbench -- backend/app/services.py backend/app/schemas.py frontend/src/api.ts frontend/src/styles.css
  ```

- [ ] **Step 3: 确认无冲突标记并完成合并提交**

  ```powershell
  rg -n "^(<<<<<<<|=======|>>>>>>>)" . -g '!frontend/node_modules/**'
  git diff --check
  git add AGENT_HANDOFF.md README.md backend docs frontend
  git commit
  ```

### Task 3: 验证统一代码与迁移链

**Files:**

- Test: `backend/tests/`
- Test: `frontend/tests/`
- Verify: `backend/alembic/versions/`

**Interfaces:**

- Consumes: 合并后的完整应用。
- Produces: 可部署的统一提交和可重复验证证据。

- [ ] **Step 1: 验证 Alembic 单一 head**

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m alembic -c backend\alembic.ini heads
  ```

- [ ] **Step 2: 运行后端全量测试**

  ```powershell
  & 'E:\Project\Hengzhe-New-Product-Workflow\.venv\Scripts\python.exe' -m pytest backend\tests -q
  ```

- [ ] **Step 3: 运行前端全量测试与构建**

  ```powershell
  npm --prefix frontend test
  npm --prefix frontend run build
  ```

- [ ] **Step 4: 检查工作树和合并父提交**

  ```powershell
  git diff --check
  git status --short
  git show -s --format='%H%n%P%n%s' HEAD
  ```

### Task 4: 文档收口并部署开发环境

**Files:**

- Modify: `AGENT_HANDOFF.md`
- Modify: `README.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/06-部署与服务器准备.md`
- Modify: `docs/20-项目推进总控.md`
- Modify: `docs/README.md`
- Append: `C:\Users\86173\.codex\work-logs\2026-29.md`

**Interfaces:**

- Consumes: 最终统一提交、验证结果和开发部署结果。
- Produces: 开发环境可访问版本及与代码一致的权威交接资料。

- [ ] **Step 1: 运行 neat-freak 影响检查并更新现役文档**

  只更新当前事实，不删除历史规格；生产版本继续记录为 `b373d65`，统一版本明确标注为“仅开发环境”。

- [ ] **Step 2: 提交文档并重新执行完成证据门**

  ```powershell
  git add AGENT_HANDOFF.md README.md docs
  git commit -m "docs: record unified development baseline"
  git diff --check
  git status --short --branch
  ```

- [ ] **Step 3: 使用现有开发部署方式发布统一提交**

  发布前核对目标 SSH 别名解析为 `139.224.2.166:2323`；只操作开发服务和开发数据库，运行迁移、候选健康检查和端口 `18081` 外网检查。

- [ ] **Step 4: 回读开发版本并记录工作日志**

  验证 `http://139.224.2.166:18081/api/health`、首页静态资源和运行提交；记录锁、文件、命令、日志和验证结果，不记录秘密。
