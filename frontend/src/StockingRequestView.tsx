import { useEffect, useMemo, useState } from "react";
import { Download, Plus, RefreshCw, Save, Send, Trash2, X } from "lucide-react";

import {
  api,
  AvailableStockingItem,
  ExportPeriodSummary,
  OperatorStockingItem,
  SalesSelfSelectionPayload,
  StockingRequestUpdate
} from "./api";
import {
  buildStockingExportPayload,
  groupStockingItems,
  stockingQuantity,
  stockingFormVisible,
  stockingStatusLabel,
  StockingDraft,
  StockingDraftErrors,
  validateStockingDraft
} from "./stockingRequests";

type RoleKey = "operator" | "manager";
type DecisionKey = "stock" | "inventory" | "pause";
type SelfChild = { sub_sku: string; sub_sku_name: string; decision: DecisionKey };

type Props = {
  role: RoleKey;
  operatorItems: OperatorStockingItem[];
  managerRows: AvailableStockingItem[];
  periods: ExportPeriodSummary[];
  onReload: () => Promise<void>;
  onStatus: (message: string) => void;
};

const emptySelfChild = (): SelfChild => ({ sub_sku: "", sub_sku_name: "", decision: "stock" });

export function StockingRequestView(props: Props) {
  return props.role === "operator" ? <OperatorStockingView {...props} /> : <ManagerStockingView {...props} />;
}

