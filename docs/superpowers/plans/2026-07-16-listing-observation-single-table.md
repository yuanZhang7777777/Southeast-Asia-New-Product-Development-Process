# 刊登与观察单表工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将刊登与观察页面收敛为一张以 `task_key` 业务上下文分组、主 SKU 为主视觉的 Excel 式表格，以业务状态筛选替代顶部页签，并修正主管/运营数据范围。

**Architecture:** 保持后端、数据库和 API 返回结构不变；前端继续一次请求 `view=all`，用纯函数把待刊登上下文、刊登记录和 Item 周期组装成主 SKU 分组，再按业务状态和现有字段筛选。待刊登编辑器移动到表格分组行的展开区域，周期明细继续复用现有表内复盘能力。

**Tech Stack:** React 19、TypeScript、Vite、Node `node:test`、现有 CSS；不新增依赖。

## Global Constraints

- 只修改开发分支和开发环境 `139.224.2.166:18081`；不得连接、部署或重启生产服务器 `101.132.26.138`。
- 不修改后端、数据库迁移、周 Item 取数逻辑或 API 协议。
- 页面不得出现顶部状态页签、`待取数`筛选或“只看待我处理”开关。
- 业务状态默认 `待刊登`；`全部`必须包含待刊登分组和全部 Item 周期。
- 普通运营的数据范围由后端认证身份强制；主管默认看全部，并可按负责人筛选。
- 待取数只作为内部 `pending_data`；页面显示 `观察中`，自动指标显示 `-`，不可复盘。
- 没有任何刊登记录的分组才属于待刊登；已刊登分组继续提供“新增店铺 + Item”。
- 分组唯一键必须是后端 `task_key`（来源 + 业务期数 + 国家/站点 + 主 SKU + 负责人）；相同主 SKU 在不同上下文下不得合并。
- 不增加数量角标、统计 API、依赖、兼容层或未确认的自动刷新机制。

---

### Task 1: 建立可测试的单表分组与业务状态模型

**Files:**
- Modify: `frontend/src/listingObservation.ts`
- Test: `frontend/tests/listingObservation.test.ts`

**Interfaces:**
- Consumes: `PendingListingTask`、`ListingRecord`、`ObservationPeriodRow` 及现有 `buildListingTaskContexts(...)`。
- Produces: `WorkbenchBusinessStatus`、`ListingWorkbenchGroup`、`buildListingWorkbenchGroups(...)`、`filterListingWorkbenchGroups(...)` 和简化后的 `resolveWorkbenchScope(...)`。

- [x] **Step 1: 写失败测试，覆盖分组、默认待刊登、全部与权限范围**

在 `frontend/tests/listingObservation.test.ts` 增加导入：

```ts
import { readFileSync } from "node:fs";
import type { ListingRecord, ObservationPeriodRow, PendingListingTask } from "../src/api.ts";
```

并在现有 `../src/listingObservation.ts` 导入列表中加入 `buildListingWorkbenchGroups` 和 `filterListingWorkbenchGroups`。

并添加三个只补稳定默认值的小工厂：

```ts
function pendingTask(patch: Partial<PendingListingTask> = {}): PendingListingTask {
  return {
    task_key: "task-1",
    source_type: "selection1",
    business_period: "2026-07",
    country: "菲律宾",
    site: "PH",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    salesperson_name: "运营甲",
    claim_record_ids: ["claim-1"],
    default_first_period_start: "2026-07-23",
    ...patch
  };
}

function listingRecord(patch: Partial<ListingRecord> = {}): ListingRecord {
  return {
    id: "listing-1",
    task_key: "task-1",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    country: "菲律宾",
    site: "PH",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    item: "ITEM-1",
    listing_strategy: "低价切入",
    first_period_start: "2026-07-23",
    status: "active",
    tracking_status: "active",
    first_round_completed_at: null,
    ...patch
  };
}

function observationRow(patch: Partial<ObservationPeriodRow> = {}): ObservationPeriodRow {
  return {
    id: "period-1",
    listing_record_id: "listing-1",
    main_sku: "SKU1",
    main_sku_name: "商品1",
    country: "菲律宾",
    salesperson_name: "运营甲",
    shop: "Shopee-PH",
    item: "ITEM-1",
    week_number: 1,
    period_start: "2026-07-23",
    period_end: "2026-07-29",
    status: "pending_data",
    tracking_status: "active",
    order_count: null,
    total_revenue: null,
    gross_profit_amount: null,
    gross_profit_rate: null,
    product_positioning: null,
    optimization_action: null,
    four_week_summary: null,
    first_round_completed_at: null,
    ...patch
  };
}
```

