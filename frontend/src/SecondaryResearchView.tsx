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
  filterSecondaryResearchGroups,
  createSecondaryResearchDraft,
  incompleteSecondaryResearchItems,
  latestSecondaryResearchPeriod,
  patchSecondaryResearchDraft,
  SECONDARY_RESEARCH_POSITIONINGS,
  SECONDARY_RESEARCH_SKIP_LISTING,
  syncSecondaryResearchDraftPatch,
  SecondaryResearchDraft
} from "./secondaryResearchDrafts";
import { isSourceClaimInputLabel, selection1ColumnLabel } from "./selection1Columns";
import { formatBusinessNumber } from "./businessFormat";
import { createKeyedSaveQueue, imageFiles } from "./imageUploads";

type SourceModuleKey = "market" | "pricing" | "development" | "cost";
type DrawerModuleKey = SourceModuleKey | "claims";

const drawerModules: { key: DrawerModuleKey; label: string }[] = [
  { key: "market", label: "市场调研" },
  { key: "pricing", label: "价格 / 毛利" },
  { key: "development", label: "开发 / 包装" },
  { key: "cost", label: "成本 / 备货" },
  { key: "claims", label: "其他运营" }
];

const syncedDraftFields = ["competitorUrl", "conclusion", "positioning", "targetDailySales", "sellingPoints"] as const;

const moduleColumns: Record<SourceModuleKey, string[]> = {
  market: columnsBetween("Z", "AN"),
  pricing: ["AO", "AP", "AR", "AS", "AT", "AU", "AV"],
  development: columnsBetween("M", "Y"),
  cost: columnsBetween("AW", "BX")
};
type DraftMap = Record<string, SecondaryResearchDraft<UploadedEvidenceImage>>;