function OperatorStockingView({ operatorItems, onReload, onStatus }: Props) {
  const [selfOpen, setSelfOpen] = useState(false);
  const [selfForm, setSelfForm] = useState({ main_sku: "", main_sku_name: "", country: "", children: [emptySelfChild()] });
  const [filters, setFilters] = useState({ query: "", status: "", source: "", country: "" });
  const [drafts, setDrafts] = useState<Record<string, StockingDraft>>({});
  const [errors, setErrors] = useState<Record<string, StockingDraftErrors>>({});
  const [busy, setBusy] = useState("");

  useEffect(() => {
    setDrafts((current) => Object.fromEntries(operatorItems.flatMap((item) => item.request_id ? [[item.request_id, current[item.request_id] || requestDraft(item)]] : [])));
  }, [operatorItems]);

  const filteredItems = useMemo(() => operatorItems.filter((item) => {
    const needle = filters.query.trim().toLowerCase();
    if (filters.status && item.downstream_status !== filters.status && item.request?.status !== filters.status) return false;
    if (filters.source && item.source_type !== filters.source) return false;
    if (filters.country && (item.request?.country || "") !== filters.country) return false;
    return !needle || `${item.main_sku} ${item.main_sku_name || ""} ${item.sub_sku} ${item.sub_sku_name || ""}`.toLowerCase().includes(needle);
  }), [filters, operatorItems]);

  const groups = groupStockingItems(filteredItems).sort((left, right) => groupPriority(left.items) - groupPriority(right.items));
  const statuses = unique(operatorItems.flatMap((item) => [item.downstream_status, item.request?.status || ""]));
  const sources = unique(operatorItems.map((item) => item.source_type));
  const countries = unique(operatorItems.map((item) => item.request?.country || ""));

  async function run(key: string, success: string, action: () => Promise<unknown>) {
    setBusy(key);
    try {
      await action();
      onStatus(success);
      await onReload();
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusy("");
    }
  }

  async function createSelfSelection() {
    const mainSku = selfForm.main_sku.trim();
    const country = selfForm.country.trim();
    const children = selfForm.children.map((child) => ({ ...child, sub_sku: child.sub_sku.trim(), sub_sku_name: child.sub_sku_name.trim() }));
    if (!mainSku || !country || children.some((child) => !child.sub_sku)) {
      onStatus("主 SKU、国家和每个子 SKU 必填");
      return;
    }
    if (new Set(children.map((child) => child.sub_sku)).size !== children.length) {
      onStatus("同一主 SKU 下的子 SKU 不能重复");
      return;
    }
    const payload: SalesSelfSelectionPayload = {
      main_sku: mainSku,
      main_sku_name: selfForm.main_sku_name.trim() || null,
      country,
      children: children.map((child) => ({
        sub_sku: child.sub_sku,
        sub_sku_name: child.sub_sku_name || null,
        ...decisionPayload(child.decision)
      }))
    };
    await run("self", "销售自选已创建", async () => {
      await api.createSalesSelfSelection(payload);
      setSelfForm({ main_sku: "", main_sku_name: "", country: "", children: [emptySelfChild()] });
      setSelfOpen(false);
    });
  }

  async function updateDecision(item: OperatorStockingItem, decision: DecisionKey) {
    await run(`decision:${item.claim_record_id}`, "备货决策已更新", () => api.updateStockingDecision(item.claim_record_id, decisionPayload(decision)));
  }

  function patchDraft(requestId: string, patch: Partial<StockingDraft>) {
    setDrafts((current) => ({ ...current, [requestId]: { ...current[requestId], ...patch } }));
    setErrors((current) => ({ ...current, [requestId]: {} }));
  }

  async function previewVolume(item: OperatorStockingItem) {
    if (!item.request_id) return;
    setBusy(`volume:${item.request_id}`);
    try {
      const [preview] = await api.volumePreview([item.sub_sku]);
      patchDraft(item.request_id, { unit_volume: preview?.unit_volume || null });
      onStatus(!preview || preview.status === "manual_required" ? "未取得体积，请手填" : "体积查询完成");
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "未取得体积，请手填");
    } finally {
      setBusy("");
    }
  }

  function payloadFor(requestId: string, salesSelf: boolean): StockingRequestUpdate | null {
    const draft = drafts[requestId];
    const nextErrors = validateStockingDraft(draft, salesSelf);
    setErrors((current) => ({ ...current, [requestId]: nextErrors }));
    if (Object.keys(nextErrors).length) return null;
    return {
      application_date: draft.application_date,
      request_type: draft.request_type,
      cost_price: Number(draft.cost_price),
      unit_volume: Number(draft.unit_volume),
      daily_sales: Number(draft.daily_sales),
      country: draft.country.trim(),
      warehouse: draft.warehouse?.trim() || null,
      reason: draft.reason?.trim() || null
    };
  }

  async function saveRequest(item: OperatorStockingItem, submit: boolean) {
    if (!item.request_id) return;
    const payload = payloadFor(item.request_id, item.source_type === "sales_self_selection");
    if (!payload) {
      onStatus("请先修正申请字段");
      return;
    }
    await run(`${submit ? "submit" : "save"}:${item.request_id}`, submit ? "申请已提交" : "草稿已保存", async () => {
      await api.updateStockingRequest(item.request_id!, payload);
      if (submit) await api.submitStockingRequest(item.request_id!);
    });
  }

  return (
    <div className="stocking-workbench stocking-operator">
      <div className="stocking-toolbar">
        <div className="stocking-filters">
          <input placeholder="搜索主 SKU / 子 SKU" value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} />
          <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
            <option value="">全部状态</option>
            {statuses.map((status) => <option key={status} value={status}>{stockingStatusLabel(status)}</option>)}
          </select>
          <select value={filters.source} onChange={(event) => setFilters({ ...filters, source: event.target.value })}>
            <option value="">全部来源</option>
            {sources.map((source) => <option key={source} value={source}>{sourceLabel(source)}</option>)}
          </select>
          <select value={filters.country} onChange={(event) => setFilters({ ...filters, country: event.target.value })}>
            <option value="">全部国家</option>
            {countries.map((country) => <option key={country} value={country}>{country}</option>)}
          </select>
        </div>
        <button className="btn primary" type="button" onClick={() => setSelfOpen(true)}><Plus size={15} />销售自选</button>
      </div>

      <div className="stocking-group-list">
        {!groups.length && <div className="empty-small">暂无备货申请</div>}
        {groups.map((group) => (
          <section className="stocking-main-card" key={group.main_sku}>
            <header><div><b>{group.main_sku}</b><span>{group.items[0]?.main_sku_name || ""}</span></div><span>{group.items.length} 个子 SKU</span></header>
            <div className="stocking-item-list">
              {group.items.map((item) => {
                const draft = item.request_id ? drafts[item.request_id] : undefined;
                const itemErrors = item.request_id ? errors[item.request_id] || {} : {};
                const readOnly = item.request?.status === "exported";
                const isSalesSelf = item.source_type === "sales_self_selection";
                const decisionReadOnly = !isSalesSelf || Boolean(item.request?.submitted_at) || ["submitted", "exported"].includes(item.request?.status || "");
                const showRequest = stockingFormVisible(item);
                return (
                  <article className="stocking-item-card" key={item.claim_record_id}>
                    <div className="stocking-item-context">
                      <div><b>{item.sub_sku}</b><span>{item.sub_sku_name || ""}</span></div>
                      <div className="tag-row"><span className="tag">{sourceLabel(item.source_type)}</span><span className="pill blue">{stockingStatusLabel(item.request?.status || item.downstream_status)}</span></div>
                      {isSalesSelf ? (
                        <div className="stocking-decision-buttons">
                          <button className={item.needs_stocking ? "btn small blue" : "btn small"} disabled={decisionReadOnly || busy !== ""} onClick={() => void updateDecision(item, "stock")}>需要备货</button>
                          <button className={item.inventory_available && !item.needs_stocking ? "btn small blue" : "btn small"} disabled={decisionReadOnly || busy !== ""} onClick={() => void updateDecision(item, "inventory")}>有库存，不备货</button>
                          <button className={item.inventory_available === false && item.needs_stocking === false ? "btn small blue" : "btn small"} disabled={decisionReadOnly || busy !== ""} onClick={() => void updateDecision(item, "pause")}>无库存，不备货</button>
                        </div>
                      ) : <span>主管复核已通过</span>}
                    </div>
                    <div className="stocking-item-form">
                      {showRequest && draft ? (
                        <>
                          <div className="stocking-request-form-grid">
                            <Field label="申请日期" error={itemErrors.application_date}><input type="date" value={draft.application_date} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { application_date: event.target.value })} /></Field>
                            <Field label="备货类型"><select value={draft.request_type} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { request_type: event.target.value as StockingDraft["request_type"] })}><option value="initial">首次备货</option><option value="replenishment">补货</option></select></Field>
                            <Field label="成本价" error={itemErrors.cost_price}><input type="number" min="0" step="0.01" value={draft.cost_price ?? ""} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { cost_price: numberOrNull(event.target.value) })} /></Field>
                            <Field label="单个体积（m³）" error={itemErrors.unit_volume}><div className="stocking-volume-field"><input type="number" min="0" step="0.000001" value={draft.unit_volume ?? ""} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { unit_volume: numberOrNull(event.target.value) })} /><button className="btn small" type="button" disabled={readOnly || busy !== ""} onClick={() => void previewVolume(item)}><RefreshCw size={13} />ERP 查询</button></div></Field>
                            <Field label="备货单销" error={itemErrors.daily_sales}><input type="number" min="0" step="0.01" value={draft.daily_sales ?? ""} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { daily_sales: numberOrNull(event.target.value) })} /></Field>
                            <Field label="备货数量（自动）"><input value={draft.daily_sales ? stockingQuantity(draft.daily_sales) : ""} readOnly /></Field>
                            <Field label="备货国家" error={itemErrors.country}><input value={draft.country} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { country: event.target.value })} /></Field>
                            <Field label="备货仓库（可空）"><input value={draft.warehouse || ""} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { warehouse: event.target.value })} /></Field>
                            {draft.request_type === "replenishment" && <Field label="补货原因" error={itemErrors.reason} wide><textarea value={draft.reason || ""} disabled={readOnly} onChange={(event) => patchDraft(item.request_id!, { reason: event.target.value })} /></Field>}
                          </div>
                          {!readOnly && <div className="stocking-form-actions"><button className="btn" disabled={busy !== ""} onClick={() => void saveRequest(item, false)}><Save size={14} />保存草稿</button><button className="btn primary" disabled={busy !== ""} onClick={() => void saveRequest(item, true)}><Send size={14} />提交申请</button></div>}
                        </>
                      ) : (
                        <div className="stocking-branch-result">
                          <b>{item.downstream_status === "waiting_listing" ? "直接进入待刊登" : item.downstream_status === "stocking_paused" ? "暂不推进" : "请选择备货决策"}</b>
                          <span>{item.downstream_status === "stocking_paused" ? "后续可点击“需要备货”恢复申请。" : "无需填写正式备货申请。"}</span>
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {selfOpen && (
        <div className="stocking-overlay" role="dialog" aria-modal="true">
          <div className="stocking-dialog">
            <header><div><h2>销售自选</h2><p>一次创建一个主 SKU，并逐子 SKU 选择后续分支。</p></div><button className="btn" onClick={() => setSelfOpen(false)}><X size={16} /></button></header>
            <div className="stocking-self-main">
              <Field label="主 SKU"><input value={selfForm.main_sku} onChange={(event) => setSelfForm({ ...selfForm, main_sku: event.target.value })} /></Field>
              <Field label="主 SKU 名称"><input value={selfForm.main_sku_name} onChange={(event) => setSelfForm({ ...selfForm, main_sku_name: event.target.value })} /></Field>
              <Field label="国家"><input value={selfForm.country} onChange={(event) => setSelfForm({ ...selfForm, country: event.target.value })} /></Field>
            </div>
            <div className="stocking-self-children">
              {selfForm.children.map((child, index) => (
                <div className="stocking-self-child" key={index}>
                  <input placeholder="子 SKU" value={child.sub_sku} onChange={(event) => patchSelfChild(index, { sub_sku: event.target.value }, selfForm, setSelfForm)} />
                  <input placeholder="子 SKU 名称" value={child.sub_sku_name} onChange={(event) => patchSelfChild(index, { sub_sku_name: event.target.value }, selfForm, setSelfForm)} />
                  <select value={child.decision} onChange={(event) => patchSelfChild(index, { decision: event.target.value as DecisionKey }, selfForm, setSelfForm)}><option value="stock">需要备货</option><option value="inventory">有库存，不备货</option><option value="pause">无库存，不备货</option></select>
                  <button className="btn" disabled={selfForm.children.length === 1} onClick={() => setSelfForm({ ...selfForm, children: selfForm.children.filter((_, childIndex) => childIndex !== index) })}><Trash2 size={14} /></button>
                </div>
              ))}
              <button className="btn" onClick={() => setSelfForm({ ...selfForm, children: [...selfForm.children, emptySelfChild()] })}><Plus size={14} />增加子 SKU</button>
            </div>
            <footer><button className="btn" onClick={() => setSelfOpen(false)}>取消</button><button className="btn primary" disabled={busy !== ""} onClick={() => void createSelfSelection()}>创建销售自选</button></footer>
          </div>
        </div>
      )}
    </div>
  );
}

