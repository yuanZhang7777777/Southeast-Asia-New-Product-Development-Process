import { ChevronDown, ChevronUp, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { Fragment, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  ListingRecord,
  ListingWorkbenchResponse,
  ObservationPeriodRow,
  PendingListingTask
} from "./api";
import {
  buildListingWorkbenchGroups,
  createRequestGate,
  defaultNextBusinessPeriodStart,
  filterListingWorkbenchGroups,
  filterObservationRows,
  formatObservationMetric,
  formatPercent,
  hasFetchedMetrics,
  ListingDraft,
  ListingDraftErrors,
  latestPeriodIdsByListing,
  mapReviewServerRowErrors,
  mapServerRowErrors,
  ObservationFilters,
  ObservationReviewDraft,
  ObservationReviewErrors,
  PRODUCT_POSITIONINGS,
  ProductPositioning,
  productListingSummary,
  resolveWorkbenchScope,
  summarySalespersonScope,
  sortObservationRows,
  validateListingDrafts,
  validateObservationReviews,
  visibleSelectedPeriodIds,
  WorkbenchBusinessStatus
} from "./listingObservation";

const EMPTY_DATA: ListingWorkbenchResponse = { pending_listing_tasks: [], listing_records: [], period_rows: [] };
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

export function ListingObservationView(props: {
  role: "operator" | "manager";
  operatorName: string;
  canManage: boolean;
  onStatus: (message: string) => void;
}) {
  const [data, setData] = useState<ListingWorkbenchResponse>(EMPTY_DATA);
  const [filters, setFilters] = useState<WorkbenchFilters>(DEFAULT_FILTERS);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [listingDrafts, setListingDrafts] = useState<Record<string, ListingDraft[]>>({});
  const [listingErrors, setListingErrors] = useState<Record<string, ListingDraftErrors[]>>({});
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, ObservationReviewDraft>>({});
  const [reviewErrors, setReviewErrors] = useState<Record<string, ObservationReviewErrors>>({});
  const [selectedPeriods, setSelectedPeriods] = useState<string[]>([]);
  const [summaryPeriodId, setSummaryPeriodId] = useState<string | null>(null);
  const [newPeriod, setNewPeriod] = useState<{ listingId: string; periodStart: string } | null>(null);
  const [editingListing, setEditingListing] = useState<{ record: ListingRecord; draft: ListingDraft; hasMetrics: boolean } | null>(null);
  const [editErrors, setEditErrors] = useState<ListingDraftErrors>({});
  const [voidingListing, setVoidingListing] = useState<{ record: ListingRecord; reason: string } | null>(null);
  const requestGate = useRef(createRequestGate());
  const workbenchRoot = useRef<HTMLDivElement | null>(null);
  const dialogReturnFocus = useRef<HTMLElement | null>(null);
  const summaryDialog = useRef<HTMLDivElement | null>(null);
  const newPeriodDialog = useRef<HTMLDivElement | null>(null);
  const editDialog = useRef<HTMLDivElement | null>(null);
  const voidDialog = useRef<HTMLDivElement | null>(null);

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
      const response = await api.listingWorkbench({
        view: "all",
        ...scope
      });
      if (!requestGate.current.isCurrent(requestId)) return;
      setData(response);
      setSelectedPeriods([]);
      setReviewDrafts((current) => {
        const next = { ...current };
        for (const row of response.period_rows) if (!next[row.id]) next[row.id] = reviewDraft(row);
        return next;
      });
    } catch (error) {
      if (requestGate.current.isCurrent(requestId)) props.onStatus(errorMessage(error, "刊登与观察工作台加载失败"));
    } finally {
      if (requestGate.current.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkbench();
  }, [props.role, props.canManage, props.operatorName]);

  useEffect(() => { if (summaryPeriodId) summaryDialog.current?.focus(); }, [summaryPeriodId]);
  useEffect(() => { if (newPeriod) newPeriodDialog.current?.focus(); }, [newPeriod?.listingId]);
  useEffect(() => { if (editingListing) editDialog.current?.focus(); }, [editingListing?.record.id]);
  useEffect(() => { if (voidingListing) voidDialog.current?.focus(); }, [voidingListing?.record.id]);

  const effectiveFilters = props.role === "manager"
    ? filters
    : { ...filters, salesperson_name: "" };
  const groups = useMemo(() => buildListingWorkbenchGroups(
    data.pending_listing_tasks,
    data.listing_records,
    data.period_rows,
    defaultNextBusinessPeriodStart()
  ), [data]);
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
      const text = effectiveFilters.query?.trim().toLocaleLowerCase();
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
  const countries = useMemo(() => unique([
    ...groups.map((group) => group.context.country || ""),
    ...data.period_rows.map((row) => row.country || "")
  ]), [data.period_rows, groups]);
  const owners = useMemo(() => unique([
    ...groups.map((group) => group.context.salesperson_name),
    ...data.period_rows.map((row) => row.salesperson_name)
  ]), [data.period_rows, groups]);
  const listingById = useMemo(
    () => new Map(data.listing_records.map((listing) => [listing.id, listing])),
    [data.listing_records]
  );
  const reviewableRows = visibleRows.filter((row) => canReview(row, listingById.get(row.listing_record_id)));
  const reviewableIds = reviewableRows.map((row) => row.id);
  const visibleSelectedIds = visibleSelectedPeriodIds(selectedPeriods, reviewableRows);
  const allReviewableSelected = reviewableIds.length > 0 && reviewableIds.every((id) => visibleSelectedIds.includes(id));
  const summaryRow = data.period_rows.find((row) => row.id === summaryPeriodId) || null;
  const summaryListing = summaryRow ? listingById.get(summaryRow.listing_record_id) : undefined;
  const latestPeriodIds = useMemo(() => latestPeriodIdsByListing(data.period_rows), [data.period_rows]);

  function setFilter<K extends keyof WorkbenchFilters>(key: K, value: WorkbenchFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function toggleGroup(taskKey: string) {
    setExpandedGroups((current) => current.includes(taskKey)
      ? current.filter((key) => key !== taskKey)
      : [...current, taskKey]);
  }

  function rememberDialogFocus() {
    dialogReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }

  function restoreDialogFocus() {
    const target = dialogReturnFocus.current;
    requestAnimationFrame(() => (target?.isConnected ? target : workbenchRoot.current)?.focus());
  }

  function closeSummary() {
    setSummaryPeriodId(null);
    restoreDialogFocus();
  }

  function openSummary(periodId: string) {
    rememberDialogFocus();
    setSummaryPeriodId(periodId);
  }

  function closeNewPeriod() {
    setNewPeriod(null);
    restoreDialogFocus();
  }

  function openNewPeriod(listingId: string) {
    rememberDialogFocus();
    setNewPeriod({ listingId, periodStart: defaultNextBusinessPeriodStart() });
  }

  function openListingEditor(record: ListingRecord) {
    rememberDialogFocus();
    const periods = data.period_rows.filter((row) => row.listing_record_id === record.id);
    setEditErrors({});
    setEditingListing({
      record,
      hasMetrics: hasFetchedMetrics(periods),
      draft: {
        shop: record.shop,
        item: record.item,
        listing_strategy: record.listing_strategy,
        first_period_start: record.first_period_start
      }
    });
  }

  function closeListingEditor() {
    setEditingListing(null);
    restoreDialogFocus();
  }

  function openVoidListing(record: ListingRecord) {
    rememberDialogFocus();
    setVoidingListing({ record, reason: "" });
  }

  function closeVoidListing() {
    setVoidingListing(null);
    restoreDialogFocus();
  }

  function addListingDraft(task: PendingListingTask) {
    setListingDrafts((current) => ({
      ...current,
      [task.task_key]: [
        ...(current[task.task_key] || []),
        { shop: "", item: "", listing_strategy: "", first_period_start: task.default_first_period_start }
      ]
    }));
  }

  function updateListingDraft(taskKey: string, index: number, field: keyof ListingDraft, value: string) {
    setListingDrafts((current) => ({
      ...current,
      [taskKey]: (current[taskKey] || []).map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row)
    }));
    setListingErrors((current) => ({
      ...current,
      [taskKey]: (current[taskKey] || []).map((error, rowIndex) => rowIndex === index ? { ...error, [field]: undefined } : error)
    }));
  }

  function removeListingDraft(taskKey: string, index: number) {
    setListingDrafts((current) => ({
      ...current,
      [taskKey]: (current[taskKey] || []).filter((_, rowIndex) => rowIndex !== index)
    }));
  }

  async function submitListingCorrection() {
    if (!editingListing) return;
    const errors = editingListing.hasMetrics
      ? { ...(!editingListing.draft.listing_strategy.trim() && { listing_strategy: "请填写刊登策略" }) }
      : validateListingDrafts([editingListing.draft])[0];
    setEditErrors(errors);
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      const draft = editingListing.draft;
      const patch: Record<string, string> = {};
      if (draft.listing_strategy.trim() !== editingListing.record.listing_strategy) patch.listing_strategy = draft.listing_strategy.trim();
      if (!editingListing.hasMetrics) {
        if (draft.shop.trim() !== editingListing.record.shop) patch.shop = draft.shop.trim();
        if (draft.item.trim() !== editingListing.record.item) patch.item = draft.item.trim();
        if (draft.first_period_start !== editingListing.record.first_period_start) patch.first_period_start = draft.first_period_start;
      }
      await api.updateListing(editingListing.record.id, patch);
      setEditingListing(null);
      restoreDialogFocus();
      props.onStatus(`${editingListing.record.item} 刊登信息已更新`);
      await loadWorkbench();
    } catch (error) {
      props.onStatus(errorMessage(error, "刊登信息更新失败"));
    } finally {
      setLoading(false);
    }
  }

  async function submitVoidListing() {
    if (!voidingListing) return;
    if (!voidingListing.reason.trim()) {
      props.onStatus("请填写作废原因");
      return;
    }
    setLoading(true);
    try {
      await api.updateListing(voidingListing.record.id, { status: "voided", void_reason: voidingListing.reason.trim() });
      setVoidingListing(null);
      restoreDialogFocus();
      props.onStatus(`${voidingListing.record.item} 已作废并保留历史`);
      await loadWorkbench();
    } catch (error) {
      props.onStatus(errorMessage(error, "刊登记录作废失败"));
    } finally {
      setLoading(false);
    }
  }

  async function submitListings(task: PendingListingTask) {
    const rows = listingDrafts[task.task_key] || [];
    const errors = validateListingDrafts(rows);
    setListingErrors((current) => ({ ...current, [task.task_key]: errors }));
    if (!rows.length || errors.some((entry) => Object.keys(entry).length)) {
      props.onStatus(rows.length ? "请修正标红的刊登信息后再提交" : "请先新增一条刊登记录");
      return;
    }
    setLoading(true);
    try {
      await api.createListingsBatch({
        task_key: task.task_key,
        rows: rows.map((row) => ({
          shop: row.shop.trim(),
          item: row.item.trim(),
          listing_strategy: row.listing_strategy.trim(),
          first_period_start: row.first_period_start
        }))
      });
      setListingDrafts((current) => ({ ...current, [task.task_key]: [] }));
      props.onStatus(`${task.main_sku} 刊登记录已提交`);
      await loadWorkbench();
    } catch (error) {
      const rowErrors = mapServerRowErrors(error);
      if (Object.keys(rowErrors).length) {
        setListingErrors((current) => ({
          ...current,
          [task.task_key]: rows.map((_, index) => rowErrors[index] || {})
        }));
        props.onStatus("提交失败，请修正标红行；本批次没有写入数据");
      } else {
        props.onStatus(errorMessage(error, "刊登记录提交失败"));
      }
    } finally {
      setLoading(false);
    }
  }

  function updateReview(periodId: string, patch: Partial<ObservationReviewDraft>) {
    setReviewDrafts((current) => ({ ...current, [periodId]: { ...current[periodId], ...patch } }));
    setReviewErrors((current) => {
      const next = { ...current };
      delete next[periodId];
      return next;
    });
  }

  async function submitReviews() {
    const rows = visibleRows.filter((row) => visibleSelectedIds.includes(row.id)).map((row) => reviewDrafts[row.id] || reviewDraft(row));
    if (!rows.length) {
      props.onStatus("请先勾选要提交的周期");
      return;
    }
    const errors = validateObservationReviews(rows);
    setReviewErrors(errors);
    if (Object.keys(errors).length) {
      const missingSummary = rows.find((row) => errors[row.period_id]?.four_week_summary);
      if (missingSummary) openSummary(missingSummary.period_id);
      props.onStatus("请补全已选周期的必填内容后再提交");
      return;
    }
    setLoading(true);
    try {
      await api.reviewListingPeriods({
        rows: rows.map((row) => ({
          period_id: row.period_id,
          product_positioning: row.product_positioning as ProductPositioning,
          optimization_action: row.optimization_action.trim(),
          four_week_summary: row.four_week_summary.trim() || null
        }))
      });
      setSelectedPeriods([]);
      props.onStatus(`已提交 ${rows.length} 条周期复盘`);
      await loadWorkbench();
    } catch (error) {
      const rowErrors = mapReviewServerRowErrors(error, rows);
      if (Object.keys(rowErrors).length) {
        setReviewErrors(rowErrors);
        const summaryErrorId = Object.keys(rowErrors).find((periodId) => rowErrors[periodId].four_week_summary);
        if (summaryErrorId) openSummary(summaryErrorId);
        props.onStatus("周期复盘提交失败，请修正标红行；本批次没有写入数据");
      } else {
        props.onStatus(errorMessage(error, "周期复盘提交失败；本批次没有写入数据"));
      }
    } finally {
      setLoading(false);
    }
  }

  async function changeListingTracking(record: ListingRecord) {
    const next = record.tracking_status === "active" ? "stopped" : "active";
    setLoading(true);
    try {
      await api.updateListing(record.id, { tracking_status: next });
      props.onStatus(next === "stopped" ? `${record.item} 已停止跟踪` : `${record.item} 已恢复跟踪`);
      await loadWorkbench();
    } catch (error) {
      props.onStatus(errorMessage(error, "跟踪状态更新失败"));
    } finally {
      setLoading(false);
    }
  }

  async function changeTracking(row: ObservationPeriodRow) {
    const record = data.listing_records.find((listing) => listing.id === row.listing_record_id);
    if (record) await changeListingTracking(record);
  }

  async function submitNewPeriod() {
    if (!newPeriod?.periodStart) {
      props.onStatus("请选择新增周期的开始日期");
      return;
    }
    setLoading(true);
    try {
      await api.addListingPeriod(newPeriod.listingId, { period_start: newPeriod.periodStart });
      closeNewPeriod();
      props.onStatus("后续周期已新增");
      await loadWorkbench();
    } catch (error) {
      props.onStatus(errorMessage(error, "新增周期失败"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="listing-workbench" ref={workbenchRoot} tabIndex={-1}>
      <div className="listing-filters">
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
        <label className="listing-search">
          关键词
          <input value={filters.query} onChange={(event) => setFilter("query", event.target.value)} placeholder="主 SKU / Item / 商品名称" />
        </label>
        <label>
          国家
          <select value={filters.country} onChange={(event) => setFilter("country", event.target.value)}>
            <option value="">全部</option>
            {countries.map((country) => <option value={country} key={country}>{country}</option>)}
          </select>
        </label>
        {props.role === "manager" && (
          <label>
            负责人
            <select value={filters.salesperson_name} onChange={(event) => setFilter("salesperson_name", event.target.value)}>
              <option value="">全部</option>
              {owners.map((owner) => <option value={owner} key={owner}>{owner}</option>)}
            </select>
          </label>
        )}
        <label>
          业务周期
          <input type="date" value={filters.period_start} onChange={(event) => setFilter("period_start", event.target.value)} />
        </label>
        <label>
          店铺
          <input value={filters.shop} onChange={(event) => setFilter("shop", event.target.value)} placeholder="包含匹配" />
        </label>
        <label>
          周期处理状态
          <select value={filters.status} onChange={(event) => setFilter("status", event.target.value)}>
            <option value="">全部</option>
            <option value="pending_review">待复盘</option>
            <option value="completed">本周已复盘</option>
          </select>
        </label>
        <button className="btn" type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>
          清空筛选
        </button>
        <button className="btn" type="button" onClick={() => void loadWorkbench()} disabled={loading}>
          <RefreshCw size={14} />刷新
        </button>
        <button className="btn" type="button" onClick={() => setAdvancedOpen((open) => !open)}>
          高级筛选{advancedOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {advancedOpen && (
        <div className="listing-advanced-filters">
          <label>
            周次
            <select value={filters.week_number} onChange={(event) => setFilter("week_number", event.target.value ? Number(event.target.value) : "")}>
              <option value="">全部</option>
              {[1, 2, 3, 4].map((week) => <option value={week} key={week}>第 {week} 周</option>)}
              <option value="5">第 5 周及以后</option>
            </select>
          </label>
          <label>
            产品定位
            <select value={filters.product_positioning} onChange={(event) => setFilter("product_positioning", event.target.value)}>
              <option value="">全部</option>
              {PRODUCT_POSITIONINGS.map((positioning) => <option value={positioning} key={positioning}>{positioning}</option>)}
            </select>
          </label>
          <label>
            跟踪状态
            <select value={filters.tracking_status} onChange={(event) => setFilter("tracking_status", event.target.value)}>
              <option value="">全部</option>
              <option value="active">正常跟踪</option>
              <option value="stopped">停止跟踪</option>
            </select>
          </label>
        </div>
      )}

      <div id="listing-workbench-panel" className="listing-workbench-panel">
        {props.canManage && props.role === "operator" && !props.operatorName ? (
          <div className="empty-state">请先选择运营</div>
        ) : (
          <>
            <div className="listing-batchbar">
              <span>当前显示 {visibleRows.length} 条 Item 周期</span>
              <button className="btn primary" type="button" disabled={loading || !visibleSelectedIds.length} onClick={() => void submitReviews()}>
                提交已选复盘（{visibleSelectedIds.length}）
              </button>
            </div>
            <div className="listing-table-scroll">
              <table className="listing-period-table listing-grouped-table">
                <thead>
                  <tr>
                    <th className="listing-sticky sticky-0">
                      <input
                        type="checkbox"
                        aria-label="选择当前页全部待复盘周期"
                        checked={allReviewableSelected}
                        onChange={(event) => setSelectedPeriods((current) => event.target.checked
                          ? unique([...current, ...reviewableIds])
                          : current.filter((id) => !reviewableIds.includes(id)))}
                      />
                    </th>
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
                      {group.periodRows.map((row) => {
                        const draft = reviewDrafts[row.id] || reviewDraft(row);
                        const listing = listingById.get(row.listing_record_id);
                        const editable = canReview(row, listing);
                        const isLastPeriod = latestPeriodIds[row.listing_record_id] === row.id;
                        return (
                          <tr key={row.id}>
                            <td className="listing-sticky sticky-0">
                              {editable && (
                                <input
                                  type="checkbox"
                                  aria-label={`选择 ${row.item} 第 ${row.week_number} 周`}
                                  checked={selectedPeriods.includes(row.id)}
                                  onChange={(event) => setSelectedPeriods((current) => event.target.checked
                                    ? unique([...current, row.id])
                                    : current.filter((id) => id !== row.id))}
                                />
                              )}
                            </td>
                            <td className="listing-sticky sticky-1"><b>{row.main_sku}</b><small>{row.main_sku_name || "-"}</small></td>
                            <td className="listing-sticky sticky-2">{row.shop}</td>
                            <td className="listing-sticky sticky-3"><b>{row.item}</b><small>{row.country || "-"}{row.tracking_status === "stopped" ? " · 停止跟踪" : ""}</small></td>
                            <td className="listing-sticky sticky-4">{row.salesperson_name}</td>
                            <td className="listing-sticky sticky-5">第 {row.week_number} 周</td>
                            <td className="listing-sticky sticky-6">{row.period_start}<small>至 {row.period_end}</small></td>
                            <td><span className={`pill ${periodStatusClass(row, listing)}`}>{periodStatusLabel(row, listing)}</span></td>
                            <td>{row.status === "pending_data" ? "-" : formatObservationMetric(row.order_count)}</td>
                            <td>{row.status === "pending_data" ? "-" : formatObservationMetric(row.total_revenue)}</td>
                            <td>{row.status === "pending_data" ? "-" : formatObservationMetric(row.gross_profit_amount)}</td>
                            <td>{row.status === "pending_data" ? "-" : formatPercent(row.gross_profit_rate)}</td>
                            <td>
                              {editable ? (
                                <>
                                  <select
                                    className={reviewErrors[row.id]?.product_positioning ? "listing-error-input" : ""}
                                    value={draft.product_positioning}
                                    onChange={(event) => updateReview(row.id, { product_positioning: event.target.value as ProductPositioning | "" })}
                                  >
                                    <option value="">请选择</option>
                                    {PRODUCT_POSITIONINGS.map((positioning) => <option value={positioning} key={positioning}>{positioning}</option>)}
                                  </select>
                                  <FieldError message={reviewErrors[row.id]?.product_positioning} />
                                </>
                              ) : draft.product_positioning || "-"}
                            </td>
                            <td>
                              {editable ? (
                                <>
                                  <textarea
                                    className={reviewErrors[row.id]?.optimization_action ? "listing-error-input" : ""}
                                    value={draft.optimization_action}
                                    onChange={(event) => updateReview(row.id, { optimization_action: event.target.value })}
                                    placeholder="填写本周期优化操作"
                                  />
                                  <FieldError message={reviewErrors[row.id]?.optimization_action} />
                                </>
                              ) : draft.optimization_action || "-"}
                            </td>
                            <td className="listing-row-actions">
                              <FieldError message={reviewErrors[row.id]?.period_id} />
                              {row.week_number === 4 && row.status !== "pending_data" && (
                                <button className="btn small" type="button" onClick={() => openSummary(row.id)}>
                                  {draft.four_week_summary ? "查看总结" : "填写总结"}
                                </button>
                              )}
                              {isLastPeriod && listing?.status === "active" && (
                                <button className="btn small" type="button" disabled={loading} onClick={() => void changeTracking(row)}>
                                  {row.tracking_status === "active" ? "停止跟踪" : "恢复跟踪"}
                                </button>
                              )}
                              {isLastPeriod && listing?.status === "active" && row.first_round_completed_at && (
                                <button
                                  className="btn small"
                                  type="button"
                                  onClick={() => openNewPeriod(row.listing_record_id)}
                                >
                                  <Plus size={13} />新增周期
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              {!visibleGroups.length && (
                <div className="empty-state">
                  {filters.business_status === "pending_listing"
                    ? "当前没有待刊登主 SKU，可选择全部查看观察记录"
                    : "没有符合条件的 Item 周期"}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {summaryRow && (
        <div className="listing-overlay">
          <div
            className="listing-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-summary-title"
            tabIndex={-1}
            ref={summaryDialog}
            onKeyDown={(event) => handleDialogKeyDown(event, closeSummary)}
          >
            <button aria-label="关闭四周总结" className="listing-dialog-close" type="button" onClick={closeSummary}><X size={18} /></button>
            <h2 id="listing-summary-title">{summaryRow.item} · 四周总结</h2>
            <p>第 4 周的定位、优化操作和四周总结一起提交。</p>
            <textarea
              className={reviewErrors[summaryRow.id]?.four_week_summary ? "listing-error-input" : ""}
              value={(reviewDrafts[summaryRow.id] || reviewDraft(summaryRow)).four_week_summary}
              disabled={!canReview(summaryRow, summaryListing)}
              onChange={(event) => updateReview(summaryRow.id, { four_week_summary: event.target.value })}
              placeholder="总结首轮四周表现、主要问题和后续动作"
            />
            <FieldError message={reviewErrors[summaryRow.id]?.four_week_summary} />
            <div className="listing-dialog-actions">
              <button className="btn primary" type="button" onClick={closeSummary}>
                {canReview(summaryRow, summaryListing) ? "保存填写" : "关闭"}
              </button>
            </div>
          </div>
        </div>
      )}

      {newPeriod && (
        <div className="listing-overlay">
          <div
            className="listing-dialog small-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-period-title"
            tabIndex={-1}
            ref={newPeriodDialog}
            onKeyDown={(event) => handleDialogKeyDown(event, closeNewPeriod)}
          >
            <button aria-label="关闭新增周期" className="listing-dialog-close" type="button" onClick={closeNewPeriod}><X size={18} /></button>
            <h2 id="listing-period-title">新增后续周期</h2>
            <label>
              周期开始日
              <input type="date" value={newPeriod.periodStart} onChange={(event) => setNewPeriod({ ...newPeriod, periodStart: event.target.value })} />
            </label>
            <div className="listing-dialog-actions">
              <button className="btn" type="button" onClick={closeNewPeriod}>取消</button>
              <button className="btn primary" type="button" disabled={loading} onClick={() => void submitNewPeriod()}>确认新增</button>
            </div>
          </div>
        </div>
      )}

      {editingListing && (
        <div className="listing-overlay">
          <div
            className="listing-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-edit-title"
            tabIndex={-1}
            ref={editDialog}
            onKeyDown={(event) => handleDialogKeyDown(event, closeListingEditor)}
          >
            <button aria-label="关闭刊登纠错" className="listing-dialog-close" type="button" onClick={closeListingEditor}><X size={18} /></button>
            <h2 id="listing-edit-title">{editingListing.record.item} · 刊登纠错</h2>
            {editingListing.hasMetrics && <p>已产生周数据：仅允许修正刊登策略；换店或换 Item 请作废旧记录后新增。</p>}
            <div className="listing-edit-grid">
              <label>店铺<input disabled={editingListing.hasMetrics} value={editingListing.draft.shop} onChange={(event) => setEditingListing({ ...editingListing, draft: { ...editingListing.draft, shop: event.target.value } })} /></label>
              <label>Item<input disabled={editingListing.hasMetrics} value={editingListing.draft.item} onChange={(event) => setEditingListing({ ...editingListing, draft: { ...editingListing.draft, item: event.target.value } })} /></label>
              <label>第一周起始周期<input disabled={editingListing.hasMetrics} type="date" value={editingListing.draft.first_period_start} onChange={(event) => setEditingListing({ ...editingListing, draft: { ...editingListing.draft, first_period_start: event.target.value } })} /></label>
              <label>刊登策略<textarea value={editingListing.draft.listing_strategy} onChange={(event) => setEditingListing({ ...editingListing, draft: { ...editingListing.draft, listing_strategy: event.target.value } })} /></label>
            </div>
            <FieldError message={editErrors.shop || editErrors.item || editErrors.first_period_start || editErrors.listing_strategy} />
            <div className="listing-dialog-actions">
              <button className="btn" type="button" onClick={closeListingEditor}>取消</button>
              <button className="btn primary" type="button" disabled={loading} onClick={() => void submitListingCorrection()}>保存纠错</button>
            </div>
          </div>
        </div>
      )}

      {voidingListing && (
        <div className="listing-overlay">
          <div
            className="listing-dialog small-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="listing-void-title"
            tabIndex={-1}
            ref={voidDialog}
            onKeyDown={(event) => handleDialogKeyDown(event, closeVoidListing)}
          >
            <button aria-label="关闭作废确认" className="listing-dialog-close" type="button" onClick={closeVoidListing}><X size={18} /></button>
            <h2 id="listing-void-title">作废 {voidingListing.record.item}</h2>
            <p>旧记录与周期历史会保留；换店、换 Item 或重新刊登后，请在同一主 SKU 下新增一条。</p>
            <label>作废原因<textarea value={voidingListing.reason} onChange={(event) => setVoidingListing({ ...voidingListing, reason: event.target.value })} /></label>
            <div className="listing-dialog-actions">
              <button className="btn" type="button" onClick={closeVoidListing}>取消</button>
              <button className="btn primary" type="button" disabled={loading} onClick={() => void submitVoidListing()}>确认作废</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function ListingObservationSummary(props: {
  mainSku: string;
  country?: string | null;
  role: "operator" | "manager";
  operatorName: string;
  canManage: boolean;
}) {
  const [data, setData] = useState<ListingWorkbenchResponse>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useRef(createRequestGate());

  useEffect(() => {
    const requestId = requestGate.current.start();
    setLoading(true);
    setError("");
    void api.listingSummary(
      props.mainSku,
      props.country,
      summarySalespersonScope(props.role, props.canManage, props.operatorName)
    ).then((response) => {
      if (requestGate.current.isCurrent(requestId)) setData(response);
    }).catch((reason) => {
      if (requestGate.current.isCurrent(requestId)) setError(errorMessage(reason, "刊登与观察汇总加载失败"));
    }).finally(() => {
      if (requestGate.current.isCurrent(requestId)) setLoading(false);
    });
  }, [props.mainSku, props.country, props.role, props.operatorName, props.canManage]);

  const summary = useMemo(() => productListingSummary(data, props.mainSku, props.country), [data, props.country, props.mainSku]);
  const periods = useMemo(() => sortObservationRows(summary.periods), [summary.periods]);

  if (loading) return <p className="muted detail-empty">正在加载刊登与观察记录...</p>;
  if (error) return <p className="muted detail-empty">{error}</p>;
  if (!summary.listings.length) return <p className="muted detail-empty">暂无刊登与观察记录。</p>;
  return (
    <div className="listing-summary-readonly">
      <div className="listing-summary-cards">
        {summary.listings.map((listing) => (
          <div className="listing-summary-card" key={listing.id}>
            <b>{listing.shop} · {listing.item}</b>
            <span>刊登策略：{listing.listing_strategy}</span>
            <span>首周：{listing.first_period_start}</span>
            <span>{listingStatusLabel(listing)}</span>
          </div>
        ))}
      </div>
      <div className="listing-table-scroll">
        <table className="detail-table listing-summary-table">
          <thead><tr><th>店铺 / Item</th><th>周次</th><th>业务周期</th><th>订单量</th><th>总收入</th><th>一次毛利额</th><th>一次毛利率</th><th>产品定位</th><th>优化操作</th><th>四周总结</th></tr></thead>
          <tbody>
            {periods.map((period) => (
              <tr key={period.id}>
                <td>{period.shop}<br /><b>{period.item}</b></td>
                <td>第 {period.week_number} 周</td>
                <td>{period.period_start} 至 {period.period_end}</td>
                <td>{period.status === "pending_data" ? "-" : formatObservationMetric(period.order_count)}</td>
                <td>{period.status === "pending_data" ? "-" : formatObservationMetric(period.total_revenue)}</td>
                <td>{period.status === "pending_data" ? "-" : formatObservationMetric(period.gross_profit_amount)}</td>
                <td>{period.status === "pending_data" ? "-" : formatPercent(period.gross_profit_rate)}</td>
                <td>{period.product_positioning || "-"}</td>
                <td>{period.optimization_action || "-"}</td>
                <td>{period.four_week_summary || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PendingListingTasks(props: {
  tasks: PendingListingTask[];
  records: ListingRecord[];
  periods: ObservationPeriodRow[];
  drafts: Record<string, ListingDraft[]>;
  errors: Record<string, ListingDraftErrors[]>;
  loading: boolean;
  onAdd: (task: PendingListingTask) => void;
  onUpdate: (taskKey: string, index: number, field: keyof ListingDraft, value: string) => void;
  onRemove: (taskKey: string, index: number) => void;
  onSubmit: (task: PendingListingTask) => void;
  onEdit: (record: ListingRecord) => void;
  onTracking: (record: ListingRecord) => void;
  onVoid: (record: ListingRecord) => void;
  canVoid: boolean;
}) {
  if (!props.tasks.length) return <div className="empty-state">点击“新增店铺 + Item”开始填写刊登信息。</div>;
  return (
    <div className="pending-listing-tasks">
      {props.tasks.map((task) => {
        const rows = props.drafts[task.task_key] || [];
        const errors = props.errors[task.task_key] || [];
        const records = props.records.filter((record) => record.task_key === task.task_key);
        return (
          <section className="pending-listing-card" key={task.task_key}>
            <div className="pending-listing-head">
              <div>
                <b>{task.main_sku}</b>
                <span>{task.main_sku_name || "未填写主 SKU 名称"}</span>
              </div>
              <div className="pending-listing-meta">
                <span>{task.country || task.site || "-"}</span>
                <span>{task.salesperson_name}</span>
                <span>{task.business_period || "-"}</span>
              </div>
              <button className="btn" type="button" onClick={() => props.onAdd(task)}><Plus size={14} />新增店铺 + Item</button>
            </div>
            {records.length > 0 && (
              <div className="listing-existing-records">
                <b>已有刊登记录</b>
                <div className="pending-listing-table-scroll">
                  <table className="pending-listing-table listing-existing-table">
                    <thead><tr><th>店铺</th><th>Item</th><th>刊登策略</th><th>起始周期</th><th>状态</th><th>操作</th></tr></thead>
                    <tbody>
                      {records.map((record) => (
                        <tr key={record.id}>
                          <td>{record.shop}</td>
                          <td>{record.item}</td>
                          <td>{record.listing_strategy}</td>
                          <td>{record.first_period_start}</td>
                          <td>{listingStatusLabel(record)}</td>
                          <td className="listing-row-actions">
                            {record.status === "active" && <button className="btn small" type="button" onClick={() => props.onEdit(record)}>纠错</button>}
                            {record.status === "active" && <button className="btn small" type="button" onClick={() => props.onTracking(record)}>{record.tracking_status === "active" ? "停止跟踪" : "恢复跟踪"}</button>}
                            {props.canVoid && record.status === "active" && <button className="btn small" type="button" onClick={() => props.onVoid(record)}>作废</button>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {rows.length ? (
              <div className="pending-listing-table-scroll">
                <table className="pending-listing-table">
                  <thead><tr><th>店铺 *</th><th>Item *</th><th>刊登策略 *</th><th>第一周起始周期 *</th><th /></tr></thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={index}>
                        <td><input aria-label={`${task.main_sku} 第 ${index + 1} 条店铺`} className={errors[index]?.shop ? "listing-error-input" : ""} value={row.shop} onChange={(event) => props.onUpdate(task.task_key, index, "shop", event.target.value)} /><FieldError message={errors[index]?.shop} /></td>
                        <td><input aria-label={`${task.main_sku} 第 ${index + 1} 条 Item`} className={errors[index]?.item ? "listing-error-input" : ""} value={row.item} onChange={(event) => props.onUpdate(task.task_key, index, "item", event.target.value)} /><FieldError message={errors[index]?.item} /></td>
                        <td><textarea aria-label={`${task.main_sku} 第 ${index + 1} 条刊登策略`} className={errors[index]?.listing_strategy ? "listing-error-input" : ""} value={row.listing_strategy} onChange={(event) => props.onUpdate(task.task_key, index, "listing_strategy", event.target.value)} placeholder="自由填写刊登策略" /><FieldError message={errors[index]?.listing_strategy} /></td>
                        <td><input aria-label={`${task.main_sku} 第 ${index + 1} 条第一周起始周期`} className={errors[index]?.first_period_start ? "listing-error-input" : ""} type="date" value={row.first_period_start} onChange={(event) => props.onUpdate(task.task_key, index, "first_period_start", event.target.value)} /><FieldError message={errors[index]?.first_period_start} /></td>
                        <td><button className="icon-btn" type="button" aria-label={`删除 ${task.main_sku} 第 ${index + 1} 条`} title="删除本行" onClick={() => props.onRemove(task.task_key, index)}><Trash2 size={15} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="pending-listing-empty">点击“新增店铺 + Item”，填写店铺、Item、刊登策略和第一周起始周期。</div>}
            <div className="pending-listing-submit">
              <span>同一主 SKU 可新增多条；任一行校验失败，整批都不会写入。</span>
              <button className="btn primary" type="button" disabled={props.loading || !rows.length} onClick={() => props.onSubmit(task)}>
                一键提交 {rows.length || ""} 条
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function reviewDraft(row: ObservationPeriodRow): ObservationReviewDraft {
  return {
    period_id: row.id,
    week_number: row.week_number,
    product_positioning: row.product_positioning || "",
    optimization_action: row.optimization_action || "",
    four_week_summary: row.four_week_summary || ""
  };
}

function canReview(row: ObservationPeriodRow, listing?: ListingRecord) {
  return listing?.status === "active"
    && row.status === "pending_review"
    && row.tracking_status === "active";
}

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

function listingStatusLabel(record: ListingRecord) {
  if (record.status === "voided") return "已作废";
  if (record.tracking_status === "stopped") return "停止跟踪";
  if (record.first_round_completed_at) return "首轮观察完成";
  return "观察中";
}

function FieldError({ message }: { message?: string }) {
  return message ? <small className="listing-field-error">{message}</small> : null;
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>, onClose: () => void) {
  if (event.key === "Escape") {
    event.preventDefault();
    onClose();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
  ));
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && (document.activeElement === first || document.activeElement === event.currentTarget)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === event.currentTarget)) {
    event.preventDefault();
    first.focus();
  }
}