添加真实对象测试：

```ts
test("单表工作台按 task_key 分组且已有作废记录也不再算待刊登", () => {
  const pending = pendingTask({ task_key: "task-pending", main_sku: "SAME", country: "菲律宾" });
  const listed = pendingTask({ task_key: "task-listed", main_sku: "SAME", country: "越南" });
  const listing = listingRecord({
    id: "listing-1",
    task_key: "task-listed",
    main_sku: "SAME",
    country: "越南",
    status: "voided",
    tracking_status: "stopped"
  });
  const period = observationRow({
    id: "period-1",
    listing_record_id: "listing-1",
    main_sku: "SAME",
    country: "越南",
    status: "completed",
    tracking_status: "stopped"
  });

  const groups = buildListingWorkbenchGroups([pending, listed], [listing], [period], "2026-07-23");

  assert.equal(groups.length, 2);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "pending_listing").map((group) => group.context.task_key), ["task-pending"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "all").map((group) => group.context.task_key), ["task-pending", "task-listed"]);
  assert.equal(groups.find((group) => group.context.task_key === "task-listed")?.periodRows.length, 1);
});

test("业务状态只返回可处理待复盘或对应里程碑记录", () => {
  const groups = buildListingWorkbenchGroups(
    [pendingTask({ task_key: "task-listed", main_sku: "SKU1" })],
    [
      listingRecord({ id: "active", task_key: "task-listed", main_sku: "SKU1" }),
      listingRecord({ id: "stopped", task_key: "task-listed", main_sku: "SKU1", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" }),
      listingRecord({ id: "voided", task_key: "task-listed", main_sku: "SKU1", status: "voided", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" })
    ],
    [
      observationRow({ id: "review", listing_record_id: "active", main_sku: "SKU1", status: "pending_review" }),
      observationRow({ id: "stopped-period", listing_record_id: "stopped", main_sku: "SKU1", status: "completed", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" }),
      observationRow({ id: "voided-period", listing_record_id: "voided", main_sku: "SKU1", status: "completed", tracking_status: "stopped", first_round_completed_at: "2026-08-20T10:00:00+08:00" })
    ],
    "2026-07-23"
  );

  assert.deepEqual(filterListingWorkbenchGroups(groups, "pending_review")[0].periodRows.map((row) => row.id), ["review"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "stopped")[0].periodRows.map((row) => row.id), ["stopped-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "voided")[0].periodRows.map((row) => row.id), ["voided-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "first_round_completed")[0].periodRows.map((row) => row.id), ["stopped-period", "voided-period"]);
  assert.deepEqual(filterListingWorkbenchGroups(groups, "voided")[0].listings.map((listing) => listing.id), ["voided"]);
});

test("主管默认全量而主管运营视角按所选运营查询", () => {
  assert.deepEqual(resolveWorkbenchScope("manager", true, ""), {});
  assert.deepEqual(resolveWorkbenchScope("operator", true, "运营甲"), { salesperson_name: "运营甲" });
  assert.equal(resolveWorkbenchScope("operator", true, ""), null);
  assert.deepEqual(resolveWorkbenchScope("operator", false, "伪造运营"), {});
});
```

- [x] **Step 2: 运行聚焦测试并确认按预期失败**

Run: `cd frontend && node --test tests/listingObservation.test.ts`

Expected: FAIL，提示新的导出不存在或旧 `resolveWorkbenchScope` 签名/结果不匹配。

- [x] **Step 3: 写最小纯函数实现**

在 `frontend/src/listingObservation.ts` 使用类型导入并实现：

