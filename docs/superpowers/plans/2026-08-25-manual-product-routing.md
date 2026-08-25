# Manual Product Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing manual secondary-research entry into a multi-child SKU form that stores the requested research fields and routes the whole group into the existing secondary, initial-stocking, or listing flow.

**Architecture:** Keep the existing `/secondary-research/manual` boundary and `manual_secondary` source namespace. Add a nested request contract, reuse `NewProductOpportunity`, `MarketResearchItem`, `SalesClaimForecast`, `StockingRequest`, and existing workflow statuses, and store a selection1-compatible JSON snapshot for display/export traceability. Keep frontend form normalization and validation in one focused pure module, while `SecondaryResearchView.tsx` only owns React state and rendering.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, pytest, React, TypeScript, Node test runner, Vite.

**Spec:** `docs/superpowers/specs/2026-08-25-manual-product-routing-design.md`

## Global Constraints

- No database migration, new table, dependency, workflow status, notification type, or production deployment.
- One request applies one `route` to every child SKU in the group.
- Preserve the existing `manual_secondary` source namespace and source traceability.
- Store research values in both normalized models and selection1-compatible snapshot fields.
- Ordinary operators can only create records for themselves; existing manager/super-admin owner selection remains authoritative.
- Existing baseline is 683 backend passes / 18 known failures and 245 frontend passes / 6 known failures; new work must add no failures.
- Write each behavior test first, run it to observe the expected failure, then add the smallest implementation.

---

### Task 1: Manual request contract and site currency mapping

**Files:**
- Modify: `backend/app/site_codes.py`
- Modify: `backend/app/schemas.py:733-744`
- Test: `backend/tests/test_secondary_research.py`

**Interfaces:**
- Consumes: existing `normalize_site_code(value: Any) -> str | None`.
- Produces: `site_currency_code(value: Any) -> str | None`, `ManualCompetitorCreate`, `ManualSecondaryChildCreate`, and the expanded `ManualSecondaryResearchCreate` with `route` plus `children`.

- [ ] **Step 1: Write failing currency and schema tests**

Add tests that name the two breakages: a wrong site/currency pair, and acceptance of an invalid multi-child request.

```python
from app.site_codes import site_currency_code


def test_manual_secondary_site_currency_codes_are_unambiguous() -> None:
    assert {code: site_currency_code(code) for code in ("PH", "TH", "VN", "MY", "SG", "ID")} == {
        "PH": "PHP", "TH": "THB", "VN": "VND", "MY": "MYR", "SG": "SGD", "ID": "IDR"
    }
    assert site_currency_code("菲律宾") == "PHP"
    assert site_currency_code("UNKNOWN") is None


def test_manual_secondary_contract_rejects_duplicate_children_and_missing_route_target() -> None:
    with pytest.raises(ValueError, match="child sub_sku values must be unique"):
        schemas.ManualSecondaryResearchCreate.model_validate({
            "country": "PH", "main_sku": "MAIN", "route": "direct_secondary",
            "children": [{"sub_sku": "Sub-A"}, {"sub_sku": "sub-a"}],
        })
    with pytest.raises(ValueError, match="target_daily_sales must be positive"):
        schemas.ManualSecondaryResearchCreate.model_validate({
            "country": "PH", "main_sku": "MAIN", "route": "initial_stocking",
            "children": [{"sub_sku": "SUB-A"}],
        })
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_secondary_research.py -k "site_currency_codes or contract_rejects" -q
```

Expected: collection/import failure because `site_currency_code` and the nested schema do not exist.

- [ ] **Step 3: Add the minimum currency helper and nested Pydantic models**

Add to `site_codes.py`:

```python
SITE_CURRENCIES = {"PH": "PHP", "TH": "THB", "VN": "VND", "MY": "MYR", "SG": "SGD", "ID": "IDR"}


def site_currency_code(value: Any) -> str | None:
    code = normalize_site_code(value)
    return SITE_CURRENCIES.get(code) if code else None
```

Replace the scalar-child manual schema with these concrete shapes in `schemas.py`:

