import { ClipboardEvent, CSSProperties, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, ImagePlus, Plus, Send, X } from "lucide-react";

import {
  API_BASE,
  api,
  getAuthToken,
  OperatorAssignmentProfile,
  PlmArrivalAssignment,
  SecondaryResearchGroup,
  SecondaryResearchItem,
  UploadedEvidenceImage
} from "./api";
import {
  filterSecondaryResearchGroups,
  createSecondaryResearchDraft,
  defaultManualSecondaryBusinessPeriod,
  incompleteSecondaryResearchItems,
  isSecondaryResearchDraftComplete,
  patchSecondaryResearchDraft,
  researchLinkLabels,
  SECONDARY_RESEARCH_POSITIONINGS,
  SECONDARY_RESEARCH_SKIP_LISTING,
  secondaryResearchTargetDailySalesValue,
  syncSecondaryResearchDraftPatch,
  SecondaryResearchDraft
} from "./secondaryResearchDrafts";
import { productImageSrc, productThumbSrc } from "./imageSource";
import { formatBeijingDateTime } from "./dateTime";
import { isSourceClaimInputLabel, selection1ColumnLabel } from "./selection1Columns";
import { formatBusinessNumber } from "./businessFormat";
import { createKeyedSaveQueue, imageFiles } from "./imageUploads";
import { isSelection2Item, selection2HeaderFields, Selection2SectionKey } from "./historicalSnapshot";
import { cachedValue, setCachedValue } from "./pageDataCache";
import { normalizeSiteText } from "./opportunityGroups";

type SourceModuleKey = "market" | "pricing" | "development" | "cost";
type DrawerModuleKey = SourceModuleKey | "claims";
type ResearchScenario = "pending" | "submitted" | "arrival_assignment";

const selection1DrawerModules: { key: DrawerModuleKey; label: string }[] = [
  { key: "market", label: "市场调研" },
  { key: "pricing", label: "价格 / 毛利" },
  { key: "development", label: "开发 / 包装" },
  { key: "cost", label: "成本 / 备货" },
  { key: "claims", label: "其他运营" }
];

const selection2DrawerModules: { key: DrawerModuleKey; label: string }[] = [
  { key: "market", label: "市场与采购" },
  { key: "pricing", label: "定价与利润" },
  { key: "development", label: "成本与包装" },
  { key: "cost", label: "核价与首单" },
  { key: "claims", label: "其他运营" }
];

const selection2ModuleSections: Record<SourceModuleKey, Selection2SectionKey> = {
  market: "market",
  pricing: "pricing",
  development: "cost",
  cost: "valuation"
};

const syncedDraftFields = ["competitorUrl", "conclusion", "positioning", "targetDailySales", "sellingPoints"] as const;

const moduleColumns: Record<SourceModuleKey, string[]> = {
  market: columnsBetween("Z", "AN"),
  pricing: ["AO", "AP", "AR", "AS", "AT", "AU", "AV"],
  development: columnsBetween("M", "Y"),
  cost: columnsBetween("AW", "BX")
};
type DraftMap = Record<string, SecondaryResearchDraft<UploadedEvidenceImage>>;
const MANUAL_SECONDARY_COUNTRIES = ["菲律宾", "泰国", "越南", "马来西亚"];

type ManualSecondaryDraft = {
  country: string;
  salesperson_name: string;
  business_period: string;
  main_sku: string;
  main_sku_name: string;
  sub_sku: string;
  sub_sku_name: string;
  secondary_competitor_url: string;
};
type ManualSecondaryErrors = Partial<Record<keyof ManualSecondaryDraft, string>>;
type PlmArrivalAssignmentGroup = {
  groupKey: string;
  itemIds: string[];
  items: PlmArrivalAssignment[];
  country?: string | null;
  mainSku?: string | null;
  productName?: string | null;
  plmSalespeople: string[];
  firstListingTime?: string | null;
  sourceSummary: string;
  existingOpportunityCount: number;
  systemBusinessPeriods: string[];
  assignmentHint?: string | null;
  assignmentBlockReason?: string | null;
};

