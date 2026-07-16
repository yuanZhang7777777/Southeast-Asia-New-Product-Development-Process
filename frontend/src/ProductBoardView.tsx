import { ChevronDown, ChevronRight, ClipboardPen, Search, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useState } from "react";

import { API_BASE, api, getAuthToken, ProductBoardGroup } from "./api";
import { formatBusinessNumber } from "./businessFormat";
import {
  buildProductBoardRows,
  filterProductBoardRows,
  hasMultipleOwners,
  ProductBoardFilters,
  ProductBoardRow,
  productBoardStatusLabel,
  productBoardStatusMeta,
  unique
} from "./productBoard";

type RoleKey = "operator" | "manager";

export function ProductBoardView({
  role,
  operatorName,
  onOpenDetail,
  onOpenResearch
}: {
  role: RoleKey;
  operatorName: string;
  onOpenDetail: (opportunityId: string) => void;
  onOpenResearch: () => void;
}) {
  const [groups, setGroups] = useState<ProductBoardGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [filters, setFilters] = useState<ProductBoardFilters>({});

  useEffect(() => {
    if (role === "operator" && !operatorName.trim()) {
      setGroups([]);
      setLoading(false);
      setError("Operator name missing; no product board data loaded.");
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .productBoard()
      .then((items) => {
        if (!cancelled) setGroups(items);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message || "商品看板加载失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [role, operatorName]);

  const rows = useMemo(() => buildProductBoardRows(groups), [groups]);
  const effectiveFilters = role === "operator" ? { ...filters, owner: operatorName.trim() } : filters;
  const visibleRows = useMemo(() => filterProductBoardRows(rows, effectiveFilters), [rows, effectiveFilters]);
  const options = useMemo(() => buildOptions(rows), [rows]);

  return (
    <div className="product-board">
      <div className="product-board-filters">
        <label className="product-board-search">
          <Search size={15} />
          <input value={filters.query || ""} onChange={(event) => setFilters({ ...filters, query: event.target.value })} placeholder="搜索主 SKU / 子 SKU / 商品名 / 负责人" />
        </label>
        <select value={filters.businessPeriod || ""} onChange={(event) => setFilters({ ...filters, businessPeriod: event.target.value })}>
          <option value="">全部期数</option>
          {options.businessPeriods.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        {role === "manager" ? (
          <select value={filters.owner || ""} onChange={(event) => setFilters({ ...filters, owner: event.target.value })}>
            <option value="">全部负责人</option>
            {options.owners.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        ) : (
          <span className="tag">负责人：我</span>
        )}
        <select value={filters.status || ""} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
          <option value="">全部状态</option>
          {options.statuses.map((item) => <option key={item} value={item}>{productBoardStatusLabel(item)}</option>)}
        </select>
        <input type="date" value={filters.arrivalDate || ""} onChange={(event) => setFilters({ ...filters, arrivalDate: event.target.value })} />
        <select value={filters.site || ""} onChange={(event) => setFilters({ ...filters, site: event.target.value })}>
          <option value="">全部站点</option>
          {options.sites.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <button className="btn" type="button" onClick={() => setFilters({})}>
          <X size={14} />
          清空
        </button>
      </div>

      {error && <div className="notice red">{error}</div>}
      <div className="dashboard-summary">
        <span className="tag">主 SKU 组：{visibleRows.length} / {rows.length}</span>
        <span className="tag">责任明细：{visibleRows.reduce((sum, row) => sum + row.responsibilities.length, 0)}</span>
        {loading && <span className="tag">加载中...</span>}
      </div>

      <div className="product-board-table-wrap">
        <table className="product-board-table">
          <thead>
            <tr>
              <th>主 SKU</th>
              <th>期数</th>
              <th>站点</th>
              <th>子 SKU</th>
              <th>已分配运营</th>
              <th>状态</th>
              <th>标签</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {!visibleRows.length && (
              <tr>
                <td colSpan={8}>当前条件下没有商品</td>
              </tr>
            )}
            {visibleRows.map((row) => {
              const firstOpportunityId = row.child_skus[0]?.opportunity_id || "";
              return (
                <Fragment key={row.key}>
                  <tr>
                    <td>
                      <div className="product-board-product">
                        <button className="product-board-expand" type="button" onClick={() => setExpanded((current) => ({ ...current, [row.key]: !current[row.key] }))} title="展开子 SKU">
                          {expanded[row.key] ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                        </button>
                        <ProductBoardThumb url={row.image_url} name={row.main_sku_name || row.main_sku} />
                        <button className="product-board-title" type="button" onClick={() => firstOpportunityId && onOpenDetail(firstOpportunityId)}>
                          <b>{row.main_sku}</b>
                          <small>{row.main_sku_name || "-"}</small>
                        </button>
                      </div>
                    </td>
                    <td>{row.business_period || "-"}</td>
                    <td>{row.site || row.country || "-"}</td>
                    <td>{row.childCount}</td>
                    <td>{row.ownersText}</td>
                    <td>{row.statuses.map((item) => <StatusPill key={item} status={item} />)}</td>
                    <td>{hasMultipleOwners(row) && <span className="pill blue">多人认领</span>}</td>
                    <td>
                      <button className="btn small" type="button" disabled={!firstOpportunityId} onClick={() => onOpenDetail(firstOpportunityId)}>
                        详情
                      </button>
                      {row.statuses.includes("waiting_secondary_research") && (
                        <button className="btn small primary" type="button" onClick={onOpenResearch}>
                          <ClipboardPen size={13} />
                          二次调研
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded[row.key] && (
                    <tr className="product-board-detail-row">
                      <td colSpan={8}>
                        <ChildSkuTable row={row} onOpenDetail={onOpenDetail} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChildSkuTable({ row, onOpenDetail }: { row: ProductBoardRow; onOpenDetail: (opportunityId: string) => void }) {
  return (
    <table className="product-board-child-table">
      <thead>
        <tr>
          <th>子 SKU</th>
          <th>名称</th>
          <th>负责人</th>
          <th>认领单销</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        {row.child_skus.map((child) => {
          const responsibilities = row.responsibilities.filter((item) => item.opportunity_id === child.opportunity_id);
          const owners = responsibilities.map((item) => item.salesperson_name).filter(Boolean).join("、") || "-";
          const claimDailySales = unique(
            responsibilities.map((item) => item.claim_daily_sales).filter((value): value is number => value != null).map(formatBusinessNumber)
          ).join("、") || "-";
          const statuses = responsibilities.length ? responsibilities.map((item) => item.visible_status) : [child.visible_status];
          return (
            <tr key={child.opportunity_id}>
              <td>
                <button className="text-link" type="button" onClick={() => onOpenDetail(child.opportunity_id)}>
                  {child.sub_sku}
                </button>
              </td>
              <td>{child.sub_sku_name || "-"}</td>
              <td>{owners}</td>
              <td>{claimDailySales}</td>
              <td>{unique(statuses).map((status) => <StatusPill key={status} status={status} />)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ProductBoardThumb({ url, name }: { url?: string | null; name: string }) {
  const src = imageSrc(url);
  const [open, setOpen] = useState(false);
  return (
    <>
      <span className="product-board-thumb">
        {src ? <img src={src} alt={name} onClick={(event) => {
          event.stopPropagation();
          setOpen(true);
        }} /> : "图"}
      </span>
      {open && src && (
        <div className="image-preview" role="dialog" aria-modal="true" onClick={() => setOpen(false)}>
          <button className="image-preview-close" type="button" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
          <img src={src} alt={name} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  );
}

function StatusPill({ status }: { status: string }) {
  const meta = productBoardStatusMeta[status] || { label: status, klass: "gray" };
  return <span className={`pill ${meta.klass}`}>{meta.label}</span>;
}

function buildOptions(rows: ProductBoardRow[]) {
  return {
    businessPeriods: unique(rows.map((row) => row.business_period).filter(Boolean) as string[]),
    owners: unique(rows.flatMap((row) => row.owners)),
    statuses: unique(rows.flatMap((row) => row.statuses)),
    sites: unique(rows.map((row) => row.site || row.country).filter(Boolean) as string[])
  };
}

function imageSrc(url?: string | null) {
  if (!url) return "";
  if (url.startsWith("/uploaded-sources/")) return `${API_BASE}${url}`;
  if (url.startsWith("https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com/")) {
    return `${API_BASE}/claims/evidence-images/proxy?url=${encodeURIComponent(url)}&token=${encodeURIComponent(getAuthToken())}`;
  }
  return url;
}