```ts
import type { ListingRecord, ObservationPeriodRow, PendingListingTask } from "./api";

export type WorkbenchBusinessStatus =
  | "all"
  | "pending_listing"
  | "pending_review"
  | "first_round_completed"
  | "stopped"
  | "voided";

export type ListingWorkbenchGroup = {
  context: PendingListingTask;
  listings: ListingRecord[];
  periodRows: ObservationPeriodRow[];
  pendingListing: boolean;
};

export function buildListingWorkbenchGroups(
  tasks: readonly PendingListingTask[],
  listings: readonly ListingRecord[],
  periodRows: readonly ObservationPeriodRow[],
  defaultFirstPeriodStart: string
): ListingWorkbenchGroup[] {
  const contexts = buildListingTaskContexts(tasks, listings, defaultFirstPeriodStart) as PendingListingTask[];
  return contexts.map((context) => {
    const groupListings = listings.filter((listing) => listing.task_key === context.task_key);
    const listingIds = new Set(groupListings.map((listing) => listing.id));
    return {
      context,
      listings: groupListings,
      periodRows: periodRows.filter((row) => listingIds.has(row.listing_record_id)),
      pendingListing: groupListings.length === 0
    };
  });
}

export function filterListingWorkbenchGroups(
  groups: readonly ListingWorkbenchGroup[],
  status: WorkbenchBusinessStatus
): ListingWorkbenchGroup[] {
  const visible = groups.flatMap((group) => {
    if (status === "pending_listing") return group.pendingListing ? [{ ...group, periodRows: [] }] : [];
    if (status === "all") return [group];
    const listingById = new Map(group.listings.map((listing) => [listing.id, listing]));
    const periodRows = group.periodRows.filter((row) => {
      const listing = listingById.get(row.listing_record_id);
      if (!listing) return false;
      if (status === "pending_review") {
        return listing.status === "active" && row.tracking_status === "active" && row.status === "pending_review";
      }
      if (status === "first_round_completed") return Boolean(listing.first_round_completed_at);
      if (status === "stopped") return listing.status === "active" && listing.tracking_status === "stopped";
      return listing.status === "voided";
    });
    const visibleListingIds = new Set(periodRows.map((row) => row.listing_record_id));
    const visibleListings = group.listings.filter((listing) => visibleListingIds.has(listing.id));
    return periodRows.length ? [{ ...group, listings: visibleListings, periodRows }] : [];
  });
  return visible.sort((left, right) => {
    const priority = (group: ListingWorkbenchGroup) => {
      if (group.pendingListing) return 0;
      const listingById = new Map(group.listings.map((listing) => [listing.id, listing]));
      return group.periodRows.some((row) => {
        const listing = listingById.get(row.listing_record_id);
        return listing?.status === "active" && row.tracking_status === "active" && row.status === "pending_review";
      }) ? 1 : 2;
    };
    return priority(left) - priority(right)
      || left.context.main_sku.localeCompare(right.context.main_sku)
      || left.context.salesperson_name.localeCompare(right.context.salesperson_name);
  });
}

export function resolveWorkbenchScope(
  role: "operator" | "manager",
  canManage: boolean,
  operatorName: string
) {
  if (canManage && role === "operator") {
    return operatorName ? { salesperson_name: operatorName } : null;
  }
  return {};
}
```

`null` 表示具备主管权限的账号切到运营视角但尚未选择运营。页面此时清空工作台数据并显示“请先选择运营”，不得向后端发送可能返回全量数据的请求。

- [x] **Step 4: 运行聚焦测试并确认通过**

Run: `cd frontend && node --test tests/listingObservation.test.ts`

Expected: PASS，包含新增的分组、状态和权限范围用例。

- [x] **Step 5: 提交 Task 1**

```bash
git add frontend/src/listingObservation.ts frontend/tests/listingObservation.test.ts
git commit -m "refactor: model grouped listing workbench"
```

---

### Task 2: 将页面改成一张可展开的分组表

**Files:**
- Modify: `frontend/src/ListingObservationView.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/tests/listingObservation.test.ts`

**Interfaces:**
- Consumes: Task 1 的 `WorkbenchBusinessStatus`、`buildListingWorkbenchGroups(...)`、`filterListingWorkbenchGroups(...)`、`resolveWorkbenchScope(...)`。
- Produces: 单表工作台、分组展开刊登编辑器、统一业务状态筛选和中性周期状态文案。

