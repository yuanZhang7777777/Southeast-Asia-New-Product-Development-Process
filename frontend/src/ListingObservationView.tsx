import { ChevronDown, ChevronUp, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  api,
  ListingRecord,
  ListingWorkbenchResponse,
  ObservationPeriodRow,
  PendingListingTask
} from "./api";
import {
  buildListingWorkbenchGroups,
  canEditObservationPeriod,
  clearListingDrafts,
  clearObservationReviewDraft,
  createObservationReviewDraft,
  createRequestGate,
  defaultNextBusinessPeriodStart,
  expectedObservationMetricsDate,
  filterListingWorkbenchGroups,
  filterObservationRows,
  formatObservationMetric,
  formatPercent,
  hasFetchedMetrics,
  ListingDraft,
  ListingDraftErrors,
  mapReviewServerRowErrors,
  mapServerRowErrors,
  ObservationFilters,
  ObservationReviewDraft,
  ObservationReviewErrors,
  observationPeriodDisplay,
  PRODUCT_POSITIONINGS,
  ProductPositioning,
  productListingSummaryByBusinessPeriod,
  resolveWorkbenchScope,
  restoreListingDrafts,
  restoreObservationReviewDraft,
  saveListingDrafts,
  saveObservationReviewDraft,
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
  draftUserId: string;
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
  const workbenchScopeKey = JSON.stringify([props.draftUserId, props.role, props.canManage, props.operatorName]);
  const workbenchScopeKeyRef = useRef(workbenchScopeKey);
  workbenchScopeKeyRef.current = workbenchScopeKey;
  const requestGate = useRef(createRequestGate());
  const submittedListingDraftKeys = useRef(new Set<string>());
  const submittedPeriodDraftKeys = useRef(new Set<string>());
  const workbenchRoot = useRef<HTMLDivElement | null>(null);
  const dialogReturnFocus = useRef<HTMLElement | null>(null);
  const summaryDialog = useRef<HTMLDivElement | null>(null);
  const newPeriodDialog = useRef<HTMLDivElement | null>(null);
  const editDialog = useRef<HTMLDivElement | null>(null);
  const voidDialog = useRef<HTMLDivElement | null>(null);

  async function loadWorkbench() {
    if (workbenchScopeKey !== workbenchScopeKeyRef.current) return;
    const requestId = requestGate.current.start();
    const isCurrent = () => requestGate.current.isCurrent(requestId)
      && workbenchScopeKeyRef.current === workbenchScopeKey;
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
      if (!isCurrent()) return;
      const storage = browserStorage();
      const taskKeys = unique([
        ...response.pending_listing_tasks.map((task) => task.task_key),
        ...response.listing_records.map((listing) => listing.task_key)
      ]);
      setData(response);
      setSelectedPeriods([]);
      setListingDrafts(Object.fromEntries(taskKeys.map((taskKey) => [
        taskKey,
        storage ? restoreListingDrafts(
          storage,
          props.draftUserId,
          taskKey,
          [],
          submittedListingDraftKeys.current.has(taskKey)
        ) : []
      ])));
      setReviewDrafts(Object.fromEntries(response.period_rows.map((row) => [
        row.id,
        storage ? restoreObservationReviewDraft(
          storage,
          props.draftUserId,
          row,
          submittedPeriodDraftKeys.current.has(row.id)
        ) : createObservationReviewDraft(row)
      ])));
    } catch (error) {
      if (isCurrent()) props.onStatus(errorMessage(error, "刊登与观察工作台加载失败"));
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }

  useEffect(() => {
    void loadWorkbench();
  }, [props.role, props.canManage, props.operatorName, props.draftUserId]);

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
      const matchedRows = sortObservationRows(filterObservationRows(group.periodRows, effectiveFilters));
      const periodRows = matchedRows.filter((row) => observationPeriodDisplay(row) !== "hidden");
      const text = effectiveFilters.query?.trim().toLocaleLowerCase();
      const contextMatches = !text || [group.context.main_sku, group.context.main_sku_name]
        .some((value) => value?.toLocaleLowerCase().includes(text));
      const commonMatches = (!effectiveFilters.country || group.context.country === effectiveFilters.country)
        && (!effectiveFilters.salesperson_name || group.context.salesperson_name === effectiveFilters.salesperson_name);
      if (!commonMatches) return [];
      if (group.pendingListing && !group.periodRows.length) {
        return contextMatches && !hasPeriodFilters ? [{ ...group, periodRows: [] }] : [];
      }
      const matchedListingIds = new Set((hasPeriodFilters ? periodRows : matchedRows).map((row) => row.listing_record_id));
      const listings = !hasPeriodFilters && contextMatches
        ? group.listings
        : group.listings.filter((listing) => matchedListingIds.has(listing.id));
      return listings.length || (group.pendingListing && contextMatches && !hasPeriodFilters)
        ? [{ ...group, listings, periodRows }]
        : [];
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
  const editableRows = visibleRows.filter((row) => canEditObservationPeriod(row, listingById.get(row.listing_record_id)));
  const pendingReviewIds = editableRows.filter((row) => row.status === "pending_review").map((row) => row.id);
  const visibleSelectedIds = visibleSelectedPeriodIds(selectedPeriods, editableRows);
  const allPendingReviewSelected = pendingReviewIds.length > 0 && pendingReviewIds.every((id) => visibleSelectedIds.includes(id));
  const summaryRow = data.period_rows.find((row) => row.id === summaryPeriodId) || null;
  const summaryListing = summaryRow ? listingById.get(summaryRow.listing_record_id) : undefined;

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
    submittedListingDraftKeys.current.delete(task.task_key);
    setListingDrafts((current) => {
      const rows = [
        ...(current[task.task_key] || []),
        { shop: "", item: "", listing_strategy: "", first_period_start: task.default_first_period_start }
      ];
      const storage = browserStorage();
      if (storage) saveListingDrafts(storage, props.draftUserId, task.task_key, rows);
      return { ...current, [task.task_key]: rows };
    });
  }

  function updateListingDraft(taskKey: string, index: number, field: keyof ListingDraft, value: string) {
    submittedListingDraftKeys.current.delete(taskKey);
    setListingDrafts((current) => {
      const rows = (current[taskKey] || []).map((row, rowIndex) => rowIndex === index ? { ...row, [field]: value } : row);
      const storage = browserStorage();
      if (storage) saveListingDrafts(storage, props.draftUserId, taskKey, rows);
      return { ...current, [taskKey]: rows };
    });
    setListingErrors((current) => ({
      ...current,
      [taskKey]: (current[taskKey] || []).map((error, rowIndex) => rowIndex === index ? { ...error, [field]: undefined } : error)
    }));
  }

  function removeListingDraft(taskKey: string, index: number) {
    submittedListingDraftKeys.current.delete(taskKey);
    setListingDrafts((current) => {
      const rows = (current[taskKey] || []).filter((_, rowIndex) => rowIndex !== index);
      const storage = browserStorage();
      if (storage) saveListingDrafts(storage, props.draftUserId, taskKey, rows);
      return { ...current, [taskKey]: rows };
    });
  }

  function captureWorkbenchScope() {
    const capturedScopeKey = workbenchScopeKey;
    return () => workbenchScopeKeyRef.current === capturedScopeKey;
  }

  async function submitListingCorrection() {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
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
      if (!isCurrentScope()) return;
      setEditingListing(null);
      restoreDialogFocus();
      props.onStatus(`${editingListing.record.item} 刊登信息已更新`);
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
      props.onStatus(errorMessage(error, "刊登信息更新失败"));
    } finally {
      if (isCurrentScope()) setLoading(false);
    }
  }

  async function submitVoidListing() {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
    if (!voidingListing) return;
    if (!voidingListing.reason.trim()) {
      props.onStatus("请填写作废原因");
      return;
    }
    setLoading(true);
    try {
      await api.updateListing(voidingListing.record.id, { status: "voided", void_reason: voidingListing.reason.trim() });
      if (!isCurrentScope()) return;
      setVoidingListing(null);
      restoreDialogFocus();
      props.onStatus(`${voidingListing.record.item} 已作废并保留历史`);
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
      props.onStatus(errorMessage(error, "刊登记录作废失败"));
    } finally {
      if (isCurrentScope()) setLoading(false);
    }
  }

  async function submitListings(task: PendingListingTask) {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
    const rows = listingDrafts[task.task_key] || [];
    const reuseListingIds = task.requires_confirmation ? task.reusable_listing_ids : [];
    const errors = validateListingDrafts(rows);
    setListingErrors((current) => ({ ...current, [task.task_key]: errors }));
    if ((!rows.length && !reuseListingIds.length) || errors.some((entry) => Object.keys(entry).length)) {
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
        })),
        reuse_listing_ids: reuseListingIds
      });
      const storage = browserStorage();
      submittedListingDraftKeys.current.add(task.task_key);
      if (storage) clearListingDrafts(storage, props.draftUserId, task.task_key);
      if (!isCurrentScope()) return;
      setListingDrafts((current) => {
        const next = { ...current };
        delete next[task.task_key];
        return next;
      });
      setListingErrors((current) => {
        const next = { ...current };
        delete next[task.task_key];
        return next;
      });
      props.onStatus(`${task.main_sku} 刊登记录已提交`);
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
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
      if (isCurrentScope()) setLoading(false);
    }
  }

  function updateReview(periodId: string, patch: Partial<ObservationReviewDraft>) {
    submittedPeriodDraftKeys.current.delete(periodId);
    setReviewDrafts((current) => {
      const draft = { ...current[periodId], ...patch };
      const storage = browserStorage();
      if (storage) saveObservationReviewDraft(storage, props.draftUserId, periodId, draft);
      return { ...current, [periodId]: draft };
    });
    setReviewErrors((current) => {
      const next = { ...current };
      delete next[periodId];
      return next;
    });
  }

  async function submitReviews() {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
    const rows = visibleRows.filter((row) => visibleSelectedIds.includes(row.id)).map((row) => reviewDrafts[row.id] || createObservationReviewDraft(row));
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
      const storage = browserStorage();
      for (const row of rows) {
        submittedPeriodDraftKeys.current.add(row.period_id);
        if (storage) clearObservationReviewDraft(storage, props.draftUserId, row.period_id);
      }
      if (!isCurrentScope()) return;
      setReviewDrafts((current) => {
        const next = { ...current };
        for (const row of rows) delete next[row.period_id];
        return next;
      });
      setReviewErrors((current) => {
        const next = { ...current };
        for (const row of rows) delete next[row.period_id];
        return next;
      });
      setSelectedPeriods([]);
      props.onStatus(`已提交 ${rows.length} 条周期复盘`);
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
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
      if (isCurrentScope()) setLoading(false);
    }
  }

  async function changeListingTracking(record: ListingRecord) {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
    const next = record.tracking_status === "active" ? "stopped" : "active";
    setLoading(true);
    try {
      await api.updateListing(record.id, { tracking_status: next });
      if (!isCurrentScope()) return;
      props.onStatus(next === "stopped" ? `${record.item} 已停止跟踪` : `${record.item} 已恢复跟踪`);
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
      props.onStatus(errorMessage(error, "跟踪状态更新失败"));
    } finally {
      if (isCurrentScope()) setLoading(false);
    }
  }

  async function submitNewPeriod() {
    const isCurrentScope = captureWorkbenchScope();
    if (!isCurrentScope()) return;
    if (!newPeriod?.periodStart) {
      props.onStatus("请选择新增周期的开始日期");
      return;
    }
    setLoading(true);
    try {
      await api.addListingPeriod(newPeriod.listingId, { period_start: newPeriod.periodStart });
      if (!isCurrentScope()) return;
      closeNewPeriod();
      props.onStatus("后续周期已新增");
      await loadWorkbench();
    } catch (error) {
      if (!isCurrentScope()) return;
      props.onStatus(errorMessage(error, "新增周期失败"));
    } finally {
      if (isCurrentScope()) setLoading(false);
    }
  }

  return (
    <div className="listing-workbench" ref={workbenchRoot} tabIndex={-1}>
      <div className="listing-workbench-header">
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
          <button className="btn" type="button" onClick={() => setFilters(DEFAULT_FILTERS)}>清空筛选</button>
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
              周期处理状态
              <select value={filters.status} onChange={(event) => setFilter("status", event.target.value)}>
                <option value="">全部</option>
                <option value="pending_review">待复盘</option>
                <option value="completed">本周已复盘</option>
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
        <div className="listing-batchbar">
          <label className="listing-select-all">
            <input
              type="checkbox"
              aria-label="选择当前结果全部待复盘周期"
              checked={allPendingReviewSelected}
              onChange={(event) => setSelectedPeriods((current) => event.target.checked
                ? unique([...current, ...pendingReviewIds])
                : current.filter((id) => !pendingReviewIds.includes(id)))}
            />
            选择全部待复盘
          </label>
          <span>当前显示 {visibleRows.length} 条周记录</span>
          <button className="btn primary" type="button" disabled={loading || !visibleSelectedIds.length} onClick={() => void submitReviews()}>
            提交选中周记录（{visibleSelectedIds.length}）
          </button>
        </div>
      </div>

      <div id="listing-workbench-panel" className="listing-workbench-panel listing-workbench-results">
        {props.canManage && props.role === "operator" && !props.operatorName ? (
          <div className="empty-state">请先选择运营</div>
        ) : visibleGroups.length ? visibleGroups.map((group) => {
          const expanded = expandedGroups.includes(group.context.task_key);
          return (
            <section className="listing-main-group" key={group.context.task_key}>
              <header className="listing-main-group-header">
                <button
                  type="button"
                  className="listing-group-toggle"
                  aria-expanded={expanded}
                  onClick={() => toggleGroup(group.context.task_key)}
                >
                  {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  <b>{group.context.main_sku}</b>
                  <span>{group.context.main_sku_name || "-"}</span>
                  <span>{group.context.country || group.context.site || "-"}</span>
                  <span>{group.context.salesperson_name}</span>
                  {group.pendingListing && <span className="pill amber">待刊登</span>}
                  <small>{group.listings.length} 个 Item</small>
                </button>
                <button type="button" className="btn small" onClick={() => {
                  setExpandedGroups((current) => current.includes(group.context.task_key)
                    ? current
                    : [...current, group.context.task_key]);
                  addListingDraft(group.context);
                }}>
                  <Plus size={13} />{group.pendingListing ? "填写刊登" : "新增店铺 + Item"}
                </button>
              </header>

              {expanded && (
                <div className="listing-main-group-content">
                  <PendingListingTasks
                    tasks={[group.context]}
                    drafts={listingDrafts}
                    errors={listingErrors}
                    loading={loading}
                    onAdd={addListingDraft}
                    onUpdate={updateListingDraft}
                    onRemove={removeListingDraft}
                    onSubmit={(task) => void submitListings(task)}
                  />

                  {group.listings.map((listing) => {
                    const rows = group.periodRows.filter((row) => row.listing_record_id === listing.id);
                    const completedWeeks = data.period_rows.filter((row) =>
                      row.listing_record_id === listing.id && row.status === "completed"
                    ).length;
                    return (
                      <article className="listing-item-card" key={listing.id}>
                        <header className="listing-item-header">
                          <div className="listing-item-identity">
                            <b>{listing.shop}</b>
                            <strong>{listing.item}</strong>
                            <span>{listing.listing_strategy}</span>
                          </div>
                          <div className="listing-item-meta">
                            <span>首周 {listing.first_period_start}</span>
                            <span className="pill gray">{listingStatusLabel(listing)}</span>
                            <span>已完成 {completedWeeks} 周</span>
                          </div>
                          <details className="listing-more-menu">
                            <summary>更多</summary>
                            <div>
                              {listing.status === "active" && <button type="button" onClick={() => openListingEditor(listing)}>纠错</button>}
                              {listing.status === "active" && <button type="button" disabled={loading} onClick={() => void changeListingTracking(listing)}>{listing.tracking_status === "active" ? "停止跟踪" : "恢复跟踪"}</button>}
                              {listing.status === "active" && listing.first_round_completed_at && <button type="button" onClick={() => openNewPeriod(listing.id)}>新增周期</button>}
                              {props.canManage && listing.status === "active" && <button type="button" onClick={() => openVoidListing(listing)}>作废</button>}
                            </div>
                          </details>
                        </header>

                        {rows.length ? (
                          <div className="listing-period-list">
                            {rows.map((row) => {
                              const display = observationPeriodDisplay(row);
                              if (display !== "ready") {
                                return (
                                  <div className={`listing-period-notice ${display}`} key={row.id}>
                                    <b>第 {row.week_number} 周{display === "in_progress" ? "进行中" : "已结束"}</b>
                                    <span>{row.period_start} 至 {row.period_end}</span>
                                    <span>{display === "in_progress"
                                      ? `预计 ${expectedObservationMetricsDate(row.period_end)} 获取数据`
                                      : "数据准备中"}</span>
                                  </div>
                                );
                              }
                              const draft = reviewDrafts[row.id] || createObservationReviewDraft(row);
                              const editable = canEditObservationPeriod(row, listing);
                              return (
                                <section className="listing-period-card" key={row.id}>
                                  <div className="listing-period-overview">
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
                                    <div className="listing-period-title">
                                      <b>第 {row.week_number} 周</b>
                                      <span>{row.period_start} 至 {row.period_end}</span>
                                      <span className={`pill ${periodStatusClass(row, listing)}`}>{periodStatusLabel(row, listing)}</span>
                                    </div>
                                    <div className="listing-period-metrics">
                                      <div><span>订单量</span><b>{formatObservationMetric(row.order_count)}</b></div>
                                      <div><span>总收入</span><b>{formatObservationMetric(row.total_revenue)}</b></div>
                                      <div><span>一次毛利额</span><b>{formatObservationMetric(row.gross_profit_amount)}</b></div>
                                      <div><span>一次毛利率</span><b>{formatPercent(row.gross_profit_rate)}</b></div>
                                    </div>
                                  </div>
                                  <div className="listing-period-review">
                                    <label>
                                      产品定位 *
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
                                      ) : <span>{draft.product_positioning || "-"}</span>}
                                    </label>
                                    <label className="listing-optimization-field">
                                      优化操作 *
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
                                      ) : <span>{draft.optimization_action || "-"}</span>}
                                    </label>
                                    <div className="listing-period-actions">
                                      <FieldError message={reviewErrors[row.id]?.period_id} />
                                      {row.week_number === 4 && (
                                        <button className="btn small" type="button" onClick={() => openSummary(row.id)}>
                                          {draft.four_week_summary ? "查看总结" : "填写总结"}
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                </section>
                              );
                            })}
                          </div>
                        ) : <p className="listing-item-empty">尚无已开始的观察周期。</p>}
                      </article>
                    );
                  })}
                </div>
              )}
            </section>
          );
        }) : (
          <div className="empty-state">
            {filters.business_status === "pending_listing"
              ? "当前没有待刊登主 SKU，可选择全部查看观察记录"
              : "没有符合条件的刊登或周记录"}
          </div>
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
              value={(reviewDrafts[summaryRow.id] || createObservationReviewDraft(summaryRow)).four_week_summary}
              disabled={!canEditObservationPeriod(summaryRow, summaryListing)}
              onChange={(event) => updateReview(summaryRow.id, { four_week_summary: event.target.value })}
              placeholder="总结首轮四周表现、主要问题和后续动作"
            />
            <FieldError message={reviewErrors[summaryRow.id]?.four_week_summary} />
            <div className="listing-dialog-actions">
              <button className="btn primary" type="button" onClick={closeSummary}>
                {canEditObservationPeriod(summaryRow, summaryListing) ? "保存填写" : "关闭"}
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
  currentBusinessPeriod?: string | null;
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

  const summaryGroups = useMemo(() => productListingSummaryByBusinessPeriod(
    data,
    props.mainSku,
    props.country,
    props.currentBusinessPeriod
  ), [data, props.country, props.currentBusinessPeriod, props.mainSku]);

  if (loading) return <p className="muted detail-empty">正在加载刊登与观察记录...</p>;
  if (error) return <p className="muted detail-empty">{error}</p>;
  if (!summaryGroups.length) return <p className="muted detail-empty">暂无刊登与观察记录。</p>;
  return (
    <div className="listing-summary-readonly">
      {summaryGroups.map((group, index) => (
        <details key={group.business_period || "未标记业务期"} open={index === 0}>
          <summary>{group.business_period || "未标记业务期"} · {group.listings.length} 个 Item</summary>
          <div className="listing-summary-items">
            {group.listings.map((listing) => {
              const periods = sortObservationRows(group.periods.filter((period) =>
                period.listing_record_id === listing.id && observationPeriodDisplay(period) !== "hidden"
              ));
              return (
                <article className="listing-item-card listing-summary-item" key={listing.id}>
                  <header className="listing-item-header">
                    <div className="listing-item-identity">
                      <b>{listing.shop}</b>
                      <strong>{listing.item}</strong>
                      <span>{listing.listing_strategy}</span>
                    </div>
                    <div className="listing-item-meta">
                      <span>负责人 {listing.salesperson_name}</span>
                      <span>首周 {listing.first_period_start}</span>
                      <span className="pill gray">{listingStatusLabel(listing)}</span>
                    </div>
                  </header>
                  {periods.length ? (
                    <div className="listing-period-list">
                      {periods.map((period) => {
                        const display = observationPeriodDisplay(period);
                        if (display !== "ready") {
                          return (
                            <div className={`listing-period-notice ${display}`} key={period.id}>
                              <b>第 {period.week_number} 周{display === "in_progress" ? "进行中" : "已结束"}</b>
                              <span>{period.period_start} 至 {period.period_end}</span>
                              <span>{display === "in_progress"
                                ? `预计 ${expectedObservationMetricsDate(period.period_end)} 获取数据`
                                : "数据准备中"}</span>
                            </div>
                          );
                        }
                        return (
                          <section className="listing-period-card" key={period.id}>
                            <div className="listing-period-overview">
                              <div className="listing-period-title">
                                <b>第 {period.week_number} 周</b>
                                <span>{period.period_start} 至 {period.period_end}</span>
                                <span className={`pill ${periodStatusClass(period, listing)}`}>{periodStatusLabel(period, listing)}</span>
                              </div>
                              <div className="listing-period-metrics">
                                <div><span>订单量</span><b>{formatObservationMetric(period.order_count)}</b></div>
                                <div><span>总收入</span><b>{formatObservationMetric(period.total_revenue)}</b></div>
                                <div><span>一次毛利额</span><b>{formatObservationMetric(period.gross_profit_amount)}</b></div>
                                <div><span>一次毛利率</span><b>{formatPercent(period.gross_profit_rate)}</b></div>
                              </div>
                            </div>
                            <dl className="listing-summary-review">
                              <div><dt>产品定位</dt><dd>{period.product_positioning || "-"}</dd></div>
                              <div><dt>优化操作</dt><dd>{period.optimization_action || "-"}</dd></div>
                              {period.four_week_summary && <div><dt>四周总结</dt><dd>{period.four_week_summary}</dd></div>}
                            </dl>
                          </section>
                        );
                      })}
                    </div>
                  ) : <p className="listing-item-empty">尚无已开始的观察周期。</p>}
                </article>
              );
            })}
          </div>
        </details>
      ))}
    </div>
  );
}

function PendingListingTasks(props: {
  tasks: PendingListingTask[];
  drafts: Record<string, ListingDraft[]>;
  errors: Record<string, ListingDraftErrors[]>;
  loading: boolean;
  onAdd: (task: PendingListingTask) => void;
  onUpdate: (taskKey: string, index: number, field: keyof ListingDraft, value: string) => void;
  onRemove: (taskKey: string, index: number) => void;
  onSubmit: (task: PendingListingTask) => void;
}) {
  if (!props.tasks.length) return null;
  return (
    <div className="pending-listing-tasks">
      {props.tasks.map((task) => {
        const rows = props.drafts[task.task_key] || [];
        const errors = props.errors[task.task_key] || [];
        const reuseCount = task.requires_confirmation ? task.reusable_listing_ids.length : 0;
        if (!rows.length && !reuseCount) return null;
        return (
          <section className="pending-listing-card listing-draft-panel" key={task.task_key}>
            <div className="listing-draft-head">
              <b>新增刊登记录</b>
              <button className="btn small" type="button" onClick={() => props.onAdd(task)}><Plus size={13} />新增一行</button>
            </div>
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
            ) : null}
            <div className="pending-listing-submit">
              <span>{reuseCount ? `将沿用 ${reuseCount} 个现有 Item；` : ""}同一主 SKU 可新增多条；任一行校验失败，整批都不会写入。</span>
              <button className="btn primary" type="button" disabled={props.loading || (!rows.length && !reuseCount)} onClick={() => props.onSubmit(task)}>
                {reuseCount ? `确认沿用现有 Item${rows.length ? ` + 新增 ${rows.length} 条` : ""}` : `一键提交 ${rows.length || ""} 条`}
              </button>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function periodStatusLabel(row: ObservationPeriodRow, listing?: ListingRecord) {
  if (listing?.status === "voided") return "已作废";
  const stopped = listing?.tracking_status === "stopped" || row.tracking_status === "stopped";
  if (stopped && row.status === "pending_review") return "停止跟踪 · 待复盘";
  if (stopped) return "停止跟踪";
  if (row.status === "pending_data") return "观察中";
  if (row.status === "pending_review") return "待复盘";
  return "本周已复盘";
}

function periodStatusClass(row: ObservationPeriodRow, listing?: ListingRecord) {
  if (listing?.status === "voided" || row.status === "pending_data") return "gray";
  if (row.status === "pending_review") return "amber";
  if (listing?.tracking_status === "stopped" || row.tracking_status === "stopped") return "gray";
  return "green";
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

function browserStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
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