```python
class ManualCompetitorCreate(BaseModel):
    url: str | None = None
    price: float | None = Field(default=None, ge=0)
    monthly_sales: float | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


class ManualSecondaryChildCreate(BaseModel):
    sub_sku: str
    sub_sku_name: str | None = None
    target_daily_sales: float | None = Field(default=None, ge=0)
    reference_price: float | None = Field(default=None, ge=0)
    secondary_competitor_url: str | None = None
    competitors: dict[Literal["lowest", "most_orders", "new_arrival"], ManualCompetitorCreate] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class ManualSecondaryResearchCreate(BaseModel):
    country: str
    site: str | None = None
    main_sku: str
    salesperson_name: str | None = None
    business_period: str | None = None
    main_sku_name: str | None = None
    keyword: str | None = None
    route: Literal["direct_secondary", "initial_stocking", "ready_to_list"]
    children: list[ManualSecondaryChildCreate] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_children(self):
        normalized = [child.sub_sku.strip().casefold() for child in self.children]
        if any(not value for value in normalized):
            raise ValueError("child sub_sku is required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("child sub_sku values must be unique")
        if self.route != "direct_secondary" and any(not child.target_daily_sales or child.target_daily_sales <= 0 for child in self.children):
            raise ValueError("target_daily_sales must be positive for this route")
        return self

    model_config = {"extra": "forbid"}
```

Use one shared validator based on `urllib.parse.urlparse` for competitor and anchor URLs; accept empty values, and require scheme `http`/`https` plus a non-empty host for non-empty values.

- [ ] **Step 4: Run the tests and confirm GREEN**

Run:

```powershell
python -m pytest tests/test_secondary_research.py -k "site_currency_codes or contract_rejects" -q
```

Expected: both tests pass.

- [ ] **Step 5: Commit the contract**

```powershell
git add -- backend/app/site_codes.py backend/app/schemas.py backend/tests/test_secondary_research.py
git commit -m "feat: define manual product entry contract"
```

---

### Task 2: Persist multi-child research data and route existing workflow states

**Files:**
- Modify: `backend/app/services.py:1591-1692`
- Modify: `backend/app/routers/secondary_research.py:61-86`
- Test: `backend/tests/test_secondary_research.py:336-427`

**Interfaces:**
- Consumes: `ManualSecondaryResearchCreate`, `site_currency_code`, `create_stocking_draft_for_claim`, workflow constants, and existing `secondary_research_item`.
- Produces: `create_manual_secondary_research(...) -> list[dict]`; POST `/secondary-research/manual` returns `list[SecondaryResearchItemRead]`.

- [ ] **Step 1: Replace the old single-child tests with failing multi-child route tests**

Add one direct-secondary persistence test with two children and literal expected snapshot/model values:

```python
def test_manual_secondary_research_creates_multi_child_research_snapshot() -> None:
    response = client.post("/secondary-research/manual", json={
        "country": "菲律宾", "main_sku": "MANUAL-MAIN", "main_sku_name": "手工商品",
        "salesperson_name": "销售A", "business_period": "销售自选8.24-8.30", "keyword": "折叠收纳",
        "route": "direct_secondary",
        "children": [
            {
                "sub_sku": "MANUAL-A", "sub_sku_name": "黑色", "target_daily_sales": 6,
                "reference_price": 399, "secondary_competitor_url": "https://shopee.ph/anchor-a",
                "competitors": {
                    "lowest": {"url": "https://shopee.ph/low", "price": 299, "monthly_sales": 88},
                    "most_orders": {"url": "https://shopee.ph/hot", "price": 329, "monthly_sales": 900},
                    "new_arrival": {"url": "https://shopee.ph/new", "price": 359, "monthly_sales": 35},
                },
            },
            {"sub_sku": "MANUAL-B", "sub_sku_name": None, "competitors": {"lowest": {"monthly_sales": 12}}},
        ],
    })
    assert response.status_code == 200
    assert [(row["sub_sku"], row["downstream_status"]) for row in response.json()] == [
        ("MANUAL-A", "waiting_secondary_research"), ("MANUAL-B", "waiting_secondary_research")
    ]
    with SessionLocal() as db:
        opportunities = db.query(models.NewProductOpportunity).order_by(models.NewProductOpportunity.sub_sku).all()
        assert [row.keyword for row in opportunities] == ["折叠收纳", "折叠收纳"]
        assert opportunities[0].snapshot["currency_code"] == "PHP"
        assert opportunities[0].snapshot["fields_by_column"]["Z"] == "https://shopee.ph/low"
        assert opportunities[0].snapshot["fields_by_column"]["AO"] == 6
        assert opportunities[0].snapshot["fields_by_column"]["AP"] == 399
        assert db.query(models.MarketResearchItem).count() == 4
        assert db.query(models.SourceRecordSnapshot).count() == 2
        assert db.query(models.NotificationLog).count() == 0
```