导入调整必须保持精确：React 导入增加 `Fragment`；API 导入删除页面不再使用的 `ListingWorkbenchView`；工具导入删除 `buildListingTaskContexts`，增加 `WorkbenchBusinessStatus`、`buildListingWorkbenchGroups` 和 `filterListingWorkbenchGroups`。`ListingRecord` 继续保留，用于按刊登生命周期判断周期行是否可编辑。

- [x] **Step 1: 写失败的页面契约测试**

在 `frontend/tests/listingObservation.test.ts` 读取 `ListingObservationView.tsx` 源码并断言：

```ts
test("刊登观察页面使用单表和业务状态筛选且不暴露内部待取数", () => {
  const source = readFileSync(new URL("../src/ListingObservationView.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /const TABS/);
  assert.doesNotMatch(source, /listing-tabs/);
  assert.doesNotMatch(source, /只看待我处理/);
  assert.doesNotMatch(source, /待取数/);
  assert.match(source, /业务状态/);
  assert.match(source, /观察中/);
  assert.match(source, /新增店铺 \+ Item/);
});
```

- [x] **Step 2: 运行聚焦测试并确认按预期失败**

Run: `cd frontend && node --test tests/listingObservation.test.ts`

Expected: FAIL，因为现有页面仍有 `TABS`、顶部页签和待取数文案。

- [x] **Step 3: 替换页面状态和筛选模型**

在 `ListingObservationView.tsx`：

```ts
type WorkbenchFilters = ObservationFilters & { business_status: WorkbenchBusinessStatus };

const DEFAULT_FILTERS: WorkbenchFilters = {
  business_status: "pending_listing",
  query: "",
  country: "",
  salesperson_name: "",
  shop: "",
  period_start: "",
  status: "",
  week_number: "",
  product_positioning: "",
  tracking_status: ""
};
```

删除 `TABS`、`view` 和 `only_my_tasks`。`loadWorkbench()` 在允许查询时始终请求 `view: "all"` 并展开 `resolveWorkbenchScope(props.role, props.canManage, props.operatorName)`。请求门必须先递增，再判断 scope；这样切到尚未选择运营的运营视角时，上一笔全量请求即使稍后返回也会失效：

```ts
async function loadWorkbench() {
  const requestId = requestGate.current.start();
  const scope = resolveWorkbenchScope(props.role, props.canManage, props.operatorName);
  if (!scope) {
    setData(EMPTY_DATA);
    setSelectedPeriods([]);
    setLoading(false);
    return;
  }
  setLoading(true);
  try {
    const response = await api.listingWorkbench({ view: "all", ...scope });
    // 继续沿用现有请求门、草稿初始化和错误处理。
  } finally {
    if (requestGate.current.isCurrent(requestId)) setLoading(false);
  }
}
```

此处注释代表保留函数中现有的 `isCurrent` 检查、`setData`、`setReviewDrafts`、`catch` 和 `finally`，不是省略业务逻辑。页面在该 scope 为 `null` 时显示“请先选择运营”。运营视角过滤时把 `salesperson_name` 视为空，避免隐藏筛选残留：

```ts
const effectiveFilters = props.role === "manager"
  ? filters
  : { ...filters, salesperson_name: "" };
```

- [x] **Step 4: 组装和筛选分组表**