function plmAssignmentMainGroupKey(row: PlmArrivalAssignment) {
  const site = normalizeSiteText(row.country) || String(row.country || "").trim();
  const mainSku = String(row.main_sku || "").trim().toUpperCase();
  return `${site || "__no_site"}::${mainSku || row.plm_arrival_item_id}`;
}

export function SecondaryResearchView(props: {
  salespersonName: string;
  editable: boolean;
  canManage: boolean;
  preset?: { scenario: "pending"; periodFilter: "__all__"; nonce: number } | null;
  onStatus: (message: string) => void;
}) {
  const [scenario, setScenario] = useState<ResearchScenario>("pending");
  const [query, setQuery] = useState("");
  const [countryFilter, setCountryFilter] = useState("");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [allGroups, setAllGroups] = useState<SecondaryResearchGroup[]>([]);
  const [periodFilter, setPeriodFilter] = useState("__all__");
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
  const [manualSecondary, setManualSecondary] = useState<ManualSecondaryDraft | null>(null);
  const [manualSecondaryErrors, setManualSecondaryErrors] = useState<ManualSecondaryErrors>({});
  const manualSecondaryDialog = useRef<HTMLDivElement | null>(null);
  const [plmAssignments, setPlmAssignments] = useState<PlmArrivalAssignment[]>([]);
  const [assignmentOperatorProfiles, setAssignmentOperatorProfiles] = useState<OperatorAssignmentProfile[]>([]);
  const [assignmentOwners, setAssignmentOwners] = useState<Record<string, string>>({});
  const [assignmentCloseReasons, setAssignmentCloseReasons] = useState<Record<string, string>>({});
  const periods = useMemo(
    () => Array.from(new Set(allGroups.map((entry) => entry.business_period || "").filter(Boolean))).sort().reverse(),
    [allGroups]
  );
  const countryOptions = useMemo(
    () => Array.from(new Set([
      ...allGroups.map((entry) => entry.country).filter(Boolean),
      ...plmAssignments.map((entry) => entry.country).filter(Boolean),
    ])).sort(),
    [allGroups, plmAssignments]
  );
  function plmAssignmentOperatorsForGroup(group: PlmArrivalAssignmentGroup) {
    return assignmentOperatorProfiles
      .filter((operator) => operator.enabled)
      .sort((left, right) => {
        const order = (left.display_order ?? 0) - (right.display_order ?? 0);
        return order || left.operator_name.localeCompare(right.operator_name, "zh-CN");
      });
  }
  const researchScenario = scenario === "submitted" ? "submitted" : "pending";
  const groups = useMemo(() => filterSecondaryResearchGroups(allGroups, {
    scenario: researchScenario, query, country: countryFilter, businessPeriod: periodFilter === "__all__" ? "" : periodFilter,
    salespersonName: props.editable ? "" : ownerFilter
  }), [allGroups, countryFilter, ownerFilter, periodFilter, props.editable, query, researchScenario]);
  const manualSecondaryOpen = Boolean(manualSecondary);
  const visiblePlmAssignments = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return plmAssignments.filter((item) => {
      if (countryFilter && item.country !== countryFilter) return false;
      if (!keyword) return true;
      return [
        item.main_sku,
        item.sub_sku,
        item.product_name,
        item.plm_salesperson_name,
        item.source_file,
        ...(item.system_business_periods || []),
      ].some((value) => String(value || "").toLowerCase().includes(keyword));
    });
  }, [countryFilter, plmAssignments, query]);
  const visiblePlmAssignmentGroups = useMemo<PlmArrivalAssignmentGroup[]>(() => {
    const groups = new Map<string, PlmArrivalAssignment[]>();
    for (const item of visiblePlmAssignments) {
      const groupKey = plmAssignmentMainGroupKey(item);
      groups.set(groupKey, [...(groups.get(groupKey) || []), item]);
    }
    return Array.from(groups.entries()).map(([groupKey, items]) => {
      const sortedItems = [...items].sort((left, right) => (left.source_row || 0) - (right.source_row || 0));
      const first = sortedItems[0];
      const plmSalespeople = Array.from(new Set(sortedItems.map((item) => item.plm_salesperson_name || "").filter(Boolean)));
      const sourceRows = sortedItems
        .map((item) => item.source_row)
        .filter((row): row is number => typeof row === "number")
        .sort((left, right) => left - right);
      const sourceSummary = sourceRows.length
        ? `${first.source_file || "-"} 行 ${sourceRows.join("、")}`
        : `${first.source_file || "-"} 行 -`;
      const blockReasons = sortedItems.map((item) => item.assignment_block_reason).filter(Boolean);
      const systemBusinessPeriods = Array.from(new Set(sortedItems.flatMap((item) => item.system_business_periods || []).filter(Boolean))).sort();
      return {
        groupKey,
        itemIds: sortedItems.map((item) => item.plm_arrival_item_id),
        items: sortedItems,
        country: first.country,
        mainSku: first.main_sku,
        productName: first.product_name,
        plmSalespeople,
        firstListingTime: first.first_listing_time,
        sourceSummary,
        existingOpportunityCount: sortedItems.reduce((sum, item) => sum + (item.existing_opportunity_count || 0), 0),
        systemBusinessPeriods,
        assignmentHint: blockReasons[0] || first.assignment_hint,
        assignmentBlockReason: blockReasons[0] || null,
      };
    });
  }, [visiblePlmAssignments]);
  const group = groups[activeIndex];
  const [detailGroupKey, setDetailGroupKey] = useState<string | null>(null);
  const detailGroup = detailGroupKey ? groups.find((entry) => entry.key === detailGroupKey) || null : null;

  function replaceDrafts(next: DraftMap) {
    draftsRef.current = next;
    setDrafts(next);
  }

  function applyGroups(result: SecondaryResearchGroup[]) {
    setAllGroups(result);
    replaceDrafts(
      Object.fromEntries(result.flatMap((entry) => entry.items.map((item) => [item.claim_record_id, createSecondaryResearchDraft(item)])))
    );
  }

  async function loadGroups(options: { force?: boolean } = {}) {
    if (props.editable && !props.salespersonName) return;
    const cacheKey = `secondary-research:${props.editable ? "operator" : "manager"}:${props.salespersonName || ""}`;
    const cached = options.force ? undefined : cachedValue<SecondaryResearchGroup[]>(cacheKey);
    if (cached) applyGroups(cached);
    setLoading(!cached);
    try {
      const result = await api.secondaryResearch(props.editable ? props.salespersonName : "", "__all__", "");
      setCachedValue(cacheKey, result);
      applyGroups(result);
    } catch (error) {
      if (!cached) props.onStatus(error instanceof Error ? error.message : "二次调研加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function loadPlmAssignments(options: { force?: boolean } = {}) {
    if (!props.canManage) return;
    const cacheKey = "secondary-research:plm-arrival-assignments";
    const cached = options.force ? undefined : cachedValue<PlmArrivalAssignment[]>(cacheKey);
    if (cached) setPlmAssignments(cached);
    setLoading(!cached);
    try {
      const [assignments, operators] = await Promise.all([
        api.plmArrivalAssignments(),
        api.plmArrivalAssignmentOperators(),
      ]);
      setCachedValue(cacheKey, assignments);
      setPlmAssignments(assignments);
      setAssignmentOperatorProfiles(operators);
    } catch (error) {
      if (!cached) props.onStatus(error instanceof Error ? error.message : "PLM到货待分配加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadGroups();
  }, [props.salespersonName, props.editable]);

  useEffect(() => {
    if (props.canManage) void loadPlmAssignments();
  }, [props.canManage]);

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

  useEffect(() => {
    if (manualSecondary) manualSecondaryDialog.current?.focus();
  }, [manualSecondaryOpen]);

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
    if (!draft || !isSecondaryResearchDraftComplete(draft)) {
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
      await loadGroups({ force: true });
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
      await loadGroups({ force: true });
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "整组提交失败");
    } finally {
      setLoading(false);
    }
  }

  function moveGroup(direction: -1 | 1) {
    setActiveIndex((current) => Math.min(groups.length - 1, Math.max(0, current + direction)));
  }

  function openManualSecondary() {
    setManualSecondaryErrors({});
    setManualSecondary({
      country: countryFilter || "菲律宾",
      salesperson_name: props.editable ? props.salespersonName : ownerFilter,
      business_period: defaultManualSecondaryBusinessPeriod(),
      main_sku: "",
      main_sku_name: "",
      sub_sku: "",
      sub_sku_name: "",
      secondary_competitor_url: ""
    });
  }

  function closeManualSecondary() {
    setManualSecondary(null);
    setManualSecondaryErrors({});
  }

  function updateManualSecondary(field: keyof ManualSecondaryDraft, value: string) {
    setManualSecondary((current) => current ? { ...current, [field]: value } : current);
    setManualSecondaryErrors((current) => ({ ...current, [field]: undefined }));
  }

  function validateManualSecondary(draft: ManualSecondaryDraft) {
    const errors: ManualSecondaryErrors = {};
    if (!draft.country.trim()) errors.country = "请填写国家";
    if (!draft.main_sku.trim()) errors.main_sku = "请填写主 SKU";
    if (!draft.sub_sku.trim()) errors.sub_sku = "请填写子 SKU";
    if (!draft.salesperson_name.trim()) errors.salesperson_name = "请填写负责人";
    return errors;
  }

  async function submitManualSecondary() {
    if (!manualSecondary) return;
    const errors = validateManualSecondary(manualSecondary);
    setManualSecondaryErrors(errors);
    if (Object.keys(errors).length) {
      props.onStatus("请补全新增二调 SKU 信息");
      return;
    }
    const mainSku = manualSecondary.main_sku.trim();
    setLoading(true);
    try {
      await api.createManualSecondaryResearch({
        country: manualSecondary.country.trim(),
        salesperson_name: manualSecondary.salesperson_name.trim(),
        business_period: manualSecondary.business_period.trim() || null,
        main_sku: mainSku,
        main_sku_name: manualSecondary.main_sku_name.trim() || null,
        sub_sku: manualSecondary.sub_sku.trim(),
        sub_sku_name: manualSecondary.sub_sku_name.trim() || null,
        secondary_competitor_url: manualSecondary.secondary_competitor_url.trim() || null
      });
      closeManualSecondary();
      setScenario("pending");
      setPeriodFilter("__all__");
      setQuery(mainSku);
      props.onStatus(`${mainSku} 已新增到二次调研待处理`);
      await loadGroups({ force: true });
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "新增二调 SKU 失败");
    } finally {
      setLoading(false);
    }
  }

  async function exportResearch(exportScenario: Exclude<ResearchScenario, "arrival_assignment"> | "all" = researchScenario) {
    if (scenario === "arrival_assignment" && exportScenario !== "all") return;
    setLoading(true);
    try {
      const businessPeriod = periodFilter === "__all__" ? "" : periodFilter;
      await api.secondaryResearchExport({
        scenario: exportScenario,
        salesperson_name: props.editable ? props.salespersonName : ownerFilter,
        business_period: businessPeriod,
        country: countryFilter,
        query: query.trim()
      });
      props.onStatus(exportScenario === "all" ? "全部二次调研导出已下载" : "二次调研导出已下载");
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "二次调研导出失败");
    } finally {
      setLoading(false);
    }
  }

  const controls = (
    <div className={`research-workbench-controls${group ? "" : " research-empty-controls"}`}>
      <div className="research-scenarios"><button className={`btn small ${scenario === "pending" ? "primary" : ""}`} type="button" onClick={() => setScenario("pending")}>待处理</button><button className={`btn small ${scenario === "submitted" ? "primary" : ""}`} type="button" onClick={() => setScenario("submitted")}>我已提交</button>{props.canManage && <button className={`btn small ${scenario === "arrival_assignment" ? "primary" : ""}`} type="button" onClick={() => setScenario("arrival_assignment")}>到货待分配</button>}</div>
      <label>关键词<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="主 / 子 SKU、名称" /></label>
      <label>国家<select value={countryFilter} onChange={(event) => setCountryFilter(event.target.value)}><option value="">全部</option>{countryOptions.map((country) => <option value={country!} key={country}>{country}</option>)}</select></label>
      {scenario !== "arrival_assignment" && <label>业务期<select value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value)}><option value="__all__">全部期数</option>{periods.map((period) => <option value={period} key={period}>{period}</option>)}</select></label>}
      {!props.editable && scenario !== "arrival_assignment" && <label>负责人<select value={ownerFilter} onChange={(event) => setOwnerFilter(event.target.value)}><option value="">全部</option>{Array.from(new Set(allGroups.map((entry) => entry.salesperson_name))).sort().map((owner) => <option value={owner} key={owner}>{owner}</option>)}</select></label>}
      <button className="btn small" type="button" onClick={() => { setQuery(""); setCountryFilter(""); setOwnerFilter(""); setPeriodFilter("__all__"); }}>清空</button>
      <button className="btn small" type="button" disabled={loading} onClick={() => void (scenario === "arrival_assignment" ? loadPlmAssignments({ force: true }) : loadGroups({ force: true }))}>刷新</button>
      {scenario !== "arrival_assignment" && <button className="btn small" type="button" disabled={loading} onClick={() => void exportResearch()}>导出二次调研</button>}
      {scenario !== "arrival_assignment" && <button className="btn small" type="button" disabled={loading} onClick={() => void exportResearch("all")}>导出全部二调</button>}
      {scenario !== "arrival_assignment" && <button className="btn small primary" type="button" disabled={loading || (props.editable && !props.salespersonName)} onClick={openManualSecondary}><Plus size={13} />新增二调 SKU</button>}
    </div>
  );

  const manualSecondaryDialogNode = manualSecondary && (
    <div className="listing-overlay" role="presentation">
      <div
        className="listing-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="manual-secondary-title"
        tabIndex={-1}
        ref={manualSecondaryDialog}
      >
        <button aria-label="关闭新增二调 SKU" className="listing-dialog-close" type="button" onClick={closeManualSecondary}><X size={18} /></button>
        <h2 id="manual-secondary-title">新增二调 SKU</h2>
        <p>用于承接原来商品看板里没有的 SKU。新增后进入二次调研待处理，不发钉钉、不跑 PLM。</p>
        <div className="manual-listing-grid">
          <label>国家 *<select className={manualSecondaryErrors.country ? "listing-error-input" : ""} value={manualSecondary.country} onChange={(event) => updateManualSecondary("country", event.target.value)}>{MANUAL_SECONDARY_COUNTRIES.map((country) => <option value={country} key={country}>{country}</option>)}</select><FieldError message={manualSecondaryErrors.country} /></label>
          <label>负责人 *<input disabled={props.editable} className={manualSecondaryErrors.salesperson_name ? "listing-error-input" : ""} value={manualSecondary.salesperson_name} onChange={(event) => updateManualSecondary("salesperson_name", event.target.value)} /><FieldError message={manualSecondaryErrors.salesperson_name} /></label>
          <label>业务期<input value={manualSecondary.business_period} onChange={(event) => updateManualSecondary("business_period", event.target.value)} placeholder="默认当前自然周，可改" /></label>
          <label>主 SKU *<input className={manualSecondaryErrors.main_sku ? "listing-error-input" : ""} value={manualSecondary.main_sku} onChange={(event) => updateManualSecondary("main_sku", event.target.value)} /><FieldError message={manualSecondaryErrors.main_sku} /></label>
          <label>主 SKU 名称<input value={manualSecondary.main_sku_name} onChange={(event) => updateManualSecondary("main_sku_name", event.target.value)} /></label>
          <label>子 SKU *<input className={manualSecondaryErrors.sub_sku ? "listing-error-input" : ""} value={manualSecondary.sub_sku} onChange={(event) => updateManualSecondary("sub_sku", event.target.value)} /><FieldError message={manualSecondaryErrors.sub_sku} /></label>
          <label>子 SKU 名称<input value={manualSecondary.sub_sku_name} onChange={(event) => updateManualSecondary("sub_sku_name", event.target.value)} /></label>
          <label>锚定链接<input value={manualSecondary.secondary_competitor_url} onChange={(event) => updateManualSecondary("secondary_competitor_url", event.target.value)} placeholder="可选" /></label>
        </div>
        <div className="listing-dialog-actions">
          <button className="btn" type="button" onClick={closeManualSecondary}>取消</button>
          <button className="btn primary" type="button" disabled={loading} onClick={() => void submitManualSecondary()}>确认新增</button>
        </div>
      </div>
    </div>
  );

  async function assignPlmArrivalGroup(group: PlmArrivalAssignmentGroup) {
    const candidates = plmAssignmentOperatorsForGroup(group);
    const owner = assignmentOwners[group.groupKey] || candidates[0]?.operator_name || "";
    if (!owner) {
      props.onStatus("请选择要承接二调的运营");
      return;
    }
    setLoading(true);
    try {
      await api.assignPlmArrivalGroup(group.itemIds, owner);
      props.onStatus(`${group.mainSku || "PLM到货"} ${group.items.length} 个子 SKU 已指派给 ${owner}`);
      await Promise.all([loadPlmAssignments({ force: true }), loadGroups({ force: true })]);
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "PLM到货指派失败");
    } finally {
      setLoading(false);
    }
  }

  async function closePlmArrivalGroup(group: PlmArrivalAssignmentGroup) {
    const reason = (assignmentCloseReasons[group.groupKey] || "").trim();
    if (!reason) {
      props.onStatus("关闭到货待分配必须填写原因");
      return;
    }
    setLoading(true);
    try {
      await api.closePlmArrivalAssignmentGroup(group.itemIds, reason);
      props.onStatus(`${group.mainSku || "PLM到货"} ${group.items.length} 个子 SKU 已关闭，不进入二调`);
      await loadPlmAssignments({ force: true });
    } catch (error) {
      props.onStatus(error instanceof Error ? error.message : "PLM到货关闭失败");
    } finally {
      setLoading(false);
    }
  }

  if (scenario === "arrival_assignment") {
    return (
      <div className="secondary-workbench">
        {controls}
        <div className="plm-assignment-panel">
          <div className="research-meta-line">
            <span>待分配 <b>{visiblePlmAssignmentGroups.length}</b> 个主 SKU 组 / <b>{visiblePlmAssignments.length}</b> 个子 SKU</span>
            <span>规则 <b>未指派前不分给 PLM 销售员，不发运营通知</b></span>
          </div>
          {loading && !visiblePlmAssignmentGroups.length ? <div className="research-empty">正在加载 PLM 到货待分配...</div> : null}
          {!loading && !visiblePlmAssignmentGroups.length ? <div className="research-empty"><b>当前筛选下没有到货待分配记录</b></div> : null}
          {visiblePlmAssignmentGroups.map((group) => (
            <div className="plm-assignment-row" key={group.groupKey}>
              <div>
                <b>{group.mainSku || "-"}</b> <span className="muted">/ {group.items.length} 个子 SKU</span>
                <div className="muted">{group.productName || "未填写商品名"}</div>
                <div className="research-meta-line">
                  <span>{group.country || "-"}</span>
                  <span>PLM销售员：{group.plmSalespeople.join("、") || "-"}</span>
                  <span>首次上架：{formatDateTime(group.firstListingTime)}</span>
                  <span>源：{group.sourceSummary}</span>
                  <span>当前商品命中：{group.existingOpportunityCount}</span>
                  {group.systemBusinessPeriods.length ? <span>系统期数：{group.systemBusinessPeriods.join("、")}</span> : null}
                </div>
                <div className="research-meta-line">
                  {group.items.map((item) => (
                    <span key={item.plm_arrival_item_id}>{item.sub_sku || "-"}：{item.product_name || "-"}</span>
                  ))}
                </div>
                <div className={group.assignmentBlockReason ? "plm-assignment-warning" : "muted"}>
                  {group.assignmentBlockReason || group.assignmentHint || "选择承接运营后才会整组进入二次调研"}
                </div>
              </div>
              <div className="plm-assignment-actions">
                <select
                  value={assignmentOwners[group.groupKey] || ""}
                  onChange={(event) => setAssignmentOwners((current) => ({ ...current, [group.groupKey]: event.target.value }))}
                >
                  <option value="">选择承接运营</option>
                  {plmAssignmentOperatorsForGroup(group).map((operator) => <option value={operator.operator_name} key={operator.id}>{operator.operator_name}</option>)}
                </select>
                <button
                  className="btn small primary"
                  type="button"
                  disabled={loading || Boolean(group.assignmentBlockReason)}
                  onClick={() => void assignPlmArrivalGroup(group)}
                >
                  整组指派进二调
                </button>
                <input
                  value={assignmentCloseReasons[group.groupKey] || ""}
                  placeholder="暂不推进原因"
                  onChange={(event) => setAssignmentCloseReasons((current) => ({ ...current, [group.groupKey]: event.target.value }))}
                />
                <button className="btn small danger" type="button" disabled={loading} onClick={() => void closePlmArrivalGroup(group)}>整组关闭</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (loading && !group) return <div className="secondary-workbench">{controls}<div className="research-empty">正在加载二次调研任务...</div>{manualSecondaryDialogNode}</div>;
  if (!group) return <div className="secondary-workbench">{controls}<div className="research-empty"><b>{scenario === "submitted" ? "当前筛选下没有已提交记录" : "当前筛选下没有待处理记录"}</b></div>{manualSecondaryDialogNode}</div>;

  const primaryImageItem = group.items.find((item) => item.image_url) || group.items[0];

  return (
    <div className="secondary-workbench">
      {controls}
      {manualSecondaryDialogNode}
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
  const isSelection2 = isSelection2Item({ source_type: props.group.source_type });
  const drawerModules = isSelection2 ? selection2DrawerModules : selection1DrawerModules;
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
                  <span>{isSelection2 ? "产品名称" : "类目"} <b>{columnValue(first, "D") || "-"}</b></span>
                  <span>{isSelection2 ? "规格属性" : "关键词"} <b>{columnValue(first, "E") || "-"}</b></span>
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
              <span>调研结论</span>
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
                <span>商品定位</span>
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
      {item?.image_url ? <img src={productThumbSrc(item.image_url)} alt={item.sub_sku_name || item.sub_sku} /> : "图"}
    </div>
  );
}

function ResearchSkuCell({ item, children, onOpenDetail, hideThumb }: { item: SecondaryResearchItem; children?: ReactNode; onOpenDetail?: () => void; hideThumb?: boolean }) {
  return (
    <div className={hideThumb ? "research-sku-cell research-sku-content no-thumb" : "research-sku-cell research-sku-content"}>
      {!hideThumb && (
        <div className="research-thumb">
          {item.image_url ? <img src={productThumbSrc(item.image_url)} alt={item.sub_sku_name || item.sub_sku} /> : "图"}
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
  const columns = sourceModuleColumns(group, moduleKey);
  const linkEntries = group.items.flatMap((item) => columns.map((column) => ({
    key: `${item.claim_record_id}:${column}`,
    value: columnValue(item, column)
  })).filter((entry) => isUrl(entry.value)));
  const linkLabels = researchLinkLabels(linkEntries.map((item) => item.value));
  const linkLabelByKey = new Map(linkEntries.map((entry, index) => [entry.key, linkLabels[index]]));
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
            const linkLabel = linkLabelByKey.get(`${item.claim_record_id}:${column}`);
            return (
              <div className="research-source-value" key={column} title={value}>
                {isUrl(value) && linkLabel ? (
                  <a
                    className={`research-link-chip tone-${linkLabel.tone}${linkLabel.repeated ? " repeated" : ""}`}
                    href={value}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {linkLabel.label} <ExternalLink size={13} />
                  </a>
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
          <div className="research-source-value">{formatBusinessNumber(item.claim_daily_sales) || "-"}</div>
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

function sourceModuleColumns(group: SecondaryResearchGroup, moduleKey: SourceModuleKey) {
  if (isSelection2Item({ source_type: group.source_type })) {
    return Array.from(new Set(
      group.items.flatMap((item) =>
        selection2HeaderFields(
          { source_type: group.source_type, snapshot: item.snapshot },
          selection2ModuleSections[moduleKey]
        ).map((field) => field.column)
      )
    )).sort((left, right) => columnNumber(left) - columnNumber(right));
  }
  return moduleColumns[moduleKey].filter(
    (column) => !isSourceClaimInputLabel(columnHeader(group.items[0], column))
  );
}

function draftPayload(draft: SecondaryResearchDraft<UploadedEvidenceImage>) {
  return {
    secondary_competitor_url: draft.competitorUrl.trim() || null,
    secondary_conclusion: draft.conclusion.trim() || null,
    product_positioning: draft.positioning || null,
    secondary_target_daily_sales: secondaryResearchTargetDailySalesValue(draft),
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
  return formatBeijingDateTime(value);
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

function FieldError({ message }: { message?: string }) {
  return message ? <small className="listing-field-error">{message}</small> : null;
}
