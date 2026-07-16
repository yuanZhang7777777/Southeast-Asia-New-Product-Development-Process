# 价格字段、主管复核与商品编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 正确导入并展示稳定期价格字段，提供同类型批量复核，并让主管审计式编辑商品业务参数和状态。

**Architecture:** 沿用选品 1 的两行表头映射、现有商品 PATCH 和复核状态机。商品原始 `SourceRecordSnapshot` 保持不变，主管修改写入当前商品快照与审计日志；批量复核在一个事务内复用单条复核服务。

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, Node test runner

## Global Constraints

- 不新增依赖。
- 不修改来源文件、Sheet、行号、导入批次和原始来源快照。
- 批量多选不得混合 `claim_submitted` 与 `claim_rejected`。
- 展示格式化不得修改数据库原始精度。

---

### Task 1: 本期价格字段映射

**Files:**
- Modify: `backend/app/selection1_importer.py`
- Modify: `backend/tests/test_selection1_import.py`
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests/selection1Columns.test.ts`

**Interfaces:**
- Consumes: 选品 1 两行表头和历史列位兜底。
- Produces: `pricing_snapshot["稳定期定价"]`、`pricing_snapshot["稳定期利润率"]`。

- [ ] **Step 1: 写入本期 AJ/AM 表头的失败测试**

```python
assert imported.snapshot["pricing_snapshot"]["稳定期定价"] == 428
assert imported.snapshot["pricing_snapshot"]["稳定期利润率"] == 0.0823262796879019
```

- [ ] **Step 2: 验证测试先失败**

Run: `pytest backend/tests/test_selection1_import.py -q`
Expected: 新断言因旧 AP/AS 兜底读错而失败。

- [ ] **Step 3: 增加精确表头别名并保留旧列兜底**

```python
"AP": ["稳定期定价", "稳定期定价 （PHP）", "参考定价"]
"AS": ["稳定期利润率", "一次毛利率"]
```

- [ ] **Step 4: 运行导入测试**

Run: `pytest backend/tests/test_selection1_import.py -q`
Expected: PASS。

### Task 2: 业务数字展示

**Files:**
- Create: `frontend/src/businessFormat.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/ProductBoardView.tsx`
- Create: `frontend/tests/businessFormat.test.ts`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces: `formatBusinessNumber(value)` 和 `formatBusinessValue(value, label)`。

- [ ] **Step 1: 写入小数和百分比失败测试**

```ts
assert.equal(formatBusinessValue(0.161309873307121, "稳定期利润率"), "16.13%")
assert.equal(formatBusinessValue(35.235647706422014, "价格"), "35.24")
assert.equal(formatBusinessNumber(2.8200000000000003), "2.82")
```

- [ ] **Step 2: 验证测试先失败**

Run: `npm test -- --test-name-pattern=业务数字`
Expected: 模块不存在或断言失败。

- [ ] **Step 3: 用 `Intl.NumberFormat` 实现并接入价格、月销、单销显示**

```ts
const decimal = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
```

- [ ] **Step 4: 运行前端测试和构建**

Run: `npm test && npm run build`
Expected: PASS。

### Task 3: 主管全参数与状态编辑

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services.py`
- Modify: `backend/tests/test_opportunity_edit.py`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Extends: `OpportunityUpdateRequest.current_status`。
- Extends: `OpportunityUpdateRequest.source_cells: dict[str, scalar]`。

- [ ] **Step 1: 写入状态、源参数和非法列失败测试**

```python
response = client.patch(f"/opportunities/{item.id}", json={
    "current_status": "pending_assignment",
    "source_cells": {"AJ": 428, "AM": 0.0823},
    "edit_reason": "修正导入参数",
}, headers=manager_headers)
assert response.status_code == 200
```

- [ ] **Step 2: 验证测试先失败**

Run: `pytest backend/tests/test_opportunity_edit.py -q`
Expected: 请求字段被 Pydantic 拒绝。

- [ ] **Step 3: 扩展现有 PATCH 并同步当前快照**

```python
snapshot["cells"][column] = value
snapshot["fields_by_column"][column] = value
```

同时按 `headers_by_column` 更新 `fields_by_header`，保留原始 `SourceRecordSnapshot`，并写现有审计日志。

- [ ] **Step 4: 在当前主管编辑面板增加状态和原生折叠参数区**

使用已有表头/列号生成输入框，只发送发生变化的列。

- [ ] **Step 5: 运行编辑测试和构建**

Run: `pytest backend/tests/test_opportunity_edit.py -q && npm run build`
Expected: PASS。

### Task 4: 同类型批量复核

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/reviews.py`
- Modify: `backend/app/services.py`
- Modify: `backend/tests/test_review_flow.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/tests/reviewLayout.test.ts`

**Interfaces:**
- Adds: `POST /reviews/bulk`，请求 `opportunity_ids`, `action`, `review_comment`。
- Produces: 同状态列表一次事务提交的复核结果。

- [ ] **Step 1: 写入批量通过、退回和混合类型拒绝测试**

```python
assert client.post("/reviews/bulk", json=claim_payload, headers=manager_headers).status_code == 200
assert client.post("/reviews/bulk", json=mixed_payload, headers=manager_headers).status_code == 400
```

- [ ] **Step 2: 验证测试先失败**

Run: `pytest backend/tests/test_review_flow.py -q`
Expected: `/reviews/bulk` 返回 404。

- [ ] **Step 3: 复用 `submit_review` 实现单事务批量接口**

通过动作按所选状态映射到 `approved` 或 `confirmed_not_claim`；拒绝映射到 `returned_for_supplement` 并要求原因。

- [ ] **Step 4: 增加两段筛选、全选、批量通过和批量拒绝**

切换筛选时清空选择，后端仍校验同类型。

- [ ] **Step 5: 运行全量验证并检查差异**

Run: `pytest backend/tests -q && npm test && npm run build && git diff --check`
Expected: 全部通过，无空白错误。