```ts
const groups = useMemo(
  () => buildListingWorkbenchGroups(
    data.pending_listing_tasks,
    data.listing_records,
    data.period_rows,
    defaultNextBusinessPeriodStart()
  ),
  [data]
);
const businessGroups = useMemo(
  () => filterListingWorkbenchGroups(groups, filters.business_status),
  [filters.business_status, groups]
);
const hasPeriodFilters = Boolean(
  effectiveFilters.shop
  || effectiveFilters.period_start
  || effectiveFilters.status
  || effectiveFilters.week_number
  || effectiveFilters.product_positioning
  || effectiveFilters.tracking_status
);
const visibleGroups = useMemo(
  () => businessGroups.flatMap((group) => {
    const periodRows = sortObservationRows(filterObservationRows(group.periodRows, effectiveFilters));
    const text = effectiveFilters.query.trim().toLocaleLowerCase();
    const contextMatches = !text || [group.context.main_sku, group.context.main_sku_name]
      .some((value) => value?.toLocaleLowerCase().includes(text));
    const commonMatches = (!effectiveFilters.country || group.context.country === effectiveFilters.country)
      && (!effectiveFilters.salesperson_name || group.context.salesperson_name === effectiveFilters.salesperson_name);
    if (!commonMatches) return [];
    if (group.pendingListing) {
      return contextMatches && !hasPeriodFilters ? [{ ...group, periodRows: [] }] : [];
    }
    const visibleListingIds = new Set(periodRows.map((row) => row.listing_record_id));
    const listings = group.listings.filter((listing) => visibleListingIds.has(listing.id));
    return periodRows.length ? [{ ...group, listings, periodRows }] : [];
  }),
  [businessGroups, effectiveFilters, hasPeriodFilters]
);
const visibleRows = visibleGroups.flatMap((group) => group.periodRows);
```

当店铺、业务周期、周次、定位、跟踪状态或周期处理状态已设置时，不保留没有周期明细的分组；关键词、国家和负责人同时作用于分组行和周期行。

在计算批量选择、单行编辑和四周总结可编辑性前先建立 `listingById`。所有 `canReview` 调用都必须带对应刊登记录，避免已作废记录在“全部”中仍出现可编辑入口：

```ts
const listingById = useMemo(
  () => new Map(data.listing_records.map((listing) => [listing.id, listing])),
  [data.listing_records]
);
const reviewableRows = visibleRows.filter((row) => canReview(row, listingById.get(row.listing_record_id)));
const reviewableIds = reviewableRows.map((row) => row.id);
const visibleSelectedIds = visibleSelectedPeriodIds(selectedPeriods, reviewableRows);
const summaryListing = summaryRow ? listingById.get(summaryRow.listing_record_id) : undefined;
```

- [x] **Step 5: 用单个 `<table>` 渲染分组行、编辑行和周期行**

保留现有周期列和周期行单元格，只把外层改为：

```tsx
<table className="listing-period-table listing-grouped-table">
  <thead>
    <tr>
      <th className="listing-sticky sticky-0">选择</th>
      <th className="listing-sticky sticky-1">主 SKU</th>
      <th className="listing-sticky sticky-2">店铺</th>
      <th className="listing-sticky sticky-3">Item</th>
      <th className="listing-sticky sticky-4">负责人</th>
      <th className="listing-sticky sticky-5">周次</th>
      <th className="listing-sticky sticky-6">业务周期</th>
      <th>业务状态</th>
      <th>订单量</th>
      <th>总收入</th>
      <th>一次毛利额</th>
      <th>一次毛利率</th>
      <th>产品定位</th>
      <th>优化操作</th>
      <th>操作</th>
    </tr>
  </thead>
  <tbody>
    {visibleGroups.map((group) => (
      <Fragment key={group.context.task_key}>
        <tr className="listing-main-group-row">
          <td colSpan={15}>
            <button type="button" className="listing-group-toggle" onClick={() => toggleGroup(group.context.task_key)}>
              {expandedGroups.includes(group.context.task_key) ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              <b>{group.context.main_sku}</b>
              <span>{group.context.main_sku_name || "-"}</span>
              <span>{group.context.country || group.context.site || "-"}</span>
              <span>{group.context.salesperson_name}</span>
              {group.pendingListing && <span className="pill amber">待刊登</span>}
            </button>
            <button type="button" className="btn small" onClick={() => {
              setExpandedGroups((current) => current.includes(group.context.task_key)
                ? current
                : [...current, group.context.task_key]);
              addListingDraft(group.context);
            }}>
              <Plus size={13} />{group.pendingListing ? "填写刊登" : "新增店铺 + Item"}
            </button>
          </td>
        </tr>
        {expandedGroups.includes(group.context.task_key) && (
          <tr className="listing-group-editor-row">
            <td colSpan={15}>
              <PendingListingTasks
                tasks={[group.context]}
                records={group.listings}
                periods={data.period_rows}
                drafts={listingDrafts}
                errors={listingErrors}
                loading={loading}
                onAdd={addListingDraft}
                onUpdate={updateListingDraft}
                onRemove={removeListingDraft}
                onSubmit={(task) => void submitListings(task)}
                onEdit={openListingEditor}
                onTracking={(record) => void changeListingTracking(record)}
                onVoid={openVoidListing}
                canVoid={props.canManage}
              />
            </td>
          </tr>
        )}
      </Fragment>
    ))}
  </tbody>
</table>
```