function ManagerStockingView({ managerRows, periods, onReload, onStatus }: Props) {
  const [period, setPeriod] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setPeriod((current) => current && periods.some((item) => item.business_period === current) ? current : periods[0]?.business_period || "");
  }, [periods]);

  const filteredRows = managerRows.filter((row) => {
    if (period && row.business_period !== period) return false;
    if (status && row.status !== status) return false;
    const needle = query.trim().toLowerCase();
    return !needle || `${row.main_sku} ${row.sub_sku} ${row.salesperson_name || ""}`.toLowerCase().includes(needle);
  });
  const filteredIds = filteredRows.map((row) => row.request_id);
  const allSelected = Boolean(filteredIds.length) && filteredIds.every((id) => selected.includes(id));

  async function exportTraceability() {
    if (!period) return;
    try {
      setBusy(true);
      await api.traceabilityExport({ business_period: period });
      onStatus(`已导出 ${period} 中央字段追溯表`);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }
  async function exportSelected() {
    try {
      setBusy(true);
      await api.availableStockingExport(buildStockingExportPayload(selected));
      onStatus(`已导出 ${selected.length} 条申请`);
      setSelected([]);
      await onReload();
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stocking-workbench stocking-manager">
      <div className="stocking-periods">
        {periods.map((item) => (
          <button className={item.business_period === period ? "stocking-period active" : "stocking-period"} key={item.business_period} onClick={() => { setPeriod(item.business_period); setSelected([]); }}>
            <b>{item.business_period}</b><span>待导出 {item.stocking_count} · 追溯 {item.traceability_count}</span>
          </button>
        ))}
        {!periods.length && <span className="muted">暂无可导出的业务期数</span>}
        {!!period && <button className="btn" disabled={busy || !periods.find((item) => item.business_period === period)?.traceability_count} onClick={() => void exportTraceability()}><Download size={14} />导出中央追溯表</button>}
      </div>
      <div className="stocking-manager-toolbar">
        <label className="stocking-select-all"><input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? selected.filter((id) => !filteredIds.includes(id)) : unique([...selected, ...filteredIds]))} />全选当前筛选</label>
        <select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">全部状态</option>{unique(managerRows.map((row) => row.status)).map((item) => <option key={item} value={item}>{stockingStatusLabel(item)}</option>)}</select>
        <input placeholder="搜索 SKU / 运营" value={query} onChange={(event) => setQuery(event.target.value)} />
        <span>已选 {selected.length} 条</span>
        <button className="btn primary" disabled={!selected.length || busy} onClick={() => void exportSelected()}><Download size={14} />导出选中</button>
      </div>
      <div className="stocking-export-scroll">
        <table className="stocking-export-table">
          <thead><tr><th>操作状态</th><th>申请日期</th><th>备货类型</th><th>选品数据源</th><th>销售员</th><th>主 SKU</th><th>子 SKU</th><th>成本价</th><th>单个体积</th><th>备货单销</th><th>备货数量</th><th>备货国家</th><th>备货仓库</th><th>货值</th><th>体积</th><th>补货原因</th></tr></thead>
          <tbody>
            {!filteredRows.length && <tr><td colSpan={16}>{period ? "当前筛选下暂无待导出申请" : "请选择业务期数"}</td></tr>}
            {filteredRows.map((row) => (
              <tr key={row.request_id}>
                <td><label className="stocking-row-check"><input type="checkbox" checked={selected.includes(row.request_id)} onChange={() => setSelected((current) => current.includes(row.request_id) ? current.filter((id) => id !== row.request_id) : [...current, row.request_id])} />{row.operation_status}</label></td>
                <td>{row.application_date || ""}</td><td>{row.stocking_type}</td><td>{row.selection_source}</td><td>{row.salesperson_name || ""}</td><td>{row.main_sku}</td><td>{row.sub_sku}</td><td>{row.cost_price ?? ""}</td><td>{row.unit_volume ?? ""}</td><td>{row.claim_daily_sales}</td><td>{row.quantity}</td><td>{row.stocking_country || ""}</td><td>{row.warehouse || ""}</td><td>{row.amount ?? ""}</td><td>{row.volume ?? ""}</td><td>{row.replenishment_reason || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Field({ label, error, wide = false, children }: { label: string; error?: string; wide?: boolean; children: React.ReactNode }) {
  return <label className={wide ? "stocking-field wide" : "stocking-field"}><span>{label}</span>{children}{error && <small>{error}</small>}</label>;
}

function requestDraft(item: OperatorStockingItem): StockingDraft {
  return {
    application_date: item.request?.application_date || new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" }),
    request_type: item.request?.request_type || "initial",
    cost_price: item.request?.cost_price ?? null,
    unit_volume: item.request?.unit_volume ?? null,
    daily_sales: item.request?.daily_sales ?? null,
    country: item.request?.country || "",
    warehouse: item.request?.warehouse || "",
    reason: item.request?.reason || ""
  };
}

function decisionPayload(decision: DecisionKey) {
  if (decision === "inventory") return { inventory_available: true, needs_stocking: false };
  if (decision === "pause") return { inventory_available: false, needs_stocking: false };
  return { inventory_available: false, needs_stocking: true };
}

function patchSelfChild(index: number, patch: Partial<SelfChild>, form: { main_sku: string; main_sku_name: string; country: string; children: SelfChild[] }, setForm: (value: typeof form) => void) {
  setForm({ ...form, children: form.children.map((child, childIndex) => childIndex === index ? { ...child, ...patch } : child) });
}

function numberOrNull(value: string) {
  return value === "" ? null : Number(value);
}

function sourceLabel(source: string) {
  if (source === "sales_self_selection") return "销售自选";
  if (source === "selection1") return "选品1";
  if (source === "selection2_caigen_claim_feedback") return "选品2/财根";
  return source;
}

function groupPriority(items: OperatorStockingItem[]) {
  return items.some((item) => ["waiting_stocking_request", "draft"].includes(item.request?.status || item.downstream_status)) ? 0 : 1;
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}