Add separate tests for routing and atomic conflict:

```python
def test_manual_secondary_initial_stocking_prefills_existing_stocking_flow() -> None:
    response = client.post("/secondary-research/manual", json={
        "country": "TH", "main_sku": "STOCK-MAIN", "salesperson_name": "销售A",
        "route": "initial_stocking", "children": [{"sub_sku": "STOCK-A", "target_daily_sales": 3.5}],
    })
    assert response.status_code == 200
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).one()
        request = db.query(models.StockingRequest).one()
        assert (claim.source_column, claim.downstream_status, claim.claim_daily_sales) == ("platform", "waiting_stocking_request", 3.5)
        assert (request.status, request.daily_sales, request.quantity) == ("draft", 3.5, 105)


def test_manual_secondary_ready_to_list_reuses_inventory_branch() -> None:
    response = client.post("/secondary-research/manual", json={
        "country": "VN", "main_sku": "LIST-MAIN", "salesperson_name": "销售A",
        "route": "ready_to_list", "children": [{"sub_sku": "LIST-A", "target_daily_sales": 8}],
    })
    assert response.status_code == 200
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).one()
        assert (claim.inventory_available, claim.needs_stocking, claim.downstream_status) == (True, False, "waiting_listing")
        assert claim.secondary_target_daily_sales == 8
        assert db.query(models.StockingRequest).count() == 0


def test_manual_secondary_existing_child_rejects_whole_group() -> None:
    with SessionLocal() as db:
        db.add(models.NewProductOpportunity(source_type="selection1_developer_claim_feedback", country="PH", site="PH", main_sku="DUP-MAIN", sub_sku="DUP-B", current_status="assigned"))
        db.commit()
    response = client.post("/secondary-research/manual", json={
        "country": "PH", "main_sku": "DUP-MAIN", "salesperson_name": "销售A", "route": "direct_secondary",
        "children": [{"sub_sku": "DUP-A"}, {"sub_sku": "DUP-B"}],
    })
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).count() == 1
        assert db.query(models.SalesClaimForecast).count() == 0
```

- [ ] **Step 2: Run the route tests and confirm RED**

Run:

```powershell
python -m pytest tests/test_secondary_research.py -k "manual_secondary" -q
```

Expected: request validation/response-shape failures because the service still reads scalar `sub_sku` fields and returns one item.

- [ ] **Step 3: Implement one service path with route data only**

In `services.py`:

```python
MANUAL_COMPETITOR_COLUMNS = {
    "lowest": ("最低价", "Z", "AA", "AB"),
    "most_orders": ("most_orders", "AC", "AD", "AE"),
    "new_arrival": ("新晋", "AL", "AM", "AN"),
}

MANUAL_ROUTE_STATUS = {
    "direct_secondary": CLAIM_WAITING_SECONDARY_RESEARCH,
    "initial_stocking": CLAIM_WAITING_STOCKING_REQUEST,
    "ready_to_list": CLAIM_WAITING_LISTING,
}
```

Implement `create_manual_secondary_research` in this order:

1. Clean main SKU, owner, period, site, country and keyword; reject unknown currency/site.
2. Query active opportunities once using case-insensitive main/child SKU matching; filter normalized site in Python; raise one conflict error naming all child SKUs before any insert.
3. For each child, build dynamic headers and non-empty fields for E, Z:AN, AO and AP; save `currency_code`, `headers_by_column`, `fields_by_column`, `fields_by_header`, `cells`, and the complete `manual_secondary` metadata.
4. Create one `NewProductOpportunity`, one `SourceRecordSnapshot`, zero-to-three `MarketResearchItem` rows, and one platform `SalesClaimForecast` per child.
5. Set `secondary_target_daily_sales` for every route. For initial stocking also set `claim_daily_sales`, `needs_stocking=True`, `inventory_available=False`, then call `create_stocking_draft_for_claim`. For ready-to-list set `needs_stocking=False`, `inventory_available=True`. Direct secondary leaves stocking decision fields null.
6. Audit each child and one group event; flush once and return `secondary_research_item` rows in request order.