不要为周期行新建组件或复制回调：把当前 `ListingObservationView.tsx` 中的周期 `<tr>` 原位移入 `group.periodRows.map(...)`，只改 `canReview(row, listing)`、状态文案和 `pending_data` 四个指标。刊登编辑区也直接复用现有 `PendingListingTasks`，每个展开分组传 `tasks={[group.context]}`；这样沿用现有字段、错误展示、校验和 API 回调，不新增第二套编辑器。把组件中的空提示改为“点击‘新增店铺 + Item’……”，已有记录状态统一调用 `listingStatusLabel(record)`。

在主组件增加：

```ts
const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
function toggleGroup(taskKey: string) {
  setExpandedGroups((current) => current.includes(taskKey)
    ? current.filter((key) => key !== taskKey)
    : [...current, taskKey]);
}
```

- [x] **Step 6: 替换筛选和状态文案**

业务状态下拉固定为：

```tsx
<label>
  业务状态
  <select value={filters.business_status} onChange={(event) => setFilter("business_status", event.target.value as WorkbenchBusinessStatus)}>
    <option value="all">全部</option>
    <option value="pending_listing">待刊登</option>
    <option value="pending_review">待复盘</option>
    <option value="first_round_completed">首轮观察完成</option>
    <option value="stopped">停止跟踪</option>
    <option value="voided">已作废</option>
  </select>
</label>
```

周期处理状态只保留空值、`pending_review` 和 `completed`。状态文案使用：

```ts
function periodStatusLabel(row: ObservationPeriodRow, listing?: ListingRecord) {
  if (listing?.status === "voided") return "已作废";
  if (row.tracking_status === "stopped") return "停止跟踪";
  if (row.status === "pending_data") return "观察中";
  if (row.status === "pending_review") return "待复盘";
  return "本周已复盘";
}

function periodStatusClass(row: ObservationPeriodRow, listing?: ListingRecord) {
  if (listing?.status === "voided" || row.tracking_status === "stopped" || row.status === "pending_data") return "gray";
  return row.status === "pending_review" ? "amber" : "green";
}

function canReview(row: ObservationPeriodRow, listing?: ListingRecord) {
  return listing?.status === "active"
    && row.status === "pending_review"
    && row.tracking_status === "active";
}

function listingStatusLabel(record: ListingRecord) {
  if (record.status === "voided") return "已作废";
  if (record.tracking_status === "stopped") return "停止跟踪";
  if (record.first_round_completed_at) return "首轮观察完成";
  return "观察中";
}
```

`pending_data` 的订单量、收入、毛利额和毛利率全部显示 `-`，已有刊登记录不再使用“任一周取数后整条显示已取数”的旧算法。待刊登筛选为空时显示“当前没有待刊登主 SKU，可选择全部查看观察记录”。

四周总结弹窗里的 `disabled` 和按钮文案同样使用 `canReview(summaryRow, summaryListing)`，不能继续调用缺少刊登记录参数的旧签名。

- [x] **Step 7: 添加最小分组样式**

在 `frontend/src/styles.css` 复用现有表格、按钮和刊登编辑器样式，只新增：

```css
.listing-main-group-row td { background: #f4f7fb; border-top: 2px solid #dbe3ee; }
.listing-group-toggle { display: inline-flex; align-items: center; gap: 8px; border: 0; background: transparent; color: inherit; cursor: pointer; }
.listing-group-editor-row > td { padding: 14px; background: #fbfcfe; }
```

如果现有 CSS 已覆盖其中任一声明，复用现有规则，不重复添加。

- [x] **Step 8: 运行聚焦测试、全量前端测试和构建**

Run:

```bash
cd frontend
node --test tests/listingObservation.test.ts
npm test
npm run build
```

