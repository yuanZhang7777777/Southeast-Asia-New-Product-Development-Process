import { ClipboardEvent, CSSProperties, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, ImagePlus, Send, X } from "lucide-react";

import {
  API_BASE,
  api,
  getAuthToken,
  SecondaryResearchGroup,
  SecondaryResearchItem,
  UploadedEvidenceImage
} from "./api";
import {
  createSecondaryResearchDraft,
  incompleteSecondaryResearchItems,
  patchSecondaryResearchDraft,
  SECONDARY_RESEARCH_POSITIONINGS,
  SECONDARY_RESEARCH_SKIP_LISTING,
  syncSecondaryResearchDraftPatch,
  SecondaryResearchDraft
} from "./secondaryResearchDrafts";
import { isSourceClaimInputLabel, selection1ColumnLabel } from "./selection1Columns";
import { formatBusinessNumber } from "./businessFormat";
import { createKeyedSaveQueue, imageFiles } from "./imageUploads";

type ModuleKey = "secondary" | "market" | "pricing" | "development" | "cost" | "claims";

const modules: { key: ModuleKey; label: string }[] = [
  { key: "secondary", label: "二次调研" },
  { key: "market", label: "市场调研" },
  { key: "pricing", label: "价格 / 毛利" },
  { key: "development", label: "开发 / 包装" },
  { key: "cost", label: "成本 / 备货" },
  { key: "claims", label: "认领记录" }
];

const moduleColumns: Record<Exclude<ModuleKey, "secondary" | "claims">, string[]> = {
  market: columnsBetween("Z", "AN"),
  pricing: ["AO", "AP", "AR", "AS", "AT", "AU", "AV"],
  development: columnsBetween("M", "Y"),
  cost: columnsBetween("AW", "BX")
};

type DraftMap = Record<string, SecondaryResearchDraft<UploadedEvidenceImage>>;