Add `manual_secondary: "手工新增"` to `_stocking_source_label` so the existing export/workbench label remains readable.

In the router, change the response model to `list[schemas.SecondaryResearchItemRead]`, return the service list, and map the explicit existing-SKU conflict message to HTTP 409. Keep the existing owner enforcement and one commit after the complete service succeeds.

- [ ] **Step 4: Run the route tests and confirm GREEN**

Run:

```powershell
python -m pytest tests/test_secondary_research.py -k "manual_secondary or site_currency_codes" -q
```

Expected: all selected tests pass and no notification/task rows are created.

- [ ] **Step 5: Run adjacent backend regressions**

Run:

```powershell
python -m pytest tests/test_secondary_research.py tests/test_stocking_requests.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit backend behavior**

```powershell
git add -- backend/app/services.py backend/app/routers/secondary_research.py backend/tests/test_secondary_research.py
git commit -m "feat: route manual product entries"
```

---

### Task 3: Frontend form state, validation, payload, and currency labels

**Files:**
- Create: `frontend/src/manualProductEntry.ts`
- Modify: `frontend/src/api.ts:492-501,924-925`
- Test: `frontend/tests/secondaryResearchDrafts.test.ts`

**Interfaces:**
- Consumes: `normalizeSiteText` from `opportunityGroups.ts`.
- Produces: `ManualProductDraft`, `ManualProductRoute`, `ManualProductEntryPayload`, `createManualProductDraft`, `emptyManualProductChild`, `manualProductCurrency`, `validateManualProductDraft`, and `buildManualProductPayload`.

- [ ] **Step 1: Write failing pure behavior tests**

Add literal tests for currency, multi-child normalization, route target validation, duplicate detection, and partial competitor payload preservation:

```typescript
test("手工新增按站点显示 ISO 货币并保留三组竞品", () => {
  assert.equal(manualProductCurrency("菲律宾"), "PHP");
  assert.equal(manualProductCurrency("TH"), "THB");
  const draft = createManualProductDraft("菲律宾", "销售A", "销售自选8.24-8.30");
  draft.main_sku = " MAIN ";
  draft.keyword = " 折叠收纳 ";
  draft.children[0] = {
    ...draft.children[0], sub_sku: " SUB-A ", target_daily_sales: "6", reference_price: "399",
    competitors: { ...draft.children[0].competitors, lowest: { url: "https://shopee.ph/low", price: "299", monthly_sales: "88" } },
  };
  assert.deepEqual(validateManualProductDraft(draft, "direct_secondary"), {});
  assert.deepEqual(buildManualProductPayload(draft, "direct_secondary").children[0], {
    sub_sku: "SUB-A", sub_sku_name: null, target_daily_sales: 6, reference_price: 399,
    secondary_competitor_url: null,
    competitors: { lowest: { url: "https://shopee.ph/low", price: 299, monthly_sales: 88 } },
  });
});