Expected: 聚焦测试通过；全量测试 0 failed；TypeScript 与 Vite 构建成功。

- [x] **Step 9: 提交 Task 2**

```bash
git add frontend/src/ListingObservationView.tsx frontend/src/styles.css frontend/tests/listingObservation.test.ts
git commit -m "feat: unify listing workbench table"
```

---

### Task 3: 修正双角色主管的运营选择

**Files:**
- Modify: `frontend/src/App.tsx`
- Test: `frontend/tests/listingObservation.test.ts`

**Interfaces:**
- Consumes: 现有 `canManage`、`authSession.operator_name` 和 `activeOperator`。
- Produces: 普通运营锁定本人；具备主管权限的账号可保留手动选择的运营。

- [ ] **Step 1: 写失败的源代码契约测试**

```ts
test("只有普通运营会被登录身份锁定当前运营", () => {
  const source = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
  assert.match(source, /authSession\?\.operator_name && !canManage/);
});
```

- [ ] **Step 2: 运行聚焦测试并确认失败**

Run: `cd frontend && node --test tests/listingObservation.test.ts`

Expected: FAIL，现有 effect 未检查 `!canManage`。

- [ ] **Step 3: 修改现有 effect 的一个条件**

```ts
if (authSession?.operator_name && !canManage) {
  if (activeOperator !== authSession.operator_name) setActiveOperator(authSession.operator_name);
  return;
}
```

把 `canManage` 加入该 effect 的依赖数组；主管切到运营视角后继续使用下拉框选择值，普通运营仍只能是认证映射姓名。

- [ ] **Step 4: 运行聚焦测试和全量前端测试**

Run:

```bash
cd frontend
node --test tests/listingObservation.test.ts
npm test
```

Expected: 0 failed。

- [ ] **Step 5: 提交 Task 3**

```bash
git add frontend/src/App.tsx frontend/tests/listingObservation.test.ts
git commit -m "fix: preserve manager operator selection"
```

---

### Task 4: 文档同步、开发环境部署与冒烟验证

**Files:**
- Modify: `docs/00-新会话交接.md`
- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/2026-07-09-已确认需求记录.md`
- Modify: `docs/superpowers/plans/2026-07-16-listing-observation-single-table.md`
- Append: `C:\Users\86173\.codex\work-logs\2026-29.md`

**Interfaces:**
- Consumes: Task 1–3 的已验证前端提交。
- Produces: 与代码一致的权威文档、开发环境前端部署和可复核证据。

- [ ] **Step 1: 运行最终本地验证**

Run:

```bash
git diff --check
cd frontend
npm test
npm run build
```

Expected: 0 failed，构建成功。

- [ ] **Step 2: 用 neat-freak 对齐权威文档**

把功能状态改成已实现，确认当前文档中不再把顶部页签、“只看待我处理”或用户可见“待取数”描述为现状。历史实施计划保留历史语境，不篡改已完成步骤；不删除文档。

- [ ] **Step 3: 只部署开发环境前端**

使用现有 `hz-new-product-dev` SSH 别名和 `hengzhe-new-product-dev` Compose 项目，将当前提交打包到 `/opt/hengzhe-new-product-dev`。归档必须排除 `.env`、`node_modules` 和 `dist`；在服务器临时目录构建后原子切换应用目录，只重建 frontend 容器。

部署前后分别记录 API、PostgreSQL、Redis 容器 ID，并断言三者未变化。不得连接 `101.132.26.138`。

- [ ] **Step 4: 冒烟验证开发地址**

验证：

```text
GET http://139.224.2.166:18081/ -> 200
GET http://139.224.2.166:18081/api/health -> environment=development
服务器源码无 const TABS、listing-tabs、只看待我处理和用户可见“待取数”
服务器源码保留业务状态默认 pending_listing、观察中和新增店铺 + Item
```

- [ ] **Step 5: 提交文档收尾**

```bash
git add docs/00-新会话交接.md docs/02-功能实现状态.md docs/2026-07-09-已确认需求记录.md docs/superpowers/plans/2026-07-16-listing-observation-single-table.md
git commit -m "docs: record single-table workbench rollout"
```