export function SecondaryResearchView(props: {
  salespersonName: string;
  editable: boolean;
  canManage: boolean;
  preset?: { scenario: "pending"; periodFilter: "__all__"; nonce: number } | null;
  onStatus: (message: string) => void;
}) {
  const [scenario, setScenario] = useState<"pending" | "submitted">("pending");
  const [query, setQuery] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [allGroups, setAllGroups] = useState<SecondaryResearchGroup[]>([]);
  const [periodFilter, setPeriodFilter] = useState("latest");
  const [activeIndex, setActiveIndex] = useState(0);
  const [drafts, setDrafts] = useState<DraftMap>({});
  const draftsRef = useRef<DraftMap>({});
  const saveQueue = useRef(createKeyedSaveQueue()).current;
  const saveRevision = useRef<Record<string, number>>({});
  const pendingSyncedSaveRevision = useRef(0);
  const pendingSyncedSaveIds = useRef<Record<string, Record<string, number>>>({});
  const [saveState, setSaveState] = useState<Record<string, string>>({});
  const [correctionClaimId, setCorrectionClaimId] = useState<string | null>(null);
  const [savingCorrectionClaimId, setSavingCorrectionClaimId] = useState<string | null>(null);
  const correctionOriginal = useRef<Record<string, SecondaryResearchDraft<UploadedEvidenceImage>>>({});
  const uploadCounts = useRef<Record<string, number>>({});
  const [, setUploadRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const periods = useMemo(
    () => Array.from(new Set(allGroups.map((entry) => entry.business_period || "").filter(Boolean))).sort().reverse(),
    [allGroups]
  );
  const latestPeriod = latestSecondaryResearchPeriod(allGroups, scenario, { country: countryFilter, salespersonName: props.editable ? "" : ownerFilter });
  const groups = useMemo(() => filterSecondaryResearchGroups(allGroups, {
    scenario, query, country: countryFilter, businessPeriod: periodFilter === "latest" ? latestPeriod : periodFilter === "__all__" ? "" : periodFilter,
    salespersonName: props.editable ? "" : ownerFilter
  }), [allGroups, countryFilter, latestPeriod, ownerFilter, periodFilter, props.editable, query, scenario]);
  const group = groups[activeIndex];
  const [detailGroupKey, setDetailGroupKey] = useState<string | null>(null);
  const detailGroup = detailGroupKey ? groups.find((entry) => entry.key === detailGroupKey) || null : null;

  function replaceDrafts(next: DraftMap) {
    draftsRef.current = next;
    setDrafts(next);
  }

  async function loadGroups() {
    if (props.editable && !props.salespersonName) return;
    setLoading(true);
    try {
      const result = await api.secondaryResearch(props.editable ? props.salespersonName : "", "__all__", "");
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
    const preset = props.preset;
    if (!preset) return;
    setScenario(preset.scenario);
    setPeriodFilter(preset.periodFilter);
    setActiveIndex(0);
  }, [props.preset?.nonce]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, groups.length - 1)));
  }, [groups.length]);

  useEffect(() => {
    if (detailGroupKey && !groups.some((entry) => entry.key === detailGroupKey)) setDetailGroupKey(null);
  }, [detailGroupKey, groups]);

  const groupProgress = useMemo(() => {
    if (!group) return { complete: 0, total: 0 };
    const missing = new Set(incompleteSecondaryResearchItems(group.items, drafts));
    return { complete: group.items.filter((item) => !missing.has(item.sub_sku)).length, total: group.items.length };
  }, [drafts, group]);

  function updateDraft(claimRecordId: string, patch: Partial<SecondaryResearchDraft<UploadedEvidenceImage>>) {
    if (group && syncedDraftFields.some((key) => key in patch)) {
      const syncedIds = group.items
        .filter((item) => item.claim_record_id !== claimRecordId)
        .filter((item) => !(draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>()).directlyEdited)
        .map((item) => item.claim_record_id);
      if (syncedIds.length) {
        const pending = pendingSyncedSaveIds.current[claimRecordId] || {};
        const revision = pendingSyncedSaveRevision.current + 1;
        pendingSyncedSaveRevision.current = revision;
        syncedIds.forEach((id) => { pending[id] = revision; });
        pendingSyncedSaveIds.current[claimRecordId] = pending;
      }
    }
    replaceDrafts(
      group
        ? syncSecondaryResearchDraftPatch(draftsRef.current, group.items, claimRecordId, patch)
        : patchSecondaryResearchDraft(draftsRef.current, claimRecordId, patch)
    );
  }

  async function saveDraft(item: SecondaryResearchItem, draft = drafts[item.claim_record_id], options: { saveSynced?: boolean } = {}) {
    if (!props.editable || scenario !== "pending" || !draft) return;
    const revision = (saveRevision.current[item.claim_record_id] ?? 0) + 1;
    saveRevision.current[item.claim_record_id] = revision;
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "保存中" }));
    try {
      await saveQueue(item.claim_record_id, () => api.updateSecondaryResearch(item.claim_record_id, props.salespersonName, draftPayload(draft)));
      if (saveRevision.current[item.claim_record_id] === revision) {
        setSaveState((current) => ({ ...current, [item.claim_record_id]: "已保存" }));
      }
      if (options.saveSynced !== false) await savePendingSyncedDrafts(item.claim_record_id).catch(() => undefined);
    } catch (error) {
      if (saveRevision.current[item.claim_record_id] === revision) {
        setSaveState((current) => ({ ...current, [item.claim_record_id]: "保存失败" }));
        props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 草稿保存失败`);
      }
      throw error;
    }
  }

  async function savePendingSyncedDrafts(sourceClaimRecordId: string) {
    const pending = pendingSyncedSaveIds.current[sourceClaimRecordId];
    const entries = Object.entries(pending || {});
    if (!group || !entries.length || !props.editable || scenario !== "pending") return;
    await Promise.all(entries.map(async ([claimRecordId, revision]) => {
      const syncedItem = group.items.find((item) => item.claim_record_id === claimRecordId);
      const syncedDraft = draftsRef.current[claimRecordId];
      if (!syncedItem || !syncedDraft) return;
      await saveDraft(syncedItem, syncedDraft, { saveSynced: false });
      if (pending?.[claimRecordId] === revision) delete pending[claimRecordId];
    }));
    if (pending && !Object.keys(pending).length) delete pendingSyncedSaveIds.current[sourceClaimRecordId];
  }

  function changeUploadCount(claimRecordId: string, delta: number) {
    const next = Math.max(0, (uploadCounts.current[claimRecordId] ?? 0) + delta);
    if (next) uploadCounts.current[claimRecordId] = next;
    else delete uploadCounts.current[claimRecordId];
    setUploadRevision((current) => current + 1);
  }

  function isUploading(claimRecordId: string) {
    return (uploadCounts.current[claimRecordId] ?? 0) > 0;
  }

  function isCorrectionBusy(claimRecordId: string) {
    return isUploading(claimRecordId) || savingCorrectionClaimId === claimRecordId;
  }

  async function uploadImages(item: SecondaryResearchItem, source: FileList | File[]) {
    const files = imageFiles(source);
    if (!files.length || savingCorrectionClaimId === item.claim_record_id) return;
    changeUploadCount(item.claim_record_id, 1);
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传中" }));
    try {
      const uploaded = await Promise.all(files.map((file) => api.uploadClaimEvidence(item.opportunity_id, file)));
      const currentDraft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
      const nextDraft = { ...currentDraft, evidenceImages: [...currentDraft.evidenceImages, ...uploaded] };
      replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: nextDraft });
      if (scenario === "pending") await saveDraft(item, nextDraft).catch(() => undefined);
      else setSaveState((current) => ({ ...current, [item.claim_record_id]: "待保存纠错" }));
    } catch (error) {
      setSaveState((current) => ({ ...current, [item.claim_record_id]: "上传失败" }));
      props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 图片上传失败`);
    } finally {
      changeUploadCount(item.claim_record_id, -1);
    }
  }

  async function removeImage(item: SecondaryResearchItem, image: UploadedEvidenceImage) {
    if (savingCorrectionClaimId === item.claim_record_id) return;
    const currentDraft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
    const nextDraft = {
      ...currentDraft,
      evidenceImages: currentDraft.evidenceImages.filter((entry) => entry.url !== image.url || entry.name !== image.name)
    };
    replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: nextDraft });
    if (scenario === "pending") await saveDraft(item, nextDraft).catch(() => undefined);
    else setSaveState((current) => ({ ...current, [item.claim_record_id]: "待保存纠错" }));
  }

  function startCorrection(item: SecondaryResearchItem) {
    const draft = draftsRef.current[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>(item);
    correctionOriginal.current[item.claim_record_id] = { ...draft, evidenceImages: [...draft.evidenceImages] };
    setCorrectionClaimId(item.claim_record_id);
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "纠错中，保存后生效" }));
  }

  function cancelCorrection(item: SecondaryResearchItem) {
    if (isCorrectionBusy(item.claim_record_id)) return;
    const original = correctionOriginal.current[item.claim_record_id];
    if (original) replaceDrafts({ ...draftsRef.current, [item.claim_record_id]: original });
    delete correctionOriginal.current[item.claim_record_id];
    setCorrectionClaimId(null);
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "已取消纠错" }));
  }

  async function saveCorrection(item: SecondaryResearchItem) {
    if (isCorrectionBusy(item.claim_record_id)) return;
    const draft = draftsRef.current[item.claim_record_id];
    const target = Number(draft?.targetDailySales);
    if (!draft?.conclusion.trim() || !draft.positioning || !Number.isFinite(target) || target <= 0 || !draft.sellingPoints.trim()) {
      props.onStatus(`${item.sub_sku} 请填写复查结论、商品定位、目标单销和卖点总结`);
      return;
    }
    setSavingCorrectionClaimId(item.claim_record_id);
    setSaveState((current) => ({ ...current, [item.claim_record_id]: "保存纠错中" }));
    try {
      await api.correctSecondaryResearch(item.claim_record_id, props.salespersonName, draftPayload(draft));
      delete correctionOriginal.current[item.claim_record_id];
      setCorrectionClaimId(null);
      props.onStatus(`${item.sub_sku} 纠错已保存，原提交时间及后续记录均保留`);
      await loadGroups();
    } catch (error) {
      setSaveState((current) => ({ ...current, [item.claim_record_id]: "纠错保存失败" }));
      props.onStatus(error instanceof Error ? error.message : `${item.sub_sku} 纠错保存失败`);
    } finally {
      setSavingCorrectionClaimId(null);
    }
  }

  async function submitGroup() {
    if (!group || scenario !== "pending") return;
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

  async function exportResearch() {
    setLoading(true);
    try {
      const businessPeriod = periodFilter === "latest" ? latestPeriod : periodFilter === "__all__" ? "" : periodFilter;
      await api.secondaryResearchExport({
        scenario,
        salesperson_name: props.editable ? props.salespersonName : ownerFilter,
        business_period: businessPeriod,
        country: countryFilter,
        query: query.trim()
      });
      props.onStatus("二次调研导出已下载");
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "二次调研导出失败");
    } finally {
      setLoading(false);
    }
  }

  const controls = (
    <div className={`research-workbench-controls${group ? "" : " research-empty-controls"}`}>
      <div className="research-scenarios"><button className={`btn small ${scenario === "pending" ? "primary" : ""}`} type="button" onClick={() => setScenario("pending")}>待处理</button><button className={`btn small ${scenario === "submitted" ? "primary" : ""}`} type="button" onClick={() => setScenario("submitted")}>我已提交</button></div>
      <label>关键词<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="主 / 子 SKU、名称" /></label>
      <label>国家<select value={countryFilter} onChange={(event) => setCountryFilter(event.target.value)}><option value="">全部</option>{Array.from(new Set(allGroups.map((entry) => entry.country).filter(Boolean))).sort().map((country) => <option value={country!} key={country}>{country}</option>)}</select></label>
      <label>业务期<select value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value)}><option value="latest">最新期数</option><option value="__all__">全部期数</option>{periods.map((period) => <option value={period} key={period}>{period}</option>)}</select></label>
      {!props.editable && <label>负责人<select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}><option value="">全部</option>{Array.from(new Set(allGroups.map((entry) => entry.salesperson_name))).sort().map((owner) => <option value={owner} key={owner}>{owner}</option>)}</select></label>}
      <button className="btn small" type="button" onClick={() => { setQuery(""); setCountryFilter(""); setOwnerFilter(""); setPeriodFilter("latest"); }}>清空</button>
      <button className="btn small" type="button" disabled={loading} onClick={() => void exportResearch()}>导出二次调研</button>
    </div>
  );

  if (loading && !group) return <div className="research-empty">正在加载二次调研任务...</div>;
  if (!group) return <div className="secondary-workbench">{controls}<div className="research-empty"><b>{scenario === "submitted" ? "当前筛选下没有已提交记录" : "当前筛选下没有待处理记录"}</b></div></div>;

  const primaryImageItem = group.items.find((item) => item.image_url) || group.items[0];

  return (
    <div className="secondary-workbench">
      {controls}
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
          <div className="research-title-main">
            <ResearchMainSkuThumb item={primaryImageItem} />
            <div className="research-main-heading">
              <button className="research-main-sku-open" type="button" onClick={() => setDetailGroupKey(group.key)}>
                {group.main_sku}
              </button>
              <span>{group.main_sku_name || "未填写主 SKU 名称"}</span>
            </div>
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
          <span>业务期数 <b>{group.business_period || "-"}</b></span>
          <span>国家 <b>{group.country || "-"}</b></span>
          <span>站点 <b>{group.site || "-"}</b></span>
          <span>负责人 <b>{group.salesperson_name}</b></span>
          <span>到货时间 <b>{formatDateTime(group.items[0]?.arrival_detected_at)}</b></span>
          <span>子 SKU <b>{group.items.length}</b></span>
          <span>已填完整 <b>{groupProgress.complete}/{groupProgress.total}</b></span>
        </div>
      </div>

      <div className="research-matrix-scroll">
        <div className="research-task-list secondary-input-matrix">
          {group.items.map((item) => {
            const draft = drafts[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
            const correctionActive = scenario === "submitted" && correctionClaimId === item.claim_record_id;
            const rowEditable = (scenario === "pending" && props.editable) || (correctionActive && savingCorrectionClaimId !== item.claim_record_id);
            const canCorrectRow = scenario === "submitted" && (props.editable || props.canManage);
            return (
              <div className="research-task-row" key={item.claim_record_id}>
                <ResearchSkuCell item={item} onOpenDetail={() => setDetailGroupKey(group.key)} hideThumb>
                  {canCorrectRow && (correctionActive ? (
                    <>
                      <button className="btn small primary" type="button" disabled={isCorrectionBusy(item.claim_record_id)} onClick={() => void saveCorrection(item)}>保存纠错</button>
                      <button className="btn small" type="button" disabled={isCorrectionBusy(item.claim_record_id)} onClick={() => cancelCorrection(item)}>取消</button>
                    </>
                  ) : (
                    <button className="btn small" type="button" disabled={correctionClaimId !== null || isCorrectionBusy(item.claim_record_id)} onClick={() => startCorrection(item)}>纠错</button>
                  ))}
                </ResearchSkuCell>
                <label className="research-entry-cell research-conclusion-cell">
                  <span>AN 调研结论</span>
                  <textarea
                    value={draft.conclusion}
                    disabled={!rowEditable}
                    placeholder="复查结论"
                    onChange={(event) => updateDraft(item.claim_record_id, { conclusion: event.target.value })}
                    onPaste={(event: ClipboardEvent<HTMLTextAreaElement>) => void uploadImages(item, event.clipboardData.files)}
                    onBlur={() => void saveDraft(item).catch(() => undefined)}
                  />
                </label>
                <div className="research-task-side">
                  <label className="research-entry-cell research-positioning-cell">
                    <span>AO 商品定位</span>
                    <select
                      value={draft.positioning}
                      disabled={!rowEditable}
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
                    <small>{SECONDARY_RESEARCH_SKIP_LISTING.has(draft.positioning) ? "不刊登" : "进刊登"}</small>
                  </label>
                </div>
                <div className="research-task-tools">
                  <label className="research-entry-cell research-inline-competitor">
                    <span>锚定链接</span>
                    <div className="research-url-input">
                      <input
                        value={draft.competitorUrl}
                        disabled={!rowEditable}
                        placeholder="锚定链接"
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
                  <label className="research-entry-cell research-target-sales">
                    <span>目标单销</span>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={draft.targetDailySales}
                      disabled={!rowEditable}
                      placeholder="目标单销"
                      onChange={(event) => updateDraft(item.claim_record_id, { targetDailySales: event.target.value })}
                      onBlur={() => void saveDraft(item).catch(() => undefined)}
                    />
                  </label>
                  <label className="research-entry-cell research-selling-points">
                    <span>卖点总结</span>
                    <input
                      value={draft.sellingPoints}
                      disabled={!rowEditable}
                      placeholder="卖点总结"
                      onChange={(event) => updateDraft(item.claim_record_id, { sellingPoints: event.target.value })}
                      onBlur={() => void saveDraft(item).catch(() => undefined)}
                    />
                  </label>
                  <ResearchImageList
                    className="research-inline-images"
                    editable={rowEditable}
                    images={draft.evidenceImages}
                    onRemove={(image) => void removeImage(item, image)}
                  >
                    {rowEditable && (
                      <label
                        className="research-upload"
                        title="添加调研图片"
                        tabIndex={0}
                        onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()}
                        onDrop={(event) => { event.preventDefault(); void uploadImages(item, event.dataTransfer.files); }}
                        onPaste={(event) => void uploadImages(item, event.clipboardData.files)}
                      >
                        <ImagePlus size={18} />
                        <span>{isUploading(item.claim_record_id) ? "上传中" : `${draft.evidenceImages.length}张`}</span>
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
                  <div className="research-entry-cell research-auto-time">
                    <span>调研时间</span>
                    <small>{formatDateTime(item.secondary_research_at) === "-" ? "提交后自动记录" : formatDateTime(item.secondary_research_at)}</small>
                  </div>
                  <div className="research-save-cell">
                    <span>保存状态</span>
                    <small>{saveState[item.claim_record_id] || "离开输入框自动保存"}</small>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {detailGroup && (
        <ResearchDetailDrawer
          canManage={props.canManage}
          correctionClaimId={correctionClaimId}
          drafts={drafts}
          editable={props.editable}
          group={detailGroup}
          isCorrectionBusy={isCorrectionBusy}
          isUploading={isUploading}
          onCancelCorrection={cancelCorrection}
          onClose={() => setDetailGroupKey(null)}
          onRemoveImage={removeImage}
          onSaveCorrection={saveCorrection}
          onSaveDraft={saveDraft}
          onStartCorrection={startCorrection}
          onUpdateDraft={updateDraft}
          onUploadImages={uploadImages}
          saveState={saveState}
          savingCorrectionClaimId={savingCorrectionClaimId}
          scenario={scenario}
        />
      )}
      <div className="research-submitbar">
        <div>
          <b>{scenario === "submitted" ? correctionClaimId ? "正在纠错，保存后生效" : "已提交，可按行纠错" : props.editable ? "草稿自动保存" : "主管只读查看"}</b>
          <span>同一主 SKU 的子 SKU 必须全部填完整后整组提交；淘汰款与清仓款提交后不进入刊登。</span>
        </div>
        {props.editable && scenario === "pending" && (
          <button className="btn primary" type="button" disabled={loading} onClick={() => void submitGroup()}>
            <Send size={16} />提交当前主 SKU
          </button>
        )}
      </div>
    </div>
  );
}

type SecondaryDraftMatrixProps = {
  group: SecondaryResearchGroup;
  drafts: DraftMap;
  scenario: "pending" | "submitted";
  editable: boolean;
  canManage: boolean;
  saveState: Record<string, string>;
  correctionClaimId: string | null;
  savingCorrectionClaimId: string | null;
  onUpdateDraft: (claimRecordId: string, patch: Partial<SecondaryResearchDraft<UploadedEvidenceImage>>) => void;
  onSaveDraft: (item: SecondaryResearchItem, draft?: SecondaryResearchDraft<UploadedEvidenceImage>) => Promise<void>;
  onUploadImages: (item: SecondaryResearchItem, source: FileList | File[]) => Promise<void>;
  onRemoveImage: (item: SecondaryResearchItem, image: UploadedEvidenceImage) => Promise<void>;
  isUploading: (claimRecordId: string) => boolean;
  isCorrectionBusy: (claimRecordId: string) => boolean;
  onStartCorrection: (item: SecondaryResearchItem) => void;
  onSaveCorrection: (item: SecondaryResearchItem) => Promise<void>;
  onCancelCorrection: (item: SecondaryResearchItem) => void;
};

function ResearchDetailDrawer(props: SecondaryDraftMatrixProps & { onClose: () => void }) {
  const [activeModule, setActiveModule] = useState<DrawerModuleKey>("market");
  const first = props.group.items[0];
  const primaryImageItem = props.group.items.find((item) => item.image_url) || first;
  const activeSourceModule = activeModule !== "claims" ? activeModule : null;
  const activeSourceLabel = drawerModules.find((entry) => entry.key === activeModule)?.label || "";

  useEffect(() => {
    setActiveModule("market");
  }, [props.group.key]);

  return (
    <div className="claim-detail-overlay" role="dialog" aria-modal="true">
      <button className="claim-detail-backdrop" type="button" onClick={props.onClose}>
        <span>关闭详情</span>
      </button>
      <aside className="claim-detail-drawer research-detail-drawer">
        <header className="claim-drawer-head">
          <div className="drawer-title-row">
            <div className="research-drawer-title-main">
              <ResearchMainSkuThumb item={primaryImageItem} />
              <div>
                <h2>{props.group.main_sku}</h2>
                <p>{props.group.main_sku_name || "未填写主 SKU 名称"} · {props.group.items.length} 个子 SKU</p>
                <div className="research-drawer-header-meta">
                  <span>类目 <b>{columnValue(first, "D") || "-"}</b></span>
                  <span>关键词 <b>{columnValue(first, "E") || "-"}</b></span>
                  {props.group.items.map((item) => (
                    <span className="research-source-reason" key={item.claim_record_id}>开品理由 · {item.sub_sku} <b>{item.reason || "-"}</b></span>
                  ))}
                </div>
              </div>
            </div>
            <div className="drawer-header-actions">
              <button className="btn small" type="button" onClick={props.onClose}><X size={14} />关闭</button>
            </div>
          </div>
        </header>
        <div className="claim-drawer-body">
          <div className="research-drawer-tabs">
            {drawerModules.map((entry) => (
              <button className={activeModule === entry.key ? "claim-module-tab active" : "claim-module-tab"} key={entry.key} type="button" onClick={() => setActiveModule(entry.key)}>
                {entry.label}
              </button>
            ))}
          </div>

          {activeModule === "claims" && (
            <section className="research-drawer-section">
              <h3>认领记录</h3>
              <p className="muted">其他运营已提交的二次调研记录按子 SKU 展示。</p>
              <div className="research-source-panel-scroll"><PeerMatrix group={props.group} /></div>
            </section>
          )}
          {activeSourceModule && (
            <section className="research-drawer-section">
              <h3>{activeSourceLabel}</h3>
              <div className="research-source-panel-scroll"><SourceModuleMatrix group={props.group} moduleKey={activeSourceModule} /></div>
              {activeModule === "market" && (
                <div className="research-drawer-section research-market-secondary">
                  <h3>二次调研填写</h3>
                  <SecondaryDraftMatrix {...props} />
                </div>
              )}
            </section>
          )}
        </div>
      </aside>
    </div>
  );
}

function SecondaryDraftMatrix(props: SecondaryDraftMatrixProps) {
  return (
    <div className="research-drawer-edit-matrix">
      {props.group.items.map((item) => {
        const draft = props.drafts[item.claim_record_id] || createSecondaryResearchDraft<UploadedEvidenceImage>();
        const correctionActive = props.scenario === "submitted" && props.correctionClaimId === item.claim_record_id;
        const rowEditable = (props.scenario === "pending" && props.editable) || (correctionActive && props.savingCorrectionClaimId !== item.claim_record_id);
        const canCorrectRow = props.scenario === "submitted" && (props.editable || props.canManage);
        return (
          <div className="research-task-row" key={item.claim_record_id}>
            <ResearchSkuCell item={item} hideThumb>
              {canCorrectRow && (correctionActive ? (
                <>
                  <button className="btn small primary" type="button" disabled={props.isCorrectionBusy(item.claim_record_id)} onClick={() => void props.onSaveCorrection(item)}>保存纠错</button>
                  <button className="btn small" type="button" disabled={props.isCorrectionBusy(item.claim_record_id)} onClick={() => props.onCancelCorrection(item)}>取消</button>
                </>
              ) : (
                <button className="btn small" type="button" disabled={props.correctionClaimId !== null || props.isCorrectionBusy(item.claim_record_id)} onClick={() => props.onStartCorrection(item)}>纠错</button>
              ))}
            </ResearchSkuCell>
            <label className="research-entry-cell research-conclusion-cell">
              <span>AN 调研结论</span>
              <textarea
                value={draft.conclusion}
                disabled={!rowEditable}
                placeholder="复查结论"
                onChange={(event) => props.onUpdateDraft(item.claim_record_id, { conclusion: event.target.value })}
                onPaste={(event: ClipboardEvent<HTMLTextAreaElement>) => void props.onUploadImages(item, event.clipboardData.files)}
                onBlur={() => void props.onSaveDraft(item).catch(() => undefined)}
              />
            </label>
            <div className="research-task-side">
              <label className="research-entry-cell research-positioning-cell">
                <span>AO 商品定位</span>
                <select
                  value={draft.positioning}
                  disabled={!rowEditable}
                  onChange={(event) => {
                    const nextDraft = { ...draft, positioning: event.target.value as SecondaryResearchDraft["positioning"], directlyEdited: true };
                    props.onUpdateDraft(item.claim_record_id, { positioning: nextDraft.positioning });
                    void props.onSaveDraft(item, nextDraft).catch(() => undefined);
                  }}
                >
                  <option value="">请选择</option>
                  {SECONDARY_RESEARCH_POSITIONINGS.map((positioning) => (
                    <option value={positioning} key={positioning}>{positioning}</option>
                  ))}
                </select>
                <small>{SECONDARY_RESEARCH_SKIP_LISTING.has(draft.positioning) ? "不刊登" : "进刊登"}</small>
              </label>
            </div>
            <div className="research-task-tools">
              <label className="research-entry-cell research-inline-competitor">
                <span>锚定链接</span>
                <div className="research-url-input">
                  <input
                    value={draft.competitorUrl}
                    disabled={!rowEditable}
                    placeholder="锚定链接"
                    onChange={(event) => props.onUpdateDraft(item.claim_record_id, { competitorUrl: event.target.value })}
                    onBlur={() => void props.onSaveDraft(item).catch(() => undefined)}
                  />
                  {draft.competitorUrl && (
                    <a href={draft.competitorUrl} target="_blank" rel="noreferrer" title="打开链接">
                      <ExternalLink size={15} />
                    </a>
                  )}
                </div>
              </label>
              <label className="research-entry-cell research-target-sales">
                <span>目标单销</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={draft.targetDailySales}
                  disabled={!rowEditable}
                  placeholder="目标单销"
                  onChange={(event) => props.onUpdateDraft(item.claim_record_id, { targetDailySales: event.target.value })}
                  onBlur={() => void props.onSaveDraft(item).catch(() => undefined)}
                />
              </label>
              <label className="research-entry-cell research-selling-points">
                <span>卖点总结</span>
                <input
                  value={draft.sellingPoints}
                  disabled={!rowEditable}
                  placeholder="卖点总结"
                  onChange={(event) => props.onUpdateDraft(item.claim_record_id, { sellingPoints: event.target.value })}
                  onBlur={() => void props.onSaveDraft(item).catch(() => undefined)}
                />
              </label>
              <ResearchImageList
                className="research-inline-images"
                editable={rowEditable}
                images={draft.evidenceImages}
                onRemove={(image) => void props.onRemoveImage(item, image)}
              >
                {rowEditable && (
                  <label
                    className="research-upload"
                    title="添加调研图片"
                    tabIndex={0}
                    onDragOver={(event: DragEvent<HTMLLabelElement>) => event.preventDefault()}
                    onDrop={(event) => { event.preventDefault(); void props.onUploadImages(item, event.dataTransfer.files); }}
                    onPaste={(event) => void props.onUploadImages(item, event.clipboardData.files)}
                  >
                    <ImagePlus size={18} />
                    <span>{props.isUploading(item.claim_record_id) ? "上传中" : `${draft.evidenceImages.length}张`}</span>
                    <input
                      type="file"
                      accept="image/*"
                      multiple
                      onChange={(event) => {
                        const files = imageFiles(event.currentTarget.files);
                        event.currentTarget.value = "";
                        void props.onUploadImages(item, files);
                      }}
                    />
                  </label>
                )}
              </ResearchImageList>
              <div className="research-entry-cell research-auto-time">
                <span>调研时间</span>
                <small>{formatDateTime(item.secondary_research_at) === "-" ? "提交后自动记录" : formatDateTime(item.secondary_research_at)}</small>
              </div>
              <div className="research-save-cell">
                <span>保存状态</span>
                <small>{props.saveState[item.claim_record_id] || "离开输入框自动保存"}</small>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
function ResearchImageList({
  className,
  editable,
  images,
  onRemove,
  children
}: {
  className?: string;
  editable: boolean;
  images: UploadedEvidenceImage[];
  onRemove: (image: UploadedEvidenceImage) => void;
  children: ReactNode;
}) {
  const [preview, setPreview] = useState<UploadedEvidenceImage | null>(null);
  return (
    <div className={className ? `research-image-list ${className}` : "research-image-list"}>
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

function ResearchMainSkuThumb({ item }: { item?: SecondaryResearchItem }) {
  return (
    <div className="research-main-thumb research-thumb">
      {item?.image_url ? <img src={resolveImageUrl(item.image_url)} alt={item.sub_sku_name || item.sub_sku} /> : "图"}
    </div>
  );
}

function ResearchSkuCell({ item, children, onOpenDetail, hideThumb }: { item: SecondaryResearchItem; children?: ReactNode; onOpenDetail?: () => void; hideThumb?: boolean }) {
  return (
    <div className={hideThumb ? "research-sku-cell research-sku-content no-thumb" : "research-sku-cell research-sku-content"}>
      {!hideThumb && (
        <div className="research-thumb">
          {item.image_url ? <img src={resolveImageUrl(item.image_url)} alt={item.sub_sku_name || item.sub_sku} /> : "图"}
        </div>
      )}
      <div>
        {onOpenDetail ? <button className="research-sku-open" type="button" onClick={onOpenDetail}>{item.sub_sku}</button> : <b>{item.sub_sku}</b>}
        <span>{item.sub_sku_name || "未填写子 SKU 名称"}</span>
        {children && <div className="research-correction-actions">{children}</div>}
      </div>
    </div>
  );
}

function SourceModuleMatrix({
  group,
  moduleKey
}: {
  group: SecondaryResearchGroup;
  moduleKey: SourceModuleKey;
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
          <ResearchSkuCell item={item} hideThumb />
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
          <ResearchSkuCell item={item} hideThumb />
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
  const targetDailySales = Number(draft.targetDailySales);
  return {
    secondary_competitor_url: draft.competitorUrl.trim() || null,
    secondary_conclusion: draft.conclusion.trim() || null,
    product_positioning: draft.positioning || null,
    secondary_target_daily_sales: Number.isFinite(targetDailySales) && targetDailySales > 0 ? targetDailySales : null,
    secondary_selling_points: draft.sellingPoints.trim() || null,
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

export function resolveImageUrl(url?: string | null) {
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