test("手工新增阻止组内重复 SKU 且备货和刊登要求目标单销", () => {
  const draft = createManualProductDraft("菲律宾", "销售A", "销售自选8.24-8.30");
  draft.main_sku = "MAIN";
  draft.children = [{ ...emptyManualProductChild(), sub_sku: "Sub-A" }, { ...emptyManualProductChild(), sub_sku: "sub-a" }];
  assert.equal(validateManualProductDraft(draft, "direct_secondary")["children.1.sub_sku"], "子 SKU 不能重复");
  draft.children[1].sub_sku = "SUB-B";
  assert.equal(validateManualProductDraft(draft, "initial_stocking")["children.0.target_daily_sales"], "首次备货必须填写大于 0 的目标单销");
  assert.equal(validateManualProductDraft(draft, "ready_to_list")["children.1.target_daily_sales"], "可刊登必须填写大于 0 的目标单销");
});
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
node --test tests/secondaryResearchDrafts.test.ts
```

Expected: module-not-found/import failure for `manualProductEntry.ts`.

- [ ] **Step 3: Implement the pure module and wire API types**

The module uses snake_case field names to match the API, stores number inputs as strings, trims all text, converts empty optional fields to `null`, and omits completely empty competitor groups. Use `new URL(value)` plus an `http:`/`https:` scheme check for URL validation. The currency map is exactly:

```typescript
const CURRENCY_BY_SITE: Record<string, string> = {
  PH: "PHP", TH: "THB", VN: "VND", MY: "MYR", SG: "SGD", ID: "IDR"
};
```

Define `ManualProductEntryPayload` in the new module and import it with `import type` in `api.ts`. Change `createManualSecondaryResearch` to return `SecondaryResearchItem[]`.

- [ ] **Step 4: Run the test and confirm GREEN**

Run:

```powershell
node --test tests/secondaryResearchDrafts.test.ts
```

Expected: all tests pass.

- [ ] **Step 5: Commit frontend domain logic**

```powershell
git add -- frontend/src/manualProductEntry.ts frontend/src/api.ts frontend/tests/secondaryResearchDrafts.test.ts
git commit -m "feat: validate manual product entry drafts"
```

---

### Task 4: Render the multi-child dialog and three route actions

**Files:**
- Modify: `frontend/src/SecondaryResearchView.tsx:3-36,74-86,136-138,475-540,573-605`
- Modify: `frontend/src/styles.css:4862-5052`
- Modify: `frontend/src/stockingRequests.ts:155-161`
- Test: `frontend/tests/secondaryResearchDrafts.test.ts`
- Test: `frontend/tests/stockingRequests.test.ts`

**Interfaces:**
- Consumes: all pure helpers from `manualProductEntry.ts` and `api.createManualSecondaryResearch`.
- Produces: a dialog titled `新增 SKU` with common fields, child cards, three competitor cards per child, add/remove controls, and route buttons.

- [ ] **Step 1: Write failing UI contract tests**

Add source-level integration assertions only for wiring that pure tests cannot observe:

```typescript
test("新增 SKU 弹窗接入多子 SKU、三组竞品和三条既有流程", () => {
  assert.match(secondaryResearchViewSource, /<h2 id="manual-secondary-title">新增 SKU<\/h2>/);
  assert.match(secondaryResearchViewSource, /添加子 SKU/);
  assert.match(secondaryResearchViewSource, /最低价竞品/);
  assert.match(secondaryResearchViewSource, /月销最高竞品/);
  assert.match(secondaryResearchViewSource, /新晋竞品/);
  assert.match(secondaryResearchViewSource, /直接进入二调/);
  assert.match(secondaryResearchViewSource, /首次备货/);
  assert.match(secondaryResearchViewSource, /可刊登/);
  assert.match(secondaryResearchViewSource, /submitManualSecondary\("direct_secondary"\)/);
  assert.match(secondaryResearchViewSource, /submitManualSecondary\("initial_stocking"\)/);
  assert.match(secondaryResearchViewSource, /submitManualSecondary\("ready_to_list"\)/);
});
```

Extend the existing source label test:

```typescript
assert.equal(stockingSourceLabel("manual_secondary"), "手工新增");
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```powershell
node --test tests/secondaryResearchDrafts.test.ts tests/stockingRequests.test.ts
```

Expected: new dialog/source-label assertions fail.

- [ ] **Step 3: Replace only the manual dialog block**

In `SecondaryResearchView.tsx`:

- Replace the local scalar draft types with imports from `manualProductEntry.ts`.
- Initialize one child with `createManualProductDraft`.
- Add small immutable update functions for common fields, child fields, competitor fields, append, and remove.
- Change `submitManualSecondary(route)` to run `validateManualProductDraft`, retain input on failure, call `buildManualProductPayload`, disable all action buttons while loading, and show a route-specific success message.
- Render common fields once and each child in a `<section>` with unique aria-labels.
- Keep `secondary_competitor_url` separate from the three initial competitor URLs.
- Use `type="url"` for URLs and `type="number" min="0"` for numeric inputs.
- Keep direct-secondary success loading/search behavior; stocking/listing success only closes the dialog and tells the operator which existing workbench to continue in.