export function SecondaryResearchView(props: {
  salespersonName: string;
  editable: boolean;
  onStatus: (message: string) => void;
}) {
  const [allGroups, setAllGroups] = useState<SecondaryResearchGroup[]>([]);
  const [periodFilter, setPeriodFilter] = useState("latest");
  const [activeIndex, setActiveIndex] = useState(0);
  const [activeModule, setActiveModule] = useState<ModuleKey>("secondary");
  const [drafts, setDrafts] = useState<DraftMap>({});
  const draftsRef = useRef<DraftMap>({});
  const saveQueue = useRef(createKeyedSaveQueue()).current;
  const saveRevision = useRef<Record<string, number>>({});
  const [saveState, setSaveState] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const periods = useMemo(
    () => Array.from(new Set(allGroups.map((entry) => entry.business_period || "").filter(Boolean))).sort().reverse(),
    [allGroups]
  );
  const latestPeriod = periods[0] || "";
  const groups = useMemo(
    () => allGroups.filter((entry) => {
      const period = entry.business_period || "";
      if (periodFilter === "__all__") return true;
      if (periodFilter === "latest") return period === latestPeriod;
      return period === periodFilter;
    }),
    [allGroups, latestPeriod, periodFilter]
  );
  const group = groups[activeIndex];

  function replaceDrafts(next: DraftMap) {
    draftsRef.current = next;
    setDrafts(next);
  }

  async function loadGroups() {
    if (props.editable && !props.salespersonName) return;
    setLoading(true);
    try {
      const result = await api.secondaryResearch(props.editable ? props.salespersonName : "", "__all__");
      setAllGroups(result);
      replaceDrafts(
        Object.fromEntries(result.flatMap((entry) => entry.items.map((item) => [item.claim_record_id, createSecondaryResearchDraft(item)])))
      );
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "二次调研加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadGroups();
  }, [props.salespersonName, props.editable]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, groups.length - 1)));
  }, [groups.length]);

  const groupProgress = useMemo(() => {
    if (!group) return { complete: 0, total: 0 };
    const missing = new Set(incompleteSecondaryResearchItems(group.items, drafts));
    return { complete: group.items.filter((item) => !missing.has(item.sub_sku)).length, total: group.items.length };
  }, [drafts, group]);

  function updateDraft(claimRecordId: string, patch: Partial<SecondaryResearchDraft<UploadedEvidenceImage>>) {
    replaceDrafts(
      group
        ? syncSecondaryResearchDraftPatch(draftsRef.current, group.items, claimRecordId, patch)
        : patchSecondaryResearchDraft(draftsRef.current, claimRecordId, patch)
    );
  }

  async function saveDraft(item: SecondaryResearchItem, draft = drafts[item.claim_record_id]) {
    if (!props.editable || !draft) return;
    const revision = (saveRevision.current[item.claim_record_id] ?? 0) + 1;
    saveRevision.current[item.claim_record_id] = revision;
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "保存中" }));
    try {
      await saveQueue(item.claim_record_id, () => api.updateSecondaryResearch(item.claim_record_id, props.salespersonName, draftPayload(draft)));
      if (saveRevision.current[item.claim_record_id] === revision) {
        setSaveState((current) => ({ ...current, [item.claim_record_id]: "已保存" }));
      }
    } catch (error) {
      if (saveRevision.current[item.claim_record_id] === revision) {
        setSaveState((current) => ({ ...current, [item.claim_record_id]: "保存失败" }));
        props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 草稿保存失败`);
      }
      throw error;
    }
  }

  async function uploadImages(item: SecondaryResearchItem, source: FileList | File[]) {
    const files = imageFiles(source);
    if (!files.length) return;
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传中" }));
    try {
      const uploaded = await Promise.all(files.map((file) => api.uploadClaimEvidence(item.opportunity_id, file)));
      const currentDraft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
      const nextDraft = { ...currentDraft, evidenceImages: [...currentDraft.evidenceImages, ...uploaded] };
      replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: nextDraft });
      await saveDraft(item, nextDraft).catch(() => undefined);
    } catch (error) {
      setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传失败" }));
      props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 图片上传失败`);
    }
  }

  async function removeImage(item: SecondaryResearchItem, image: UploadedEvidenceImage) {
    const currentDraft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
    const nextDraft = {
      ...currentDraft,
      evidenceImages: currentDraft.evidenceImages.filter((entry) => entry.url !== image.url || entry.name !== image.name)
    };
    replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: nextDraft });
    await saveDraft(item, nextDraft).catch(() => undefined);
  }

  async function submitGroup() {
    if (!group) return;
    const missing = incompleteSecondaryResearchItems(group.items, drafts);
    if (missing.length) {
      props.onStatus(`请先补全：${missing.join("、")}`);
      return;
    }
    setLoading(true);
    try {
      await Promise.all(group.items.map((item) => saveDraft(item)));
      await api.submitSecondaryResearchGroup(
        props.salespersonName,
        group.items.map((item) => item.claim_record_id)
      );
      props.onStatus(`${group.main_sku} 二次调研已提交`);
      await loadGroups();
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "整组提交失败");
    } finally {
      setLoading(false);
    }
  }

  function moveGroup(direction: -1 | 1) {
    setActiveIndex((current) => Math.min(groups.length - 1, Math.max(0, current + direction)));
  }

  if (loading && !group) return <div className="research-empty">正在加载二次调研任务...</div>;
  if (!group) {
    return (
      <div className="research-empty">
        <b>当前没有待二次调研的商品</b>
        <span>PLM 到货匹配成功后，对应运营的主 SKU 会出现在这里。</span>
      </div>
    );
  }

  return (
    <div className="secondary-workbench">
      <button
        className="research-side-nav previous"
        type="button"
        title="上一个主 SKU"
        disabled={activeIndex === 0}
        onClick={() => moveGroup(-1)}
      >
        <ChevronLeft size={20} />
      </button>
      <button
        className="research-side-nav next"
        type="button"
        title="下一个主 SKU"
        disabled={activeIndex === groups.length - 1}
        onClick={() => moveGroup(1)}
      >
        <ChevronRight size={20} />
      </button>

      <div className="research-context">
        <div className="research-title-row">
          <div>
            <b>{group.main_sku}</b>
            <span>{group.main_sku_name || "未填写主 SKU 名称"}</span>
          </div>
          <div className="research-top-nav">
            <button className="btn small" type="button" disabled={activeIndex === 0} onClick={() => moveGroup(-1)}>
              <ChevronLeft size={14} />上一个主 SKU
            </button>
            <span>第 {activeIndex + 1} / {groups.length} 组</span>
            <button className="btn small" type="button" disabled={activeIndex === groups.length - 1} onClick={() => moveGroup(1)}>
              下一个主 SKU<ChevronRight size={14} />
            </button>
          </div>
        </div>
        <div className="research-meta-line">
          <span>筛选 <select value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value)}>
            <option value="latest">最新期数</option>
            <option value="__all__">全部期数</option>
            {periods.map((period) => <option value={period} key={period}>{period}</option>)}
          </select></span>
          <span>业务期数 <b>{group.business_period || "-"}</b></span>
          <span>站点 / 国家 <b>{group.site || group.country || "-"}</b></span>
          <span>负责人 <b>{group.salesperson_name}</b></span>
          <span>到货时间 <b>{formatDateTime(group.items[0]?.arrival_detected_at)}</b></span>
          <span>类目 <b>{columnValue(group.items[0], "D") || "-"}</b></span>
          <span>关键词 <b>{columnValue(group.items[0], "E") || "-"}</b></span>
          <span>开品理由 <b>{group.items[0]?.reason || "-"}</b></span>
          <span>子 SKU <b>{group.items.length}</b></span>
          <span>已填完整 <b>{groupProgress.complete}/{groupProgress.total}</b></span>
        </div>
      </div>

      <div className="research-tabs" role="tablist">
        {modules.map((entry) => (
          <button
            type="button"
            className={activeModule === entry.key ? "active" : ""}
            key={entry.key}
            onClick={() => setActiveModule(entry.key)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="research-matrix-scroll">
        {activeModule === "secondary" && (
          <div className="research-matrix secondary-input-matrix">
            <div className="research-matrix-head research-secondary-grid">
              <span className="research-sku-cell">子 SKU</span>
              <span>AL 调研时间</span>
              <span>AM 竞品链接</span>
              <span>AN 调研结论</span>
              <span>AO 商品定位</span>
              <span>调研图片</span>
              <span>其他运营记录</span>
            </div>
            {group.items.map((item) => {
              const draft = drafts[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
              return (
                <div className="research-matrix-row research-secondary-grid" key={item.claim_record_id}>
                  <ResearchSkuCell item={item} />
                  <label className="research-entry-cell">
                    <span>AL 调研时间</span>
                    <input
                      type="datetime-local"
                      value={draft.researchedAt}
                      disabled={!props.editable}
                      onChange={(event) => updateDraft(item.claim_record_id, { researchedAt: event.target.value })}
                      onBlur={() => void saveDraft(item).catch(() => undefined)}
                    />
                  </label>
                  <label className="research-entry-cell">
                    <span>AM 竞品链接</span>
                    <div className="research-url-input">
                      <input
                        value={draft.competitorUrl}
                        disabled={!props.editable}
                        placeholder="粘贴二次调研链接"
                        onChange={(event) => updateDraft(item.claim_record_id, { competitorUrl: event.target.value })}
                        onBlur={() => void saveDraft(item).catch(() => undefined)}
                      />
                      {draft.competitorUrl && (
                        <a href={draft.competitorUrl} target="_blank" rel="noreferrer" title="打开链接">
                          <ExternalLink size={15} />
                        </a>
                      )}
                    </div>
                  </label>
                  <label className="research-entry-cell">
                    <span>AN 调研结论</span>
                    <textarea
                      value={draft.conclusion}
                      disabled={!props.editable}
                      placeholder="填写到货后的复查结论"
                      onChange={(event) => updateDraft(item.claim_record_id, { conclusion: event.target.value })}
                      onPaste={(event: ClipboardEvent<HTMLTextAreaElement>) => void uploadImages(item, event.clipboardData.files)}
                      onBlur={() => void saveDraft(item).catch(() => undefined)}
                    />
                  </label>
                  <label className="research-entry-cell">
                    <span>AO 商品定位</span>
                    <select
                      value={draft.positioning}
                      disabled={!props.editable}
                      onChange={(event) => {
                        const nextDraft = { ...draft, positioning: event.target.value as SecondaryResearchDraft["positioning"], directlyEdited: true };
                        updateDraft(item.claim_record_id, { positioning: nextDraft.positioning });
                        void saveDraft(item, nextDraft).catch(() => undefined);
                      }}
                    >
                      <option value="">请选择</option>
                      {SECONDARY_RESEARCH_POSITIONINGS.map((positioning) => (
                        <option value={positioning} key={positioning}>{positioning}</option>
                      ))}
                    </select>
                    <small>{SECONDARY_RESEARCH_SKIP_LISTING.has(draft.positioning) ? "提交后不进入刊登" : "提交后进入待刊登"}</small>
                  </label>
                  <div className="research-entry-cell research-image-cell">
                    <span>调研图片</span>
                    <ResearchImageList
                      editable={props.editable}
                      images={draft.evidenceImages}
                      onRemove={(image) => void removeImage(item, image)}
                    >
                      {props.editable && (
                        <label
                          className="research-upload"
                          title="添加调研图片"
                          tabIndex={0}
                          onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()}
                          onDrop={(event) => { event.preventDefault(); void uploadImages(item, event.dataTransfer.files); }}
                          onPaste={(event) => void uploadImages(item, event.clipboardData.files)}
                        >
                          <ImagePlus size={18} />
                          <span>添加</span>
                          <input
                            type="file"
                            accept="image/*"
                            multiple
                            onChange={(event) => {
                              const files = imageFiles(event.currentTarget.files);
                              event.currentTarget.value = "";
                              void uploadImages(item, files);
                            }}
                          />
                        </label>
                      )}
                    </ResearchImageList>
                    <small>{saveState[item.claim_record_id] || "离开输入框自动保存"}</small>
                  </div>
                  <div className="research-entry-cell research-peer-summary">
                    <span>其他运营记录</span>
                    <b>{item.peer_records.length} 条</b>
                    {item.peer_records.slice(0, 2).map((peer) => (
                      <small key={peer.claim_record_id}>{peer.salesperson_name} · {peer.product_positioning || "未定位"}</small>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {activeModule !== "secondary" && activeModule !== "claims" && (
          <SourceModuleMatrix group={group} moduleKey={activeModule} />
        )}

        {activeModule === "claims" && <PeerMatrix group={group} />}
      </div>

      <div className="research-submitbar">
        <div>
          <b>{props.editable ? "草稿自动保存" : "主管只读查看"}</b>
          <span>同一主 SKU 的子 SKU 必须全部填完整后整组提交；淘汰款与清仓款提交后不进入刊登。</span>
        </div>
        {props.editable && (
          <button className="btn primary" type="button" disabled={loading} onClick={() => void submitGroup()}>
            <Send size={16} />提交当前主 SKU
          </button>
        )}
      </div>
    </div>
  );
}

function ResearchImageList({
  editable,
  images,
  onRemove,
  children
}: {
  editable: boolean;
  images: UploadedEvidenceImage[];
  onRemove: (image: UploadedEvidenceImage) => void;
  children: ReactNode;
}) {
  const [preview, setPreview] = useState<UploadedEvidenceImage | null>(null);
  return (
    <div className="research-image-list">
      {images.map((image) => {
        const src = resolveImageUrl(image.url);
        return (
          <span className="evidence-thumb-card" key={`${image.url}-${image.name}`}>
            <button type="button" onClick={() => setPreview(image)} title="查看大图">
              <img src={src} alt={image.name} />
            </button>
            {editable && (
              <button className="evidence-thumb-remove" type="button" onClick={() => onRemove(image)} title="删除图片">
                <X size={12} />
              </button>
            )}
          </span>
        );
      })}
      {children}
      {preview && (
        <div className="image-preview" role="dialog" aria-modal="true" onClick={() => setPreview(null)}>
          <button className="image-preview-close" type="button" onClick={() => setPreview(null)}>
            <X size={18} />
          </button>
          <img src={resolveImageUrl(preview.url)} alt={preview.name} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function ResearchSkuCell({ item }: { item: SecondaryResearchItem }) {
  return (
    <div className="research-sku-cell research-sku-content">
      <div className="research-thumb">
        {item.image_url ? <img src={resolveImageUrl(item.image_url)} alt={item.sub_sku_name || item.sub_sku} /> : "图"}
      </div>
      <div>
        <b>{item.sub_sku}</b>
        <span>{item.sub_sku_name || "未填写子 SKU 名称"}</span>
        <small>{item.reason || "暂无开品理由"}</small>
      </div>
    </div>
  );
}

function SourceModuleMatrix({
  group,
  moduleKey
}: {
  group: SecondaryResearchGroup;
  moduleKey: Exclude<ModuleKey, "secondary" | "claims">;
}) {
  const columns = moduleColumns[moduleKey].filter(
    (column) => !isSourceClaimInputLabel(columnHeader(group.items[0], column))
  );
  return (
    <div className="research-matrix source-module-matrix" style={{ "--research-column-count": columns.length } as CSSProperties}>
      <div className="research-matrix-head research-source-grid">
        <span className="research-sku-cell">子 SKU</span>
        {columns.map((column) => (
          <span key={column}>{column} · {columnHeader(group.items[0], column)}</span>
        ))}
      </div>
      {group.items.map((item) => (
        <div className="research-matrix-row research-source-grid" key={item.claim_record_id}>
          <ResearchSkuCell item={item} />
          {columns.map((column) => {
            const value = columnValue(item, column);
            return (
              <div className="research-source-value" key={column} title={value}>
                {isUrl(value) ? (
                  <a href={value} target="_blank" rel="noreferrer">打开链接 <ExternalLink size={13} /></a>
                ) : value || "-"}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function PeerMatrix({ group }: { group: SecondaryResearchGroup }) {
  return (
    <div className="research-matrix peer-matrix">
      <div className="research-matrix-head research-peer-grid">
        <span className="research-sku-cell">子 SKU</span>
        <span>当前负责人</span>
        <span>认领单销</span>
        <span>其他运营已提交记录</span>
      </div>
      {group.items.map((item) => (
        <div className="research-matrix-row research-peer-grid" key={item.claim_record_id}>
          <ResearchSkuCell item={item} />
          <div className="research-source-value">{item.salesperson_name}</div>
          <div className="research-source-value">{formatBusinessNumber(columnValue(item, "AJ")) || "-"}</div>
          <div className="research-peer-list">
            {item.peer_records.length ? item.peer_records.map((peer) => (
              <div key={peer.claim_record_id}>
                <b>{peer.salesperson_name}</b>
                <span>{peer.product_positioning || "未定位"} · {peer.secondary_conclusion || "未填写结论"}</span>
              </div>
            )) : <span className="muted">暂无其他运营提交记录</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function draftPayload(draft: SecondaryResearchDraft<UploadedEvidenceImage>) {
  return {
    secondary_research_at: draft.researchedAt || null,
    secondary_competitor_url: draft.competitorUrl.trim() || null,
    secondary_conclusion: draft.conclusion.trim() || null,
    product_positioning: draft.positioning || null,
    secondary_evidence_images: draft.evidenceImages
  };
}

function columnValue(item: SecondaryResearchItem, column: string) {
  if (!item) return "";
  const fields = record(item.snapshot.fields_by_column);
  const cells = record(item.snapshot.cells);
  return valueText(fields[column] ?? cells[column] ?? item.snapshot[column]);
}

function formatDateTime(value?: string | null) {
  return value?.slice(0, 16).replace("T", " ") || "-";
}

function columnHeader(item: SecondaryResearchItem, column: string) {
  const headers = record(item.snapshot.headers_by_column)[column];
  if (Array.isArray(headers)) {
    return headers.map(valueText).filter(Boolean).join(" / ") || selection1ColumnLabel(column);
  }
  return valueText(headers) || selection1ColumnLabel(column);
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function valueText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function isUrl(value: string) {
  return /^https?:\/\//i.test(value);
}

function resolveImageUrl(url?: string | null) {
  if (!url) return "";
  if (url.startsWith("/uploaded-sources/")) return `${API_BASE}${url}`;
  if (url.includes("hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com")) {
    return `${API_BASE}/claims/evidence-images/proxy?url=${encodeURIComponent(url)}&token=${encodeURIComponent(getAuthToken())}`;
  }
  return url;
}

function columnsBetween(start: string, end: string) {
  const first = columnNumber(start);
  const last = columnNumber(end);
  return Array.from({ length: last - first + 1 }, (_, index) => columnName(first + index));
}

function columnNumber(column: string) {
  return column.split("").reduce((total, character) => total * 26 + character.charCodeAt(0) - 64, 0);
}

function columnName(index: number) {
  let value = "";
  while (index > 0) {
    index -= 1;
    value = String.fromCharCode(65 + (index % 26)) + value;
    index = Math.floor(index / 26);
  }
  return value;
}