Add only these scoped CSS units: `.manual-product-dialog`, `.manual-product-common-grid`, `.manual-product-child`, `.manual-product-child-head`, `.manual-product-child-grid`, `.manual-product-competitors`, `.manual-product-competitor`, and a narrow-screen media rule. The dialog must have a viewport-bounded max height with internal vertical scrolling.

Add the one `manual_secondary` label branch to `stockingSourceLabel`.

- [ ] **Step 4: Run tests and build to confirm GREEN**

Run:

```powershell
node --test tests/secondaryResearchDrafts.test.ts tests/stockingRequests.test.ts
npm run build
```

Expected: both test files and TypeScript/Vite build pass.

- [ ] **Step 5: Commit the UI**

```powershell
git add -- frontend/src/SecondaryResearchView.tsx frontend/src/styles.css frontend/src/stockingRequests.ts frontend/tests/secondaryResearchDrafts.test.ts frontend/tests/stockingRequests.test.ts
git commit -m "feat: add multi-route manual SKU dialog"
```

---

### Task 5: Focused regression, durable documentation, and final feature verification

**Files:**
- Modify: `docs/2026-07-09-已确认需求记录.md`
- Modify: `docs/02-功能实现状态.md`
- Modify if the current handoff describes manual secondary limitations: `AGENT_HANDOFF.md`
- Modify outside repository: `E:/Project/work-logs/2026-35.md`

**Interfaces:**
- Consumes: completed backend/frontend behavior and the approved spec.
- Produces: authoritative current behavior documentation and evidence for Git convergence.

- [ ] **Step 1: Run focused feature and adjacent regression tests**

```powershell
python -m pytest tests/test_secondary_research.py tests/test_stocking_requests.py -q
node --test tests/secondaryResearchDrafts.test.ts tests/stockingRequests.test.ts
npm run build
python -m alembic heads
git diff --check
```

Expected: focused tests and build pass; Alembic remains the single existing head `a7b8c9d0e123`.

- [ ] **Step 2: Run the complete suites and compare to baseline**

```powershell
python -m pytest -q
npm test -- --run
```

Expected: no failures beyond the recorded backend 18 and frontend 6. If a recorded stale assertion directly names the old manual dialog contract, update that assertion to the approved behavior and require the pass count to increase accordingly.

- [ ] **Step 3: Update authoritative project knowledge**

Append one confirmed-requirement section describing the public fields, route semantics, full initial-stocking chain, ready-to-list bypass, group-level route, target validation, and site currency display. Update the implementation-status document in place instead of adding another status file. Remove any handoff sentence that still says manual entry only supports one child or always enters secondary research.

- [ ] **Step 4: Run the neat-freak documentation alignment gate**

Inventory project docs and rules, check the changed API/state references, and modify only stale authoritative files. Do not add historical narrative to AGENTS.md or duplicate the design spec.

- [ ] **Step 5: Record the work log and commit**

Append an Asia/Shanghai entry to `E:/Project/work-logs/2026-35.md` with project, feature type, summary, affected files, focused/full verification, known baseline debt, and follow-up that deployment was not performed.

```powershell
git add -- docs/2026-07-09-已确认需求记录.md docs/02-功能实现状态.md AGENT_HANDOFF.md
git commit -m "docs: record manual SKU routing"
```

Stage `AGENT_HANDOFF.md` only if it actually changed.

- [ ] **Step 6: Verify the feature branch is ready for Git convergence**

```powershell
git status --short --branch
git log --oneline --decorate prod-2026-08-25-baseline..HEAD
git diff --check prod-2026-08-25-baseline..HEAD
```

Expected: clean branch, only reviewed feature/docs commits after the production baseline, and no whitespace errors.

## Self-Review

- Spec coverage: Tasks 1-4 cover currency, payload, fields, multi-child UI, three routes, traceability, permissions, validation, atomicity, and existing-flow reuse; Task 5 covers tests and durable docs.
- Placeholder scan: no deferred implementation markers or unspecified error-handling steps remain.
- Type consistency: backend and frontend use the same three route strings, competitor keys, snake_case payload fields, and list response shape.
- Scope: Git deletion and branch convergence are intentionally isolated in `2026-08-25-git-single-branch-convergence.md`.
