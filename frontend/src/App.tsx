import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardPen,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  GripVertical,
  LayoutDashboard,
  PackageOpen,
  Plus,
  RefreshCw,
  Save,
  Search,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
  UserCheck,
  UserRoundPlus,
  Users,
  WandSparkles,
  X,
  XCircle
} from "lucide-react";
import { ChangeEvent, ClipboardEvent, Dispatch, DragEvent, FormEvent, ReactNode, SetStateAction, useEffect, useMemo, useState } from "react";
import { formatBusinessNumber, formatBusinessValue } from "./businessFormat";
import {
  API_BASE,
  api,
  AssignmentPreviewItem,
  AuthSession,
  AvailableStockingItem,
  ExportPeriodSummary,
  getAuthToken,
  ImportBatchSummary,
  Opportunity,
  OperatorAssignmentProfile,
  PlmArrivalPreview,
  Selection1ImportResponse,
  setAuthToken,
  Task
} from "./api";
import { ClaimDraftState, claimSubmissionState, createClaimDraft, createClaimDraftFromLatest, formatRejectReason, parseClaimEvidenceImages, parseRejectReason, patchClaimDraftGroup, REJECT_REASON_OPTIONS } from "./claimDrafts";
import { filterAssignmentItems, groupOperatorProfilesBySite, moveOperatorWithinSite, reorderOperatorWithinSite, sortOperatorProfiles } from "./assignmentFilters";
import { competitorGroupForColumn, competitorGroupForLabel } from "./competitorGroups";
import { ImportResults, recordImportResult } from "./importResults";
import { businessPeriodsByNewest, filterOperatorClaimRows, latestBusinessPeriod, operatorClaimStatusOptions } from "./operatorClaimFilters";
import { groupByBusinessIdentity, normalizeSiteText } from "./opportunityGroups";
import { adjacentDetailTarget } from "./productDetailNavigation";
import { ProductBoardView } from "./ProductBoardView";
import { SecondaryResearchView } from "./SecondaryResearchView";
import { isSourceClaimInputLabel, selection1ColumnLabel } from "./selection1Columns";
import { ListingObservationSummary, ListingObservationView } from "./ListingObservationView";
import { compactUrlLabel } from "./urlDisplay";
import { exportPeriodFilter, filterRowsForExportPeriod, selectExportPeriod } from "./exportPeriods";
import { imageFiles } from "./imageUploads";

type DingTalkAuthCodeResult = {
  authCode?: string;
  code?: string;
};

type DingTalkAuthCodeOptions = {
  corpId?: string;
  onSuccess: (result: DingTalkAuthCodeResult) => void;
  onFail?: (error: unknown) => void;
};

declare global {
  interface Window {
    dd?: {
      runtime?: {
        permission?: {
          requestAuthCode?: (options: DingTalkAuthCodeOptions) => void;
        };
      };
    };
  }
}

type RoleKey = "operator" | "manager";
type ViewKey = "dashboard" | "source" | "pool" | "assign" | "claim" | "review" | "stock" | "research" | "listing";

type ProductGroup = {
  key: string;
  main_sku: string;
  items: Opportunity[];
  first: Opportunity;
  status: string;
};

type DashboardFilters = {
  query: string;
  status: string;
  health: string;
  site: string;
  owner: string;
  category: string;
  source: string;
};

type ListState = {
  query: string;
  page: number;
  pageSize: number;
};

type EvidenceImage = {
  id: string;
  name: string;
  type: string;
  size: number;
  previewUrl: string;
  url?: string;
};

type SubmittedEvidenceImage = {
  name: string;
  type: string;
  size: number;
  previewUrl?: string;
};

type ClaimDraft = ClaimDraftState<EvidenceImage>;

type ReviewDraft = {
  reviewerName: string;
  reviewStatus: string;
  reviewComment: string;
};

type AssignmentLoad = {
  groups: number;
  subSkus: number;
  draftGroups: number;
  draftSubSkus: number;
};

type DetailSectionKey = "core" | "development" | "market" | "pricing" | "cost" | "claim" | "listing" | "source";
type ClaimDrawerModuleKey = "market" | "pricing" | "development" | "cost";

const flowItems: { view: ViewKey; roles: RoleKey[]; icon: ReactNode; label: string }[] = [
  { view: "source", roles: ["manager"], icon: <FileSpreadsheet size={16} />, label: "源表导入" },
  { view: "pool", roles: ["operator", "manager"], icon: <Database size={16} />, label: "新品机会池" },
  { view: "assign", roles: ["manager"], icon: <UserRoundPlus size={16} />, label: "分配台" },
  { view: "claim", roles: ["operator"], icon: <ClipboardPen size={16} />, label: "运营认领" },
  { view: "review", roles: ["manager"], icon: <ShieldCheck size={16} />, label: "主管复核" },
  { view: "stock", roles: ["manager"], icon: <Download size={16} />, label: "导出中心" },
  { view: "research", roles: ["operator", "manager"], icon: <ClipboardPen size={16} />, label: "二次调研" },
  { view: "listing", roles: ["operator", "manager"], icon: <FileCheck2 size={16} />, label: "刊登与观察" }
];

const viewMeta: Record<ViewKey, { title: string; desc: string }> = {
  dashboard: { title: "商品看板", desc: "按主 SKU 分组查看全部商品当前状态，展开可看子 SKU 状态。" },
  source: { title: "源表导入", desc: "第一版只导入两张内部反馈表，写入平台数据库，不提供在线表自动写回入口。" },
  pool: { title: "新品机会池", desc: "默认按状态优先展示主 SKU 分组；展开后查看子 SKU 明细和来源追溯。" },
  assign: { title: "分配台", desc: "主管按主 SKU 整组生成推荐，可逐行调整最终分配；系统先按站点过滤，再按当前负载均衡，负载相同时看重点品类和优先级。" },
  claim: { title: "运营认领", desc: "分配任务必须认领或不认领；财根机会池允许其他运营自认领，人数不限。" },
  review: { title: "主管复核", desc: "主管只能通过、确认不认领或退回补充，不允许代改运营填写内容。" },
  stock: { title: "导出中心", desc: "只导出 Excel。按子 SKU 明细出行，同一子 SKU 被不同运营认领时另起一行。" },
  research: { title: "二次调研", desc: "按主 SKU 整组处理到货后的复查；全部子 SKU 在同一界面填写，草稿自动保存。" },
  listing: { title: "刊登与观察工作台", desc: "按主 SKU 新增店铺与 Item，并逐周期完成数据复盘。" }
};

const statusMeta: Record<string, { label: string; klass: string }> = {
  pending_assignment: { label: "待分配", klass: "amber" },
  open_claim_pool: { label: "财根机会池", klass: "amber" },
  assigned: { label: "待认领", klass: "amber" },
  returned_for_supplement: { label: "已驳回-待运营补充", klass: "red" },
  claim_submitted: { label: "待复核-认领", klass: "amber" },
  claim_rejected: { label: "待复核-不认领", klass: "red" },
  ready_for_stocking: { label: "可备货", klass: "green" },
  waiting_arrival: { label: "待到货", klass: "blue" },
  waiting_secondary_research: { label: "待二次调研", klass: "amber" },
  waiting_listing: { label: "待刊登", klass: "blue" },
  confirmed_not_claim: { label: "已确认不认领", klass: "gray" },
  已确认不认领: { label: "已确认不认领", klass: "gray" },
  disabled: { label: "已停用", klass: "gray" },
  mixed: { label: "多状态", klass: "blue" }
};

const defaultDashboardFilters: DashboardFilters = {
  query: "",
  status: "",
  health: "",
  site: "",
  owner: "",
  category: "",
  source: ""
};

const defaultListState: ListState = { query: "", page: 1, pageSize: 50 };

const operatorClaimStatuses = new Set(["assigned", "open_claim_pool", "returned_for_supplement", "claim_submitted", "claim_rejected"]);
const OSS_PUBLIC_BASE = "https://hz-sea-np-flow-prod.oss-cn-shanghai.aliyuncs.com";
const DINGTALK_CORP_ID = import.meta.env.VITE_DINGTALK_CORP_ID || "";

function readDingTalkAuthCodeFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("authCode") || params.get("auth_code") || params.get("code") || "";
}

function isDingTalkAutoLoginEntry() {
  const params = new URLSearchParams(window.location.search);
  return Boolean(readDingTalkAuthCodeFromUrl()) || params.get("from") === "ding" || navigator.userAgent.toLowerCase().includes("dingtalk");
}

function requestDingTalkAuthCode() {
  const requestAuthCode = window.dd?.runtime?.permission?.requestAuthCode;
  if (!requestAuthCode) return Promise.reject(new Error("missing DingTalk bridge"));
  return new Promise<string>((resolve, reject) => {
    requestAuthCode({
      corpId: DINGTALK_CORP_ID || undefined,
      onSuccess: (result) => {
        const code = result.authCode || result.code || "";
        if (code) resolve(code);
        else reject(new Error("missing DingTalk auth code"));
      },
      onFail: reject
    });
  });
}

function isCaigenOpportunity(item: Opportunity) {
  return item.source_type === "selection2_caigen_claim_feedback" || Boolean(item.source_file?.includes("财根"));
}

function isSelfClaimPoolItem(item: Opportunity) {
  return item.current_status === "open_claim_pool" || (item.current_status === "pending_assignment" && isCaigenOpportunity(item));
}

function isOperatorClaimItem(item: Opportunity) {
  return operatorClaimStatuses.has(item.current_status) || isSelfClaimPoolItem(item);
}

function isVisibleOperatorClaimItem(item: Opportunity, assignedOpportunityIds: Set<string>) {
  if (!operatorClaimStatuses.has(item.current_status)) return false;
  return assignedOpportunityIds.has(item.id);
}

function isOwnSubmittedClaim(item: Opportunity, activeOperator: string) {
  return ["claim_submitted", "claim_rejected"].includes(item.current_status) && item.latest_claim_salesperson === activeOperator;
}

function isPoolItem(item: Opportunity, role: RoleKey) {
  if (role === "manager") return isSelfClaimPoolItem(item);
  return isSelfClaimPoolItem(item);
}

function claimSourceFor(item: Opportunity) {
  return isSelfClaimPoolItem(item) ? "caigen_self_claim" : "assigned_task";
}

function claimTypeLabel(item: Opportunity) {
  if (isSelfClaimPoolItem(item)) return "财根自领机会";
  if (item.current_status === "returned_for_supplement") return "退回补充";
  return "分配任务";
}

function App() {
  const [activeRole, setActiveRole] = useState<RoleKey>("manager");
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [authChecked, setAuthChecked] = useState(false);
  const [authSession, setAuthSession] = useState<AuthSession | null>(null);
  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [passwordPanelOpen, setPasswordPanelOpen] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ old_password: "", new_password: "", confirm_password: "" });
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [healthStatus, setHealthStatus] = useState("checking");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [operatorProfiles, setOperatorProfiles] = useState<OperatorAssignmentProfile[]>([]);
  const [importBatches, setImportBatches] = useState<ImportBatchSummary[]>([]);
  const [activeOperator, setActiveOperator] = useState("");
  const [availableStocking, setAvailableStocking] = useState<AvailableStockingItem[]>([]);
  const [exportPeriods, setExportPeriods] = useState<ExportPeriodSummary[]>([]);
  const [lastImports, setLastImports] = useState<ImportResults>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [source1Sheet, setSource1Sheet] = useState("");
  const [source2Sheet, setSource2Sheet] = useState("");
  const [source1BusinessPeriod, setSource1BusinessPeriod] = useState("");
  const [source1PeriodTouched, setSource1PeriodTouched] = useState(false);
  const [source1Sheets, setSource1Sheets] = useState<string[]>([]);
  const [source2Sheets, setSource2Sheets] = useState<string[]>([]);
  const [source1File, setSource1File] = useState<File | null>(null);
  const [source2File, setSource2File] = useState<File | null>(null);
  const [previewItems, setPreviewItems] = useState<AssignmentPreviewItem[]>([]);
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, string>>({});
  const [profilePanelOpen, setProfilePanelOpen] = useState(false);
  const [claimDrafts, setClaimDrafts] = useState<Record<string, ClaimDraft>>({});
  const [reviewTarget, setReviewTarget] = useState<Opportunity | null>(null);
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, ReviewDraft>>({});
  const [detailGroupKey, setDetailGroupKey] = useState<string | null>(null);
  const [detailChildId, setDetailChildId] = useState<string | null>(null);
  const [claimDetailChildId, setClaimDetailChildId] = useState<string | null>(null);
  const [dashboardFilters, setDashboardFilters] = useState<DashboardFilters>(defaultDashboardFilters);
  const [dashboardList, setDashboardList] = useState<ListState>(defaultListState);
  const [poolList, setPoolList] = useState<ListState>(defaultListState);
  const [assignList, setAssignList] = useState<ListState>(defaultListState);
  const [claimList, setClaimList] = useState<ListState>(defaultListState);
  const [reviewList, setReviewList] = useState<ListState>(defaultListState);
  const [arrivalDate, setArrivalDate] = useState(previousDateText());
  const [arrivalPreview, setArrivalPreview] = useState<PlmArrivalPreview | null>(null);
  const [arrivalList, setArrivalList] = useState<ListState>(defaultListState);
  const [stockList, setStockList] = useState<ListState>(defaultListState);
  const [selectedSelfClaimIds, setSelectedSelfClaimIds] = useState<string[]>([]);
  const [newProfile, setNewProfile] = useState<Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "assignment_priority" | "enabled">>({
    operator_name: "",
    key_site: "",
    key_category1: "",
    key_category2: "",
    assignment_priority: 0,
    enabled: true
  });

  const availableRoles = useMemo(
    () => {
      if (!authSession) return ["operator", "manager"] as RoleKey[];
      const roles = new Set<RoleKey>();
      for (const item of authSession.roles) {
        if (item.role === "super_admin") {
          roles.add("manager");
          roles.add("operator");
        } else {
          roles.add(item.role);
        }
      }
      return Array.from(roles);
    },
    [authSession]
  );
  const visibleFlow = useMemo(() => flowItems.filter((item) => item.roles.includes(activeRole)), [activeRole]);
  const groups = useMemo(() => groupOpportunities(opportunities), [opportunities]);
  const dashboardGroups = useMemo(() => filterDashboardGroups(groups, dashboardFilters), [groups, dashboardFilters]);
  const dashboardOptions = useMemo(() => buildDashboardOptions(groups), [groups]);
  const poolGroups = useMemo(() => groups.filter((group) => group.items.some((item) => isPoolItem(item, activeRole))), [activeRole, groups]);
  const pendingAssignGroups = useMemo(
    () => groups.map(toPendingAssignmentGroup).filter((group): group is ProductGroup => Boolean(group)),
    [groups]
  );
  const assignableIds = useMemo(
    () => pendingAssignGroups.flatMap((group) => group.items.map((item) => item.id)),
    [pendingAssignGroups]
  );
  const assignmentItems = useMemo(
    () => (previewItems.length ? previewItems : pendingAssignGroups.map(groupToAssignmentItem)),
    [pendingAssignGroups, previewItems]
  );
  const assignSummary = useMemo(
    () => ({
      enabledCount: operatorProfiles.filter((profile) => profile.enabled).length,
      groupCount: pendingAssignGroups.length,
      childCount: assignableIds.length,
      selectedGroupCount: assignmentItems.filter((item) => assignmentDrafts[assignmentItemKey(item)]).length,
      unassignedGroupCount: assignmentItems.length
        ? assignmentItems.filter((item) => !assignmentDrafts[assignmentItemKey(item)]).length
        : pendingAssignGroups.length
    }),
    [assignableIds.length, assignmentDrafts, assignmentItems, operatorProfiles, pendingAssignGroups.length]
  );
  const activeOperatorTaskOpportunityIds = useMemo(
    () =>
      new Set(
        tasks
          .filter((task) => task.task_type === "sales_claim" && ["pending", "completed"].includes(task.status) && task.assignee_name === activeOperator)
          .map((task) => task.opportunity_id)
          .filter((id): id is string => Boolean(id))
      ),
    [activeOperator, tasks]
  );
  const isSuperAdmin = Boolean(authSession?.roles.some((item) => item.role === "super_admin"));
  const canManage = Boolean(authSession?.roles.some((item) => item.role === "manager" || item.role === "super_admin"));
  const selectedSelfClaimIdSet = useMemo(() => new Set(selectedSelfClaimIds), [selectedSelfClaimIds]);
  const claimRows = useMemo(
    () =>
      opportunities.filter(
        (item) =>
          isVisibleOperatorClaimItem(item, activeOperatorTaskOpportunityIds) ||
          isOwnSubmittedClaim(item, activeOperator) ||
          (selectedSelfClaimIdSet.has(item.id) && isSelfClaimPoolItem(item))
      ),
    [activeOperator, activeOperatorTaskOpportunityIds, opportunities, selectedSelfClaimIdSet]
  );
  const reviewRows = useMemo(
    () => opportunities.filter((item) => ["claim_submitted", "claim_rejected"].includes(item.current_status)),
    [opportunities]
  );
  const detailGroup = useMemo(
    () => (detailGroupKey ? groups.find((group) => group.key === detailGroupKey) || null : null),
    [detailGroupKey, groups]
  );
  const detailSequence = useMemo(
    () => groups.flatMap((group) => group.items.map((item) => ({ groupKey: group.key, childId: item.id }))),
    [groups]
  );
  const detailSequenceIndex = detailGroup
    ? detailSequence.findIndex(
        (entry) => entry.groupKey === detailGroup.key && entry.childId === (detailChildId || detailGroup.items[0]?.id)
      )
    : -1;
  const stats = useMemo(() => buildStats(opportunities, tasks, availableStocking), [opportunities, tasks, availableStocking]);

  function openProductDetail(group: ProductGroup, childId?: string | null) {
    setDetailGroupKey(group.key);
    setDetailChildId(childId || group.items[0]?.id || null);
  }

  function navigateProductDetail(delta: -1 | 1, currentChildId: string) {
    if (!detailGroupKey) return;
    const target = adjacentDetailTarget(groups, detailGroupKey, currentChildId, delta);
    if (!target) return;
    setDetailGroupKey(target.groupKey);
    setDetailChildId(target.childId);
  }

  function openOpportunityDetail(item: Opportunity) {
    const group = groups.find((entry) => entry.items.some((child) => child.id === item.id));
    if (group) openProductDetail(group, item.id);
  }

  function openClaimDetail(group: ProductGroup, childId?: string | null) {
    setClaimDetailChildId(childId || group.items[0]?.id || null);
  }

  function addSelfClaimGroup(group: ProductGroup) {
    const ids = group.items.filter(isSelfClaimPoolItem).map((item) => item.id);
    if (!ids.length) return;
    setSelectedSelfClaimIds((current) => Array.from(new Set([...current, ...ids])));
    setActiveRole("operator");
    setActiveView("claim");
  }

  function removeSelfClaimItem(id: string) {
    setSelectedSelfClaimIds((current) => current.filter((itemId) => itemId !== id));
    setClaimDrafts((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      const token = getAuthToken();
      if (token) {
        try {
          const session = await api.me();
          if (!cancelled) applyAuthSession(session);
          return;
        } catch {
          setAuthToken("");
        }
      }
      if (!isDingTalkAutoLoginEntry()) return;
      if (!cancelled) {
        setLoading(true);
        setStatusMessage("正在通过钉钉登录...");
      }
      try {
        const authCode = readDingTalkAuthCodeFromUrl() || (await requestDingTalkAuthCode());
        const session = await api.dingtalkLogin({ auth_code: authCode });
        if (!cancelled) {
          applyAuthSession(session);
          setStatusMessage("");
        }
      } catch {
        if (!cancelled) setStatusMessage("钉钉免登失败，请使用账号密码登录");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    checkAuth().finally(() => {
      if (!cancelled) setAuthChecked(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (activeView !== "claim") setClaimDetailChildId(null);
  }, [activeView]);

  useEffect(() => {
    if (authChecked && authSession) refresh();
  }, [authChecked, authSession]);

  useEffect(() => {
    const token = getAuthToken();
    if (!authSession || !token) return;
    let seenInitialEvent = false;
    let refreshWhenVisible = false;
    const source = new EventSource(`${API_BASE}/events/stream?token=${encodeURIComponent(token)}`);

    source.onmessage = () => {
      if (!seenInitialEvent) {
        seenInitialEvent = true;
        return;
      }
      if (document.hidden) {
        refreshWhenVisible = true;
        return;
      }
      void refresh({ silent: true });
    };

    const onVisible = () => {
      if (!document.hidden && refreshWhenVisible) {
        refreshWhenVisible = false;
        void refresh({ silent: true });
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      source.close();
    };
  }, [authSession?.access_token]);

  useEffect(() => {
    if (activeView !== "dashboard" && !visibleFlow.some((item) => item.view === activeView)) {
      setActiveView(activeRole === "manager" ? "source" : "pool");
    }
  }, [activeRole, activeView, visibleFlow]);

  useEffect(() => {
    setSelectedSelfClaimIds((current) => {
      const valid = new Set(opportunities.filter(isSelfClaimPoolItem).map((item) => item.id));
      const next = current.filter((id) => valid.has(id));
      return next.length === current.length ? current : next;
    });
  }, [opportunities]);

  useEffect(() => {
    if (activeRole !== "operator") return;
    if (authSession?.operator_name && !canManage) {
      if (activeOperator !== authSession.operator_name) setActiveOperator(authSession.operator_name);
      return;
    }
    if (activeOperator && operatorProfiles.some((profile) => profile.enabled && profile.operator_name === activeOperator)) return;
    setActiveOperator(sortOperatorProfiles(operatorProfiles.filter((profile) => profile.enabled))[0]?.operator_name || "");
  }, [activeOperator, activeRole, authSession, canManage, operatorProfiles]);

  useEffect(() => {
    if (!statusMessage || statusMessage.includes("中...") || statusMessage.includes("正在") || statusMessage.includes("失败") || statusMessage.includes("Error")) return;
    const timer = window.setTimeout(() => setStatusMessage(""), 2400);
    return () => window.clearTimeout(timer);
  }, [statusMessage]);

  useEffect(() => {
    setDetailGroupKey(null);
  }, [activeView]);

  function applyAuthSession(session: AuthSession) {
    setAuthSession(session);
    setAuthToken(session.access_token);
    setActiveRole(session.default_role);
    if (session.operator_name) setActiveOperator(session.operator_name);
    setLoginName(session.user.name);
  }

  async function loginLocal() {
    const name = loginName.trim();
    if (!name || !loginPassword) {
      setStatusMessage("请输入账号和密码");
      return;
    }
    await runAction("登录", async () => {
      const session = await api.login({ name, password: loginPassword });
      applyAuthSession(session);
      setLoginPassword("");
    });
  }

  async function logout() {
    setAuthSession(null);
    setAuthToken("");
    setActiveRole("manager");
    setActiveView("dashboard");
    setOpportunities([]);
    setTasks([]);
    setAvailableStocking([]);
    setExportPeriods([]);
    setOperatorProfiles([]);
    setImportBatches([]);
  }

  async function changeOwnPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (passwordForm.new_password !== passwordForm.confirm_password) {
      setStatusMessage("两次新密码不一致");
      return;
    }
    await runAction("修改密码", async () => {
      await api.changePassword({
        old_password: passwordForm.old_password,
        new_password: passwordForm.new_password
      });
      setPasswordForm({ old_password: "", new_password: "", confirm_password: "" });
      setPasswordPanelOpen(false);
    });
  }

  async function refresh(options: { silent?: boolean } = {}) {
    if (!options.silent) setLoading(true);
    const failures: string[] = [];
    async function loadPart<T>(label: string, loader: () => Promise<T>, fallback: T): Promise<T> {
      try {
        return await loader();
      } catch {
        failures.push(label);
        return fallback;
      }
    }
    const [health, opportunityList, taskList, stockingList, exportPeriodList, profileList, batchList] = await Promise.all([
      loadPart("健康检查", api.health, { status: "error", environment: "unknown" }),
      loadPart("机会池", () => api.opportunities(5000, undefined, isSuperAdmin), []),
      loadPart("待办", api.tasks, []),
      loadPart("导出中心", api.availableStocking, availableStocking),
      loadPart("导出期数", api.exportPeriods, exportPeriods),
      loadPart("人员配置", api.operatorProfiles, []),
      canManage ? loadPart("导入批次", api.importBatches, []) : Promise.resolve([])
    ]);
    setHealthStatus(health.status);
    setOpportunities(opportunityList);
    setTasks(taskList);
    setAvailableStocking(stockingList);
    setExportPeriods(exportPeriodList);
    setOperatorProfiles(profileList);
    setImportBatches(batchList);
    if (!options.silent || failures.length) {
      setStatusMessage(failures.length ? `部分数据未加载：${failures.join("、")}` : "已刷新");
    }
    if (!options.silent) setLoading(false);
  }

  async function loadPlmArrivalPreview() {
    setLoading(true);
    try {
      const preview = await api.plmArrivalPreview(arrivalDate);
      setArrivalPreview(preview);
      setArrivalList((current) => ({ ...current, page: 1 }));
      setStatusMessage(`已加载 ${preview.date} 到货预览`);
    } catch (error) {
      setArrivalPreview(null);
      setStatusMessage(error instanceof Error ? error.message : "到货预览加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function runAction(label: string, action: () => Promise<unknown>) {
    setLoading(true);
    setStatusMessage(`${label}中...`);
    try {
      await action();
      setStatusMessage(`${label}完成`);
      await refresh({ silent: true });
      return true;
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : `${label}失败`);
      return false;
    } finally {
      setLoading(false);
    }
  }

  function updateSourceSheet(kind: 1 | 2, value: string) {
    if (kind === 1) {
      setSource1Sheet(value);
      if (!source1PeriodTouched) setSource1BusinessPeriod(value);
    } else {
      setSource2Sheet(value);
    }
  }

  function updateBusinessPeriod(value: string) {
    setSource1PeriodTouched(true);
    setSource1BusinessPeriod(value);
  }

  async function importSelection(kind: 1 | 2) {
    await runAction(`导入选品${kind}`, async () => {
      const selectedFile = kind === 1 ? source1File : source2File;
      if (!selectedFile) throw new Error(`请先选择选品${kind}反馈表 Excel 文件`);
      const result =
        kind === 1
          ? await api.importSelection1File(source1Sheet, source1BusinessPeriod, selectedFile)
          : await api.importSelection2File(source2Sheet, selectedFile);
      setLastImports((current) => recordImportResult(current, kind, result));
      setActiveView(kind === 1 ? "assign" : "pool");
    });
  }

  async function previewAssignments() {
    if (!assignableIds.length) {
      setStatusMessage("没有待分配的主 SKU 组");
      return [];
    }
    const result = await api.assignmentPreview(assignableIds, []);
    setPreviewItems(result.items);
    setAssignmentDrafts(
      Object.fromEntries(result.items.map((item) => [assignmentItemKey(item), item.suggested_assignee || ""]))
    );
    setStatusMessage(`已生成 ${result.items.length} 个主 SKU 分配建议`);
    return result.items;
  }

  function cancelAssignmentPreview() {
    setPreviewItems([]);
    setAssignmentDrafts({});
    setStatusMessage("已取消本次分配推荐");
  }

  async function submitAssignments() {
    await runAction("提交分配", async () => {
      if (!assignmentItems.length) throw new Error("没有待分配的主 SKU 组");
      const idsByAssignee = new Map<string, string[]>();
      const currentAssignableIds = new Set(assignableIds);
      for (const item of assignmentItems) {
        const assignee = assignmentDrafts[assignmentItemKey(item)];
        if (!assignee) continue;
        const opportunityIds = item.opportunity_ids.filter((id) => currentAssignableIds.has(id));
        if (!opportunityIds.length) continue;
        idsByAssignee.set(assignee, [...(idsByAssignee.get(assignee) || []), ...opportunityIds]);
      }
      if (!idsByAssignee.size) throw new Error("没有选择最终分配人");
      for (const [assignee, opportunityIds] of idsByAssignee) {
        await api.assignmentConfirm(opportunityIds, assignee);
      }
      setPreviewItems([]);
      setAssignmentDrafts({});
      setActiveView("pool");
    });
  }

  async function submitClaimPayload(payload: unknown | unknown[]) {
    return runAction(Array.isArray(payload) ? "批量提交认领" : "提交认领", async () => {
      const payloads = Array.isArray(payload) ? payload : [payload];
      for (const item of payloads) {
        await api.claim(item);
      }
    });
  }

  async function updateOpportunityDetails(id: string, payload: unknown) {
    await runAction("保存 SKU 信息", async () => {
      const updated = await api.updateOpportunity(id, payload);
      setDetailGroupKey(groupByBusinessIdentity([updated])[0]?.key || null);
    });
  }

  async function saveProfiles() {
    await runAction("保存人员配置", async () => {
      for (const profile of operatorProfiles) {
        await api.updateOperatorProfile(profile.id, {
          operator_name: profile.operator_name,
          key_site: profile.key_site || "",
          key_category1: profile.key_category1 || "",
          key_category2: profile.key_category2 || "",
          assignment_priority: Number(profile.assignment_priority || 0),
          display_order: profile.display_order || 0,
          enabled: profile.enabled
        });
      }
    });
  }

  async function addProfile() {
    await runAction("新增人员配置", async () => {
      if (!newProfile.operator_name.trim()) throw new Error("运营不能为空");
      await api.createOperatorProfile(newProfile);
      setNewProfile({ operator_name: "", key_site: "", key_category1: "", key_category2: "", assignment_priority: 0, enabled: true });
    });
  }

  async function removeProfile(profileId: string) {
    await runAction("删除人员配置", async () => {
      await api.deleteOperatorProfile(profileId);
    });
  }

  async function setOpportunityDisabled(item: Opportunity, disabled: boolean) {
    const reason = window.prompt(disabled ? "请输入停用原因" : "请输入恢复原因", "");
    if (reason === null) return;
    await runAction(disabled ? "停用 SKU" : "恢复 SKU", async () => {
      await api.disableOpportunity(item.id, { disabled, reason });
    });
  }

  async function setOpportunityGroupDisabled(group: ProductGroup, disabled: boolean) {
    const reason = window.prompt(disabled ? "请输入停用整组原因" : "请输入恢复整组原因", "");
    if (reason === null) return;
    await runAction(disabled ? "停用主 SKU 组" : "恢复主 SKU 组", async () => {
      await api.disableOpportunityGroup(group.first.id, { disabled, reason });
    });
  }

  async function setImportBatchDisabled(batch: ImportBatchSummary, disabled: boolean) {
    const reason = window.prompt(disabled ? "请输入停用批次原因" : "请输入恢复批次原因", "");
    if (reason === null) return;
    await runAction(disabled ? "停用导入批次" : "恢复导入批次", async () => {
      await api.disableImportBatch(batch.id, { disabled, reason });
    });
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewTarget) return;
    const targetId = reviewTarget.id;
    const form = new FormData(event.currentTarget);
    await runAction("提交复核", async () => {
      await api.review({
        opportunity_id: targetId,
        claim_record_id: reviewTarget.latest_claim_record_id || undefined,
        reviewer_name: String(form.get("reviewer_name") || "练玉君"),
        review_status: String(form.get("review_status") || "approved"),
        review_comment: String(form.get("review_comment") || "")
      });
      setReviewDrafts((current) => {
        const next = { ...current };
        delete next[targetId];
        return next;
      });
      setReviewTarget(null);
    });
  }

  async function bulkReview(items: Opportunity[], action: "approve" | "reject", reviewComment = "") {
    if (!items.length) return;
    await runAction(action === "approve" ? "批量通过" : "批量拒绝", async () => {
      await api.bulkReview({
        opportunity_ids: items.map((item) => item.id),
        reviewer_name: authSession?.user.name || "主管",
        action,
        review_comment: reviewComment || undefined
      });
      setReviewTarget(null);
    });
  }

  const meta = detailGroup
    ? { title: "商品详情", desc: "查看主 SKU 下所有子 SKU、竞品链接、价格参考、源表字段和认领复核信息。" }
    : viewMeta[activeView];

  if (!authChecked) {
    return (
      <div className="login-page">
        <div className="login-card">
          <b>东南亚新品流程平台</b>
          <span>{statusMessage || "正在检查登录状态..."}</span>
        </div>
      </div>
    );
  }

  if (!authSession) {
    return (
      <div className="login-page">
        <form className="login-card" onSubmit={(event) => {
          event.preventDefault();
          void loginLocal();
        }}>
          <span className="mark">
            <PackageOpen size={20} />
          </span>
          <div>
            <h1>东南亚新品流程平台</h1>
            <p>请使用已配置账号密码登录。初始密码为姓名拼音首字母加 123456。</p>
          </div>
          <label>
            账号姓名
            <input value={loginName} onChange={(event) => setLoginName(event.target.value)} placeholder="请输入姓名" autoFocus />
          </label>
          <label>
            密码
            <input
              value={loginPassword}
              onChange={(event) => setLoginPassword(event.target.value)}
              placeholder="请输入密码"
              type="password"
            />
          </label>
          <button className="btn primary" disabled={loading} type="submit">登录</button>
          {statusMessage && <span className="login-status">{statusMessage}</span>}
        </form>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="appbar">
        <div className="brand">
          <span className="mark">
            <PackageOpen size={18} />
          </span>
          <div>
            <b>东南亚新品流程平台</b>
            <span>反馈表导入、主管分配、运营认领、主管复核、Excel 导出</span>
          </div>
        </div>
        <div className="appbar-actions">
          <span className={healthStatus === "ok" ? "pill green" : "pill red"}>{healthStatus}</span>
          <button className="btn" disabled={loading} onClick={() => void refresh()}>
            <RefreshCw size={15} />刷新
          </button>
          <span className="auth-chip">
            {authSession.user.name}
            {authSession.roles.some((item) => item.role === "super_admin") ? " · 管理员" : ""}
          </span>
          <button className="btn" onClick={() => setPasswordPanelOpen((open) => !open)}>修改密码</button>
          {passwordPanelOpen && (
            <form className="password-popover" onSubmit={changeOwnPassword}>
              <label>
                原密码
                <input
                  type="password"
                  value={passwordForm.old_password}
                  onChange={(event) => setPasswordForm({ ...passwordForm, old_password: event.target.value })}
                />
              </label>
              <label>
                新密码
                <input
                  type="password"
                  value={passwordForm.new_password}
                  onChange={(event) => setPasswordForm({ ...passwordForm, new_password: event.target.value })}
                />
              </label>
              <label>
                确认新密码
                <input
                  type="password"
                  value={passwordForm.confirm_password}
                  onChange={(event) => setPasswordForm({ ...passwordForm, confirm_password: event.target.value })}
                />
              </label>
              <div className="action-row">
                <button className="btn primary" disabled={loading} type="submit">保存</button>
                <button className="btn" type="button" onClick={() => setPasswordPanelOpen(false)}>取消</button>
              </div>
            </form>
          )}
          <button className="btn" onClick={logout}>退出</button>
          {activeRole === "operator" && (!authSession || availableRoles.includes("manager")) && (
            <label className="operator-select">
              当前运营
              <select value={activeOperator} onChange={(event) => setActiveOperator(event.target.value)}>
                <option value="">请选择</option>
                {sortOperatorProfiles(operatorProfiles.filter((profile) => profile.enabled))
                  .map((profile) => (
                    <option key={profile.id} value={profile.operator_name}>
                      {profile.operator_name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          {activeRole === "operator" && authSession && !availableRoles.includes("manager") && (
            <span className="auth-chip">当前运营：{activeOperator || authSession.operator_name || authSession.user.name}</span>
          )}
          <div className="role-switch">
            {availableRoles.includes("operator") && (
              <button className={activeRole === "operator" ? "role-tab active" : "role-tab"} onClick={() => {
                setActiveRole("operator");
                setActiveView("dashboard");
              }}>
                <UserCheck size={15} />运营
              </button>
            )}
            {availableRoles.includes("manager") && (
              <button className={activeRole === "manager" ? "role-tab active" : "role-tab"} onClick={() => {
                setActiveRole("manager");
                setActiveView("dashboard");
              }}>
                <ShieldCheck size={15} />主管
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="wrap">
        <nav className="panel workflow-nav">
          <div className="workflow-nav-main">
            <div className="hub-actions">
              <button className={activeView === "dashboard" ? "flow-step active" : "flow-step"} onClick={() => setActiveView("dashboard")}>
                <LayoutDashboard size={16} />
                商品看板
              </button>
              <button className={activeView !== "dashboard" ? "flow-step active" : "flow-step"} onClick={() => setActiveView("pool")}>
                <Database size={16} />
                机会池流程
              </button>
            </div>
            <div className="workflow-flow">
              {visibleFlow.map((item, index) => (
                <span className="flow-node" key={item.view}>
                  {index > 0 && <span className="arrow">→</span>}
                  <button className={activeView === item.view ? "flow-step active" : "flow-step"} onClick={() => setActiveView(item.view)}>
                    {item.icon}
                    {item.label}
                  </button>
                </span>
              ))}
            </div>
          </div>
          <span className="hub-note">当前为测试阶段：真实钉钉自动推送保持关闭</span>
        </nav>

        <section className={["claim", "research", "listing"].includes(activeView) && !detailGroup ? "layout claim-full-layout" : "layout"}>
          <div className="panel screen">
            <div className="screen-top">
              <div>
                <h1>
                  {detailGroup && (
                    <button className="btn small" type="button" onClick={() => {
                      setDetailGroupKey(null);
                      setDetailChildId(null);
                    }}>
                      <ArrowLeft size={14} />
                      返回
                    </button>
                  )}
                  {viewIcon(activeView)}
                  {meta.title}
                </h1>
                <p>{meta.desc}</p>
              </div>
              <Toolbar
                activeView={activeView}
                assignSummary={assignSummary}
                hasAssignmentPreview={previewItems.length > 0}
                onPreview={previewAssignments}
                onCancelPreview={cancelAssignmentPreview}
                onAssign={submitAssignments}
                onOpenProfilePanel={() => setProfilePanelOpen(true)}
              />
            </div>
            {statusMessage && <div className={statusMessage.includes("失败") || statusMessage.includes("Error") ? "notice toast red" : "notice toast"}>{statusMessage}</div>}
            <div className="screen-body">
            {detailGroup ? (
              <ProductDetailView
                group={detailGroup}
                activeRole={activeRole}
                activeChildId={detailChildId}
                navLabel={
                  detailSequenceIndex >= 0
                    ? `子 SKU ${detailGroup.items.findIndex((item) => item.id === detailChildId) + 1}/${detailGroup.items.length} · 主 SKU ${groups.findIndex((group) => group.key === detailGroup.key) + 1}/${groups.length}`
                    : ""
                }
                canGoPrevious={detailSequenceIndex > 0}
                canGoNext={detailSequenceIndex >= 0 && detailSequenceIndex < detailSequence.length - 1}
                operatorName={activeOperator}
                canManage={canManage}
                onBack={() => {
                  setDetailGroupKey(null);
                  setDetailChildId(null);
                }}
                onSelectChild={setDetailChildId}
                onNavigate={navigateProductDetail}
                onUpdate={updateOpportunityDetails}
              />
            ) : (
            <>
            {activeView === "source" && (
              <SourceView
                loading={loading}
                source1File={source1File}
                source1Sheet={source1Sheet}
                source1BusinessPeriod={source1BusinessPeriod}
                source1Sheets={source1Sheets}
                source2File={source2File}
                source2Sheet={source2Sheet}
                source2Sheets={source2Sheets}
                lastImports={lastImports}
                importBatches={importBatches}
                isSuperAdmin={isSuperAdmin}
                setSource1File={setSource1File}
                setSource1Sheet={(value) => updateSourceSheet(1, value)}
                setSource1BusinessPeriod={updateBusinessPeriod}
                setSource1Sheets={setSource1Sheets}
                setSource2File={setSource2File}
                setSource2Sheet={(value) => updateSourceSheet(2, value)}
                setSource2Sheets={setSource2Sheets}
                onImport={importSelection}
                onToggleBatch={setImportBatchDisabled}
              />
            )}
            {activeView === "dashboard" && (
              <ProductBoardView
                role={activeRole}
                operatorName={activeOperator}
                onOpenDetail={(opportunityId) => {
                  const item = opportunities.find((entry) => entry.id === opportunityId);
                  if (item) openOpportunityDetail(item);
                }}
                onOpenResearch={() => setActiveView("research")}
              />
            )}
            {activeView === "pool" && (
              <PoolView
                activeRole={activeRole}
                groups={poolGroups}
                list={poolList}
                setList={setPoolList}
                expanded={expanded}
                toggle={(key) => setExpanded((current) => ({ ...current, [key]: !current[key] }))}
                onOpenDetail={(group) => openProductDetail(group)}
                goAssign={() => {
                  setActiveRole("manager");
                  setActiveView("assign");
                }}
                goClaim={addSelfClaimGroup}
                goImport={() => {
                  setActiveRole("manager");
                  setActiveView("source");
                }}
              />
            )}
            {activeView === "assign" && (
              <AssignView
                groups={groups}
                assignmentGroups={pendingAssignGroups}
                tasks={tasks}
                previewItems={assignmentItems}
                hasGeneratedRecommendations={previewItems.length > 0}
                assignmentDrafts={assignmentDrafts}
                setAssignmentDrafts={setAssignmentDrafts}
                profilePanelOpen={profilePanelOpen}
                setProfilePanelOpen={setProfilePanelOpen}
                operatorProfiles={operatorProfiles}
                setOperatorProfiles={setOperatorProfiles}
                list={assignList}
                setList={setAssignList}
                newProfile={newProfile}
                setNewProfile={setNewProfile}
                onSaveProfiles={saveProfiles}
                onAddProfile={addProfile}
                onDeleteProfile={removeProfile}
                onPreview={previewAssignments}
                onAssign={submitAssignments}
              />
            )}
            {activeView === "claim" && (
              <ClaimView
                rows={claimRows}
                activeOperator={activeOperator}
                drafts={claimDrafts}
                setDrafts={setClaimDrafts}
                list={claimList}
                setList={setClaimList}
                detailChildId={claimDetailChildId}
                setDetailChildId={setClaimDetailChildId}
                onOpenDetail={openClaimDetail}
                onRemoveSelfClaim={removeSelfClaimItem}
                onSubmit={submitClaimPayload}
              />
            )}
            {activeView === "review" && (
              <ReviewView
                rows={reviewRows}
                target={reviewTarget}
                setTarget={setReviewTarget}
                drafts={reviewDrafts}
                setDrafts={setReviewDrafts}
                list={reviewList}
                setList={setReviewList}
                onOpenDetail={openOpportunityDetail}
                onSubmit={submitReview}
                onBulkReview={bulkReview}
              />
            )}
            {activeView === "stock" && (
              <StockView
                rows={availableStocking}
                periods={exportPeriods}
                list={stockList}
                setList={setStockList}
                onStatus={setStatusMessage}
              />
            )}
            {activeView === "research" && (
              <SecondaryResearchView
                salespersonName={activeOperator}
                editable={activeRole === "operator"}
                onStatus={setStatusMessage}
              />
            )}
            {activeView === "listing" && (
              <ListingObservationView
                key={authSession.user.id}
                draftUserId={authSession.user.id}
                role={activeRole}
                operatorName={activeOperator}
                canManage={canManage}
                onStatus={setStatusMessage}
              />
            )}
            </>
            )}
            </div>
          </div>

          {activeView !== "claim" && activeView !== "research" && activeView !== "listing" && (
          <aside className="side">
            <section className="panel side-card">
              <h2>
                <LayoutDashboard size={16} />
                {activeRole === "operator" ? "运营视角" : "主管视角"}
              </h2>
              <p className="muted">
                {activeRole === "operator"
                  ? "处理分配给自己的子 SKU 认领或不认领；财根反馈表里的机会池可自认领。"
                  : "导入两张内部反馈表，按主 SKU 组分配，复核认领/不认领并导出 Excel。"}
              </p>
              <div className="metrics">
                {roleMetrics(activeRole, stats).map(([label, value]) => (
                  <div className="metric" key={label}>
                    <span>{label}</span>
                    <b>{value}</b>
                  </div>
                ))}
              </div>
            </section>
          </aside>
          )}
        </section>
      </main>
    </div>
  );
}

function DashboardView(props: {
  groups: ProductGroup[];
  allCount: number;
  filters: DashboardFilters;
  list: ListState;
  options: ReturnType<typeof buildDashboardOptions>;
  expanded: Record<string, boolean>;
  setFilter: (key: keyof DashboardFilters, value: string) => void;
  setList: Dispatch<SetStateAction<ListState>>;
  clearFilters: () => void;
  toggle: (key: string) => void;
  onOpenDetail: (group: ProductGroup) => void;
  onToggleGroupDisabled: (group: ProductGroup, disabled: boolean) => void;
  onToggleItemDisabled: (item: Opportunity, disabled: boolean) => void;
  isSuperAdmin: boolean;
  goImport: () => void;
}) {
  const pageGroups = pageItems(props.groups, props.list);
  return (
    <div className="dashboard">
      <div className="dashboard-filters">
        <FilterSelect label="状态" value={props.filters.status} options={props.options.statuses} onChange={(value) => props.setFilter("status", value)} />
        <FilterSelect label="健康标签" value={props.filters.health} options={["正常", "需关注", "异常"]} onChange={(value) => props.setFilter("health", value)} />
        <FilterSelect label="站点" value={props.filters.site} options={props.options.sites} onChange={(value) => props.setFilter("site", value)} />
        <FilterSelect label="开发人员" value={props.filters.owner} options={props.options.owners} onChange={(value) => props.setFilter("owner", value)} />
        <FilterSelect label="类目" value={props.filters.category} options={props.options.categories} onChange={(value) => props.setFilter("category", value)} />
        <FilterSelect label="来源批次" value={props.filters.source} options={props.options.sources} onChange={(value) => props.setFilter("source", value)} />
        <button className="btn" onClick={props.clearFilters}>
          清空
        </button>
      </div>
      <ListControls
        label="商品看板"
        list={{ ...props.list, query: props.filters.query }}
        total={props.groups.length}
        setList={(patch) => {
          props.setList((current) => ({ ...current, ...patch }));
          if (patch.query !== undefined) props.setFilter("query", patch.query);
        }}
      />
      <div className="dashboard-summary">
        <span className="tag">当前展示 {props.groups.length} / {props.allCount} 个主 SKU 组</span>
        <span className="tag">商品看板看全量状态；机会池只看待处理新品机会</span>
      </div>
      {!props.allCount ? (
        <section className="empty-state">
          <LayoutDashboard size={28} />
          <h3>商品看板暂无数据</h3>
          <p>导入两张内部反馈表后，这里展示所有商品走到哪一步。</p>
          <button className="btn primary" onClick={props.goImport}>
            去源表导入
          </button>
        </section>
      ) : !props.groups.length ? (
        <EmptySmall text="当前筛选条件下没有商品。" />
      ) : (
        <div className="group-list">
          {pageGroups.map((group) => (
            <ProductGroupCard
              group={group}
              expanded={Boolean(props.expanded[group.key])}
              key={group.key}
              onToggle={() => props.toggle(group.key)}
              onOpenDetail={() => props.onOpenDetail(group)}
              onToggleGroupDisabled={(disabled) => props.onToggleGroupDisabled(group, disabled)}
              onToggleItemDisabled={props.onToggleItemDisabled}
              showAdminActions={props.isSuperAdmin}
              showPrimary={false}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function FilterSelect({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (value: string) => void }) {
  return (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">全部</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function SourceView(props: {
  loading: boolean;
  source1File: File | null;
  source1Sheet: string;
  source1BusinessPeriod: string;
  source1Sheets: string[];
  source2File: File | null;
  source2Sheet: string;
  source2Sheets: string[];
  lastImports: ImportResults;
  importBatches: ImportBatchSummary[];
  isSuperAdmin: boolean;
  setSource1File: (value: File | null) => void;
  setSource1Sheet: (value: string) => void;
  setSource1BusinessPeriod: (value: string) => void;
  setSource1Sheets: (value: string[]) => void;
  setSource2File: (value: File | null) => void;
  setSource2Sheet: (value: string) => void;
  setSource2Sheets: (value: string[]) => void;
  onImport: (kind: 1 | 2) => void;
  onToggleBatch: (batch: ImportBatchSummary, disabled: boolean) => void;
}) {
  return (
    <div className="source-grid">
      <ImportCard
        title="选品1：海外仓开发部门开发新品认领-反馈"
        desc="按中央表截断到“开发是否接受核价结果”之前的字段对齐，后接内部认领字段。"
        sheet={props.source1Sheet}
        businessPeriod={props.source1BusinessPeriod}
        sheets={props.source1Sheets}
        file={props.source1File}
        result={props.lastImports[1]}
        setSheet={props.setSource1Sheet}
        setBusinessPeriod={props.setSource1BusinessPeriod}
        setSheets={props.setSource1Sheets}
        setFile={props.setSource1File}
        buttonText="导入选品1反馈表"
        disabled={props.loading}
        onImport={() => props.onImport(1)}
      />
      <ImportCard
        title="选品2：海外仓财根团队开发新品认领-反馈"
        desc="作为财根机会池来源；主运营必须处理，其他运营可自认领。"
        sheet={props.source2Sheet}
        sheets={props.source2Sheets}
        file={props.source2File}
        result={props.lastImports[2]}
        setSheet={props.setSource2Sheet}
        setSheets={props.setSource2Sheets}
        setFile={props.setSource2File}
        buttonText="导入选品2反馈表"
        disabled={props.loading}
        onImport={() => props.onImport(2)}
      />
      {props.isSuperAdmin && (
        <section className="info import-result import-history">
          <h3>
            <ShieldCheck size={16} />
            导入批次
          </h3>
          {!props.importBatches.length ? (
            <p className="muted">暂无导入批次。</p>
          ) : (
            <div className="batch-table">
              <div className="batch-row head">
                <span>时间</span>
                <span>来源</span>
                <span>期数</span>
                <span>新增/更新</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {props.importBatches.map((batch) => {
                const disabled = batch.status === "disabled";
                return (
                  <div className="batch-row" key={batch.id}>
                    <span>{formatDateTime(batch.imported_at)}</span>
                    <span>{batch.source_file || batch.source_type}</span>
                    <span>{batch.business_period || batch.source_sheet || "-"}</span>
                    <span>{batch.created_count} / {batch.updated_count}</span>
                    <span>{disabled ? "已停用" : batch.status}</span>
                    <button className="btn" type="button" onClick={() => props.onToggleBatch(batch, !disabled)}>
                      {disabled ? "恢复" : "停用"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function ImportCard(props: {
  title: string;
  desc: string;
  sheet: string;
  businessPeriod?: string;
  sheets: string[];
  file: File | null;
  result?: Selection1ImportResponse;
  buttonText: string;
  disabled: boolean;
  setSheet: (value: string) => void;
  setBusinessPeriod?: (value: string) => void;
  setSheets: (value: string[]) => void;
  setFile: (value: File | null) => void;
  onImport: () => void;
}) {
  const [sheetLoading, setSheetLoading] = useState(false);
  const [sheetError, setSheetError] = useState("");

  async function takeFileList(files: FileList | null) {
    const file = files?.[0] || null;
    props.setFile(file);
    props.setSheets([]);
    setSheetError("");
    if (!file) return;
    setSheetLoading(true);
    try {
      const result = await api.excelSheets(file);
      props.setSheets(result.sheets);
      if (result.default_sheet) props.setSheet(result.default_sheet);
      if (!result.sheets.length) setSheetError("没有读取到 Sheet，可手填数据 Sheet 后导入。");
    } catch (error) {
      setSheetError(`未能自动读取 Sheet：${readableError(error)}。可手填数据 Sheet 后导入。`);
    } finally {
      setSheetLoading(false);
    }
  }

  return (
    <section className="info import-card">
      <h3>
        <FileSpreadsheet size={16} />
        {props.title}
      </h3>
      <p>{props.desc}</p>
      <div className="form">
        <div className="period-row">
          <label>
            数据 Sheet
            {props.sheets.length ? (
              <select value={props.sheet} onChange={(event) => props.setSheet(event.target.value)}>
                {props.sheets.map((sheet) => (
                  <option key={sheet} value={sheet}>
                    {sheet}
                  </option>
                ))}
              </select>
            ) : (
              <input value={props.sheet} onChange={(event) => props.setSheet(event.target.value)} />
            )}
          </label>
          {props.setBusinessPeriod && (
            <label>
              业务期数
              <input value={props.businessPeriod || ""} onChange={(event) => props.setBusinessPeriod?.(event.target.value)} />
            </label>
          )}
        </div>
        {sheetLoading && <p className="muted sheet-hint">正在读取 Excel 的 Sheet...</p>}
        {!sheetLoading && props.sheets.length > 0 && <p className="muted sheet-hint">已读取 {props.sheets.length} 个 Sheet，请选择要读取的数据 Sheet。</p>}
        {!sheetLoading && sheetError && <p className="notice red sheet-hint">{sheetError}</p>}
        <label
          className="upload-zone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            void takeFileList(event.dataTransfer.files);
          }}
        >
          <Upload size={20} />
          <b className="upload-file-name">{props.file ? props.file.name : "拖拽 Excel 到这里，或点击选择文件"}</b>
          <span>{props.file ? `${formatFileSize(props.file.size)} · 可重新选择` : "支持 .xlsx / .xlsm / .xls"}</span>
          <input
            type="file"
            accept=".xlsx,.xlsm,.xls"
            onChange={(event) => {
              void takeFileList(event.target.files);
              event.currentTarget.value = "";
            }}
          />
        </label>
        <button className="btn primary" disabled={props.disabled || sheetLoading || !props.file} onClick={props.onImport}>
          <Upload size={15} />
          {props.buttonText}
        </button>
        {props.result && (
          <div className="import-card-result">
            <h4>
              <FileCheck2 size={15} />
              最近导入结果
            </h4>
            <div className="status-grid compact">
              <StatusCell label="数据 Sheet" value={props.result.source_sheet} />
              <StatusCell label="业务期数" value={props.result.business_period || props.result.source_sheet} />
              <StatusCell label="入池" value={props.result.imported_count} />
              <StatusCell label="新增 / 更新" value={`${props.result.created_count} / ${props.result.updated_count}`} />
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function readableError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error || "未知错误");
  try {
    const parsed = JSON.parse(message) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : message;
  } catch {
    return message;
  }
}

function PoolView(props: {
  activeRole: RoleKey;
  groups: ProductGroup[];
  list: ListState;
  setList: Dispatch<SetStateAction<ListState>>;
  expanded: Record<string, boolean>;
  toggle: (key: string) => void;
  onOpenDetail: (group: ProductGroup) => void;
  goAssign: () => void;
  goClaim: (group: ProductGroup) => void;
  goImport: () => void;
}) {
  const filteredGroups = filterGroupsBySearch(props.groups, props.list.query);
  const pageGroups = pageItems(filteredGroups, props.list);
  if (!props.groups.length) {
    return (
      <section className="empty-state">
        <Database size={28} />
        <h3>还没有财根机会池数据</h3>
        <p>选品1只进入分配台；这里展示选品2/财根可自领机会。</p>
        <button className="btn primary" onClick={props.goImport}>
          去源表导入
        </button>
      </section>
    );
  }
  return (
    <>
      <ListControls label="机会池" list={props.list} total={filteredGroups.length} setList={(patch) => props.setList((current) => ({ ...current, ...patch }))} />
      {!filteredGroups.length ? (
        <EmptySmall text="当前搜索条件下没有财根机会。" />
      ) : (
        <div className="group-list">
          {pageGroups.map((group) => (
            <ProductGroupCard
              group={group}
              expanded={Boolean(props.expanded[group.key])}
              key={group.key}
              onToggle={() => props.toggle(group.key)}
              onOpenDetail={() => props.onOpenDetail(group)}
              onPrimary={() => {
                if (props.activeRole === "manager") props.goAssign();
                else props.goClaim(group);
              }}
              primaryLabel={poolPrimaryLabel(group, props.activeRole)}
              showPrimary={Boolean(poolPrimaryLabel(group, props.activeRole))}
            />
          ))}
        </div>
      )}
    </>
  );
}

function ProductGroupCard(props: {
  group: ProductGroup;
  expanded: boolean;
  onToggle: () => void;
  onOpenDetail: () => void;
  onPrimary?: () => void;
  onToggleGroupDisabled?: (disabled: boolean) => void;
  onToggleItemDisabled?: (item: Opportunity, disabled: boolean) => void;
  primaryLabel?: string;
  showAdminActions?: boolean;
  showPrimary?: boolean;
}) {
  const { group } = props;
  const item = group.first;
  const imageItem = group.items.find((child) => child.image_url) || item;
  return (
    <article className={props.expanded ? "group-item active" : "group-item"}>
      <div className="sku-group">
        <ProductThumb item={imageItem} />
        <div>
          <div className="title-row">
            <button className="sku-title-link" type="button" onClick={props.onOpenDetail} title="查看商品详情">
              {group.main_sku}
            </button>
            {statusPill(group.status)}
            <span className="tag">开发：{ownerText(group)}</span>
          </div>
          <p>
            <b>{item.main_sku_name || item.sub_sku_name || "未命名商品"}</b>
            {item.keyword ? ` · ${item.keyword}` : ""}
          </p>
          <p className="muted">开品理由：{groupReason(group)}</p>
          <div className="tag-row">
            <span className="tag">{item.site || item.country || "未填站点"}</span>
            <span className="tag">{item.category_level1 || "未填类目"} 一级类目</span>
            <span className="tag">{group.items.length} 个子 SKU</span>
            <span className="tag">{item.source_sheet || item.source_type || "来源待追溯"}</span>
            <span className="tag">健康：{healthLabel(group)}</span>
          </div>
        </div>
        <div className="card-actions">
          <button className="btn blue" onClick={props.onToggle}>
            {props.expanded ? "收起子 SKU" : "展开子 SKU"}
          </button>
          {props.showPrimary !== false && (
            <button className="btn primary" onClick={props.onPrimary || props.onToggle}>
              {props.primaryLabel || primaryActionLabel(group)}
            </button>
          )}
          {props.showAdminActions && props.onToggleGroupDisabled && (
            <button className="btn" type="button" onClick={() => props.onToggleGroupDisabled?.(group.status !== "disabled")}>
              {group.status === "disabled" ? "恢复整组" : "停用整组"}
            </button>
          )}
        </div>
      </div>
      {props.expanded && (
        <div className="child-skus">
          {group.items.map((child) => (
            <div className="child-sku" key={child.id}>
              <ProductThumb item={child} small />
              <div>
                <b>{child.sub_sku}</b>
                <br />
                <span className="muted">{child.sub_sku_name || "-"} · 行 {child.source_row || "-"}</span>
              </div>
              <span className="tag">子 SKU</span>
              {statusPill(child.current_status)}
              {props.showAdminActions && props.onToggleItemDisabled && (
                <button className="btn" type="button" onClick={() => props.onToggleItemDisabled?.(child, child.current_status !== "disabled")}>
                  {child.current_status === "disabled" ? "恢复" : "停用"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

const competitorSpecs = [
  {
    label: "最低价",
    link: "Z",
    price: "AA",
    sales: "AB",
    linkAliases: ["最低价链接", "平台综合推荐(前三页）最低价竞品链接1"],
    priceAliases: ["售价1", "售价1(PHP）", "竞品单价 / （链接1） / (比索）"],
    salesAliases: ["月销1", "竞品子sku月销 / （链接1）"]
  },
  {
    label: "月销最高",
    link: "AC",
    price: "AD",
    sales: "AE",
    linkAliases: ["月销最高链接链接1", "月销最高链接", "most / orders链接", "most orders链接", "平台综合推荐（前三页）销量最多竞品链接2"],
    priceAliases: ["售价2", "售价2(PHP）", "竞品单价 / （链接2） / (比索）"],
    salesAliases: ["月销2", "竞品子sku月销 / （链接2）"]
  },
  {
    label: "月销次高",
    link: "AF",
    price: "AG",
    sales: "AH",
    linkAliases: ["月销次高链接链接2", "月销次高链接"],
    priceAliases: ["售价(PHP）"],
    salesAliases: ["月销"]
  },
  {
    label: "月销第三高",
    link: "AI",
    price: "AJ",
    sales: "AK",
    linkAliases: ["月销第三高链接链接3", "月销第三高链接"],
    priceAliases: ["售价(PHP）"],
    salesAliases: ["月销"]
  },
  {
    label: "新晋",
    link: "AL",
    price: "AM",
    sales: "AN",
    linkAliases: ["新晋链接", "平台综合推荐（前三页近3个月上架的）新晋竞品链接3"],
    priceAliases: ["售价3", "售价3(PHP）", "竞品单价（链接3）（比索）"],
    salesAliases: ["月销3", "竞品子sku月销（链接3）"]
  }
];

const pricingSpecs = [
  { column: "AO", label: "参考单销", aliases: ["参考单销"] },
  { column: "AP", label: "稳定期定价", aliases: ["稳定期定价", "稳定期定价 （PHP）", "稳定期定价 / （PHP）", "参考定价", "稳定期参考定价 / （VND）"] },
  { column: "AQ", label: "一次毛利额", aliases: ["一次毛利额 / （THB）", "一次毛利额 / （PHP）", "一次毛利额 / （VND）"] },
  { column: "AR", label: "一次毛利额(RMB)", aliases: ["一次毛利额 / （人民币）"] },
  { column: "AS", label: "稳定期利润率", aliases: ["稳定期利润率", "一次毛利率"] },
  { column: "AT", label: "预估单销", aliases: ["预估单销"] },
  { column: "AU", label: "推广期定价", aliases: ["推广期定价"] },
  { column: "AV", label: "推广期利润率", aliases: ["推广期利润率"] },
  { column: "AW", label: "稳定期总成本", aliases: ["稳定期总成本（PHP）（含头程+平台费+基础设施）", "稳定期总成本（THB）（含头程+平台费+基础设施）", "稳定期总成本（VND）（含头程+平台费+基础设施）"] },
  { column: "AX", label: "推广期总成本", aliases: ["推广期总成本（PHP）（含头程+平台费+基础设施）", "推广期总成本（THB）（含头程+平台费+基础设施）", "推广期总成本（VND）（含头程+平台费+基础设施）"] }
] as const;

const detailSections: { key: DetailSectionKey; label: string }[] = [
  { key: "core", label: "基础信息" },
  { key: "development", label: "开发询价" },
  { key: "market", label: "市场调研" },
  { key: "pricing", label: "价格参考" },
  { key: "cost", label: "成本参数" },
  { key: "claim", label: "认领与复核" },
  { key: "listing", label: "刊登与观察" },
  { key: "source", label: "源表字段" }
];

type DetailFieldSpec = {
  label: string;
  column: string;
  aliases?: string[];
  value?: (item: Opportunity) => string;
};

const coreFieldSpecs: DetailFieldSpec[] = [
  { label: "站点/国家", column: "A", aliases: ["站点", "国家"], value: (item) => item.site || item.country || "" },
  { label: "开发部门", column: "B", aliases: ["开发部门", "部门"], value: (item) => item.developer_department || "" },
  { label: "开发员", column: "C", aliases: ["开发员"], value: (item) => item.developer_name || "" },
  { label: "一级类目", column: "D", aliases: ["一级类目"], value: (item) => item.category_level1 || "" },
  { label: "关键词", column: "E", aliases: ["关键词"], value: (item) => item.keyword || "" },
  { label: "主 SKU 名称", column: "G", aliases: ["主SKU名称"], value: (item) => item.main_sku_name || "" },
  { label: "主 SKU", column: "H", aliases: ["主SKU"], value: (item) => item.main_sku || "" },
  { label: "子 SKU 名称", column: "I", aliases: ["子SKU名称"], value: (item) => item.sub_sku_name || "" },
  { label: "子 SKU", column: "J", aliases: ["子SKU"], value: (item) => item.sub_sku || "" },
  { label: "产品类型", column: "K", aliases: ["产品类型", "引流or绑定or利润"], value: (item) => item.product_type || "" },
  { label: "开品理由", column: "L", aliases: ["开品理由"], value: (item) => item.reason || "" }
];

const developmentFieldSpecs: DetailFieldSpec[] = [
  { label: "产品规格", column: "M", aliases: ["产品规格"] },
  { label: "产品外包装", column: "N", aliases: ["产品外包装"] },
  { label: "末道包材", column: "O", aliases: ["末道包材"] },
  { label: "供应商链接", column: "P", aliases: ["供应商链接"] },
  { label: "供应商名称", column: "Q", aliases: ["供应商名称"] },
  { label: "商品成本-含税（元）", column: "R", aliases: ["商品成本-含税（元）"] },
  { label: "加购运费", column: "S", aliases: ["预估单销*30的加购运费", "包装重量(kg)"] },
  { label: "加购运费分摊", column: "T", aliases: ["单子sku的加购运费分摊", "产品包装后体积长(cm)"] },
  { label: "包装重量", column: "U", aliases: ["包装重量(kg)", "产品包装后体积宽(cm)"] },
  { label: "长(cm)", column: "V", aliases: ["产品包装后体积长(cm)", "产品包装后体积高(cm)"] },
  { label: "宽(cm)", column: "W", aliases: ["产品包装后体积宽(cm)", "包装后体积"] },
  { label: "高(cm)", column: "X", aliases: ["产品包装后体积高(cm)"] },
  { label: "包装后体积", column: "Y", aliases: ["包装后体积"] }
];

const costParameterColumns = columnsBetween("AQ", "BR");

function hasOperatorSubmission(item: Opportunity) {
  return Boolean(item.latest_claim_result || item.latest_claim_salesperson || item.latest_claim_daily_sales != null || item.latest_reject_reason || item.latest_feedback_summary || item.latest_claim_note);
}

type SkuEditDraft = {
  main_sku: string;
  sub_sku: string;
  main_sku_name: string;
  sub_sku_name: string;
  site: string;
  country: string;
  category_level1: string;
  developer_department: string;
  developer_name: string;
  keyword: string;
  product_type: string;
  reason: string;
  image_url: string;
  current_status: string;
  sourceCells: Record<string, string>;
  edit_reason: string;
};

function skuEditDraft(item: Opportunity): SkuEditDraft {
  return {
    main_sku: item.main_sku || "",
    sub_sku: item.sub_sku || "",
    main_sku_name: item.main_sku_name || "",
    sub_sku_name: item.sub_sku_name || "",
    site: item.site || "",
    country: item.country || "",
    category_level1: item.category_level1 || "",
    developer_department: item.developer_department || "",
    developer_name: item.developer_name || "",
    keyword: item.keyword || "",
    product_type: item.product_type || "",
    reason: item.reason || "",
    image_url: item.image_url || "",
    current_status: item.current_status,
    sourceCells: Object.fromEntries(editableSourceCellRows(item).map((row) => [row.column, row.value])),
    edit_reason: ""
  };
}

const editableStatusOptions = [
  "pending_assignment",
  "open_claim_pool",
  "assigned",
  "claim_submitted",
  "claim_rejected",
  "returned_for_supplement",
  "ready_for_stocking",
  "已确认不认领"
];

function ProductDetailView(props: {
  group: ProductGroup;
  activeRole: RoleKey;
  activeChildId: string | null;
  navLabel: string;
  canGoPrevious: boolean;
  canGoNext: boolean;
  operatorName: string;
  canManage: boolean;
  onBack: () => void;
  onSelectChild: (id: string) => void;
  onNavigate: (delta: -1 | 1, currentChildId: string) => void;
  onUpdate: (id: string, payload: unknown) => Promise<void>;
}) {
  const { group } = props;
  const item = group.first;
  const activeChild = group.items.find((child) => child.id === props.activeChildId) || group.items[0] || item;
  const imageItem = activeChild.image_url ? activeChild : group.items.find((child) => child.image_url) || item;
  const [activeSection, setActiveSection] = useState<DetailSectionKey>("core");
  const [editingItem, setEditingItem] = useState<Opportunity | null>(null);
  const [editDraft, setEditDraft] = useState<SkuEditDraft>(() => skuEditDraft(item));

  useEffect(() => {
    if (!editingItem) setEditDraft(skuEditDraft(item));
  }, [editingItem, item.id]);

  function startEdit(child: Opportunity) {
    setEditingItem(child);
    setEditDraft(skuEditDraft(child));
  }

  function patchEditDraft(field: keyof SkuEditDraft, value: string) {
    setEditDraft((current) => ({ ...current, [field]: value }));
  }

  function patchSourceCell(column: string, value: string) {
    setEditDraft((current) => ({ ...current, sourceCells: { ...current.sourceCells, [column]: value } }));
  }

  async function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingItem) return;
    if (!editDraft.edit_reason.trim()) {
      window.alert("请填写修改原因");
      return;
    }
    const originalCells = Object.fromEntries(editableSourceCellRows(editingItem).map((row) => [row.column, row.value]));
    const source_cells = Object.fromEntries(Object.entries(editDraft.sourceCells).filter(([column, value]) => value !== (originalCells[column] || "")));
    const { sourceCells: _, ...fields } = editDraft;
    await props.onUpdate(editingItem.id, {
      ...fields,
      source_cells,
      edit_reason: editDraft.edit_reason.trim()
    });
    setEditingItem(null);
  }
  return (
    <div className="detail-page">
      <div className="detail-toolbar">
        <div className="detail-sequence-nav">
          <button
            className="btn"
            type="button"
            disabled={!props.canGoPrevious}
            onClick={() => props.onNavigate(-1, activeChild.id)}
          >
            <ChevronLeft size={16} />
            上一个
          </button>
          <span className="tag">{props.navLabel || `子 SKU 1/${group.items.length}`}</span>
          <button
            className="btn"
            type="button"
            disabled={!props.canGoNext}
            onClick={() => props.onNavigate(1, activeChild.id)}
          >
            下一个
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <section className="detail-hero">
        <ProductThumb item={imageItem} />
        <div>
          <div className="title-row">
            <h2>{group.main_sku}</h2>
            {statusPill(group.status)}
            <span className="tag">{ownerText(group)}</span>
          </div>
          <p>
            <b>{item.main_sku_name || item.sub_sku_name || "未命名商品"}</b>
            {item.keyword ? ` · ${item.keyword}` : ""}
          </p>
          <p className="muted">{groupReason(group)}</p>
          <div className="tag-row">
            <span className="tag">{item.site || item.country || "未填站点"}</span>
            <span className="tag">{item.category_level1 || "未填类目"}</span>
            <span className="tag">{group.items.length} 个子 SKU</span>
            <span className="tag">{item.source_file || "来源文件待追溯"}</span>
            <span className="tag">{sourceLabel(item)} · 行 {item.source_row || "-"}</span>
          </div>
        </div>
      </section>

      <section className="detail-section">
        <div className="detail-workspace">
          <aside className="detail-sidebar">
            <h3>商品全局档案</h3>
            <div className="detail-nav">
              {detailSections.map((section) => (
                <button
                  className={activeSection === section.key ? "detail-nav-button active" : "detail-nav-button"}
                  key={section.key}
                  type="button"
                  onClick={() => setActiveSection(section.key)}
                >
                  {section.label}
                </button>
              ))}
            </div>
          </aside>
          <div className="detail-content">
            <div className="detail-subsku-strip">
              {group.items.map((child) => (
                <button
                  className={activeChild.id === child.id ? "detail-subsku-chip active" : "detail-subsku-chip"}
                  key={child.id}
                  type="button"
                  onClick={() => props.onSelectChild(child.id)}
                >
                  <span>{child.sub_sku}</span>
                  <small>{child.sub_sku_name || child.main_sku_name || "未命名"}</small>
                </button>
              ))}
            </div>
            <div className="active-detail-head">
              <ProductThumb item={activeChild} small />
              <div>
                <div className="title-row">
                  <h3>{activeChild.sub_sku}</h3>
                  {statusPill(activeChild.current_status)}
                  {props.activeRole === "manager" && (
                    <button className="btn" type="button" onClick={() => startEdit(activeChild)}>
                      <ClipboardPen size={14} />
                      编辑
                    </button>
                  )}
                </div>
                <p>
                  <b>{activeChild.sub_sku_name || activeChild.main_sku_name || "未命名商品"}</b>
                </p>
                <div className="tag-row">
                  <span className="tag">{activeChild.site || activeChild.country || "未填站点"}</span>
                  <span className="tag">{activeChild.category_level1 || "未填类目"}</span>
                  <span className="tag">{sourceLabel(activeChild)} · 行 {activeChild.source_row || "-"}</span>
                </div>
              </div>
            </div>
            {activeSection === "core" && (
              <div className="detail-pane">
                <h3>基础信息（A-L）</h3>
                <DetailFieldGrid item={activeChild} specs={coreFieldSpecs} />
              </div>
            )}
            {activeSection === "development" && (
              <div className="detail-pane">
                <h3>开发询价（M-Y）</h3>
                <DetailFieldGrid item={activeChild} specs={developmentFieldSpecs} />
              </div>
            )}
            {activeSection === "market" && (
              <div className="detail-pane">
                <h3>市场调研（表头匹配，历史 Z-AN 兜底）</h3>
                <CompetitorTable item={activeChild} />
              </div>
            )}
            {activeSection === "pricing" && (
              <div className="detail-pane">
                <h3>价格 / 毛利参考（表头匹配，历史 AO-AV 兜底）</h3>
                <PricingGrid item={activeChild} />
                {!pricingRows(activeChild).length && <p className="muted detail-empty">暂无价格 / 毛利参考字段。</p>}
              </div>
            )}
            {activeSection === "cost" && (
              <div className="detail-pane">
                <h3>成本参数（AQ-BR）</h3>
                <ColumnRangeTable item={activeChild} columns={costParameterColumns} />
              </div>
            )}
            {activeSection === "claim" && (
              <div className="detail-pane">
                <h3>认领与复核</h3>
                {hasOperatorSubmission(activeChild) ? <OperatorSubmissionSummary item={activeChild} /> : <p className="muted detail-empty">暂无运营提交记录。</p>}
                <ClaimReviewTable item={activeChild} />
              </div>
            )}
            {activeSection === "listing" && (
              <div className="detail-pane">
                <h3>刊登与周期观察（只读）</h3>
                <ListingObservationSummary
                  mainSku={group.main_sku}
                  country={activeChild.country || item.country}
                  currentBusinessPeriod={activeChild.batch || item.batch || activeChild.source_sheet || item.source_sheet}
                  role={props.activeRole}
                  operatorName={props.operatorName}
                  canManage={props.canManage}
                />
              </div>
            )}
            {activeSection === "source" && (
              <div className="detail-pane">
                <h3>源表字段与追溯</h3>
                <div className="detail-trace">
                  <span>文件：{activeChild.source_file || "-"}</span>
                  <span>Sheet：{activeChild.source_sheet || "-"}</span>
                  <span>行号：{activeChild.source_row || "-"}</span>
                </div>
                <SourceFieldsTable item={activeChild} />
              </div>
            )}
          </div>
        </div>
        {props.activeRole === "manager" && editingItem && (
          <form className="sku-edit-form" onSubmit={submitEdit}>
            <div className="form-grid">
              <label>
                主 SKU
                <input value={editDraft.main_sku} onChange={(event) => patchEditDraft("main_sku", event.target.value)} />
              </label>
              <label>
                子 SKU
                <input value={editDraft.sub_sku} onChange={(event) => patchEditDraft("sub_sku", event.target.value)} />
              </label>
              <label>
                主 SKU 名称
                <input value={editDraft.main_sku_name} onChange={(event) => patchEditDraft("main_sku_name", event.target.value)} />
              </label>
              <label>
                子 SKU 名称
                <input value={editDraft.sub_sku_name} onChange={(event) => patchEditDraft("sub_sku_name", event.target.value)} />
              </label>
              <label>
                站点
                <input value={editDraft.site} onChange={(event) => patchEditDraft("site", event.target.value)} />
              </label>
              <label>
                国家
                <input value={editDraft.country} onChange={(event) => patchEditDraft("country", event.target.value)} />
              </label>
              <label>
                一级类目
                <input value={editDraft.category_level1} onChange={(event) => patchEditDraft("category_level1", event.target.value)} />
              </label>
              <label>
                开发部门
                <input value={editDraft.developer_department} onChange={(event) => patchEditDraft("developer_department", event.target.value)} />
              </label>
              <label>
                开发员
                <input value={editDraft.developer_name} onChange={(event) => patchEditDraft("developer_name", event.target.value)} />
              </label>
              <label>
                关键词
                <input value={editDraft.keyword} onChange={(event) => patchEditDraft("keyword", event.target.value)} />
              </label>
              <label>
                产品类型
                <input value={editDraft.product_type} onChange={(event) => patchEditDraft("product_type", event.target.value)} />
              </label>
              <label>
                图片地址
                <input value={editDraft.image_url} onChange={(event) => patchEditDraft("image_url", event.target.value)} />
              </label>
              <label>
                商品状态
                <select value={editDraft.current_status} onChange={(event) => patchEditDraft("current_status", event.target.value)}>
                  {editableStatusOptions.map((status) => <option key={status} value={status}>{statusMeta[status]?.label || status}</option>)}
                </select>
              </label>
            </div>
            <label>
              开品理由
              <textarea rows={2} value={editDraft.reason} onChange={(event) => patchEditDraft("reason", event.target.value)} />
            </label>
            <details className="source-parameter-editor">
              <summary>其他导入参数（{editableSourceCellRows(editingItem).length}）</summary>
              <div className="form-grid">
                {editableSourceCellRows(editingItem).map((row) => (
                  <label key={row.column}>
                    {row.column} · {row.label}
                    {row.value.length > 80 ? (
                      <textarea rows={2} value={editDraft.sourceCells[row.column] || ""} onChange={(event) => patchSourceCell(row.column, event.target.value)} />
                    ) : (
                      <input value={editDraft.sourceCells[row.column] || ""} onChange={(event) => patchSourceCell(row.column, event.target.value)} />
                    )}
                  </label>
                ))}
              </div>
            </details>
            <label>
              修改原因
              <textarea rows={2} value={editDraft.edit_reason} onChange={(event) => patchEditDraft("edit_reason", event.target.value)} />
            </label>
            <div className="action-row">
              <button className="btn primary" type="submit">
                <Save size={15} />
                保存
              </button>
              <button className="btn" type="button" onClick={() => setEditingItem(null)}>
                <X size={15} />
                取消
              </button>
            </div>
          </form>
        )}
      </section>
    </div>
  );
}

function ClaimReviewTable(props: { item: Opportunity }) {
  const child = props.item;
  return (
    <div className="table-wrap detail-table-wrap">
      <table className="detail-table">
        <thead>
          <tr>
            <th>运营</th>
            <th>认领结果</th>
            <th>认领单销</th>
            <th>不认领原因</th>
            <th>调研结论</th>
            <th>主管复核</th>
            <th>复核意见</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{child.latest_claim_salesperson || "-"}</td>
            <td>{claimResultLabel(child.latest_claim_result)}</td>
            <td>{child.latest_claim_result === "claim" ? formatBusinessNumber(child.latest_claim_daily_sales) || "-" : "-"}</td>
            <td>{child.latest_reject_reason || "-"}</td>
            <td>{child.latest_feedback_summary || "-"}</td>
            <td>{reviewStatusLabel(child.latest_review_status)}</td>
            <td>{child.latest_review_comment || "-"}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function DetailFieldGrid(props: { item: Opportunity; specs: DetailFieldSpec[] }) {
  const rows = detailFieldRows(props.item, props.specs);
  if (!rows.length) return <p className="muted detail-empty">暂无可展示字段。</p>;
  return (
    <div className="detail-field-grid">
      {rows.map((row) => (
        <div className="detail-field-cell" key={`${row.column}-${row.label}`}>
          <span>{row.column} · {row.label}</span>
          <b>{renderMaybeLink(formatBusinessValue(row.value, row.label))}</b>
        </div>
      ))}
    </div>
  );
}

function ColumnRangeTable(props: { item: Opportunity; columns: string[] }) {
  const rows = props.columns
    .map((column) => ({
      column,
      label: headerLabel(props.item, column),
      value: snapshotColumnText(props.item, column)
    }))
    .filter((row) => row.value);
  if (!rows.length) return <p className="muted detail-empty">暂无成本参数字段。</p>;
  return (
    <div className="table-wrap detail-table-wrap">
      <table className="detail-table">
        <thead>
          <tr>
            <th>列</th>
            <th>字段</th>
            <th>值</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.column}>
              <td>{row.column}</td>
              <td>{row.label}</td>
              <td>{renderMaybeLink(formatBusinessValue(row.value, row.label))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CompetitorTable(props: { item: Opportunity }) {
  const rows = competitorRows(props.item);
  if (!rows.length) return <p className="muted detail-empty">源表 Z:AN 暂无竞品链接、售价或月销。</p>;
  return (
    <div className="table-wrap detail-table-wrap">
      <table className="detail-table">
        <thead>
          <tr>
            <th>竞品位置</th>
            <th>链接列</th>
            <th>竞品链接</th>
            <th>价格列</th>
            <th>售价</th>
            <th>月销列</th>
            <th>月销</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const group = competitorGroupForLabel(row.label);
            return (
            <tr className={group ? `competitor-row competitor-${group.key}` : ""} key={row.label}>
              <td><span className={group ? `competitor-group-badge competitor-${group.key}` : "competitor-group-badge"}>{group?.label || row.label}</span></td>
              <td>{row.linkColumn}</td>
              <td>{renderLinkCell(row.link)}</td>
              <td>{row.priceColumn}</td>
              <td>{formatBusinessNumber(row.price) || "-"}</td>
              <td>{row.salesColumn}</td>
              <td>{formatBusinessNumber(row.sales) || "-"}</td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function PricingGrid(props: { item: Opportunity }) {
  const rows = pricingRows(props.item);
  if (!rows.length) return null;
  return (
    <div className="pricing-grid">
      {rows.map((row) => (
        <div className="pricing-cell" key={row.column}>
          <span>{row.column} · {row.label}</span>
          <b>{formatBusinessValue(row.value, row.label)}</b>
        </div>
      ))}
    </div>
  );
}

function SourceFieldsTable(props: { item: Opportunity }) {
  const rows = sourceFieldRows(props.item);
  if (!rows.length) return <p className="muted detail-empty">暂无可展示的源表字段。</p>;
  return (
    <div className="table-wrap detail-table-wrap">
      <table className="detail-table source-fields-table">
        <thead>
          <tr>
            <th>字段</th>
            <th>值</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <td>{row.key}</td>
              <td>{renderMaybeLink(row.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderLinkCell(value: string) {
  if (!value) return "-";
  if (!isHttpUrl(value)) return <span>{value}</span>;
  return (
    <a href={value} target="_blank" rel="noreferrer" className="link-inline" title={value}>
      <span>{compactUrlLabel(value)}</span>
      <ExternalLink size={14} />
    </a>
  );
}

function renderMaybeLink(value: string) {
  if (!isHttpUrl(value)) return value;
  return (
    <a href={value} target="_blank" rel="noreferrer" className="link-inline" title={value}>
      <span>{compactUrlLabel(value)}</span>
      <ExternalLink size={14} />
    </a>
  );
}

function competitorRows(item: Opportunity) {
  return competitorSpecs
    .map((spec) => ({
      label: spec.label,
      linkColumn: spec.link,
      priceColumn: spec.price,
      salesColumn: spec.sales,
      link: detailFieldValue(item, spec.linkAliases, spec.link),
      price: detailFieldValue(item, spec.priceAliases, spec.price),
      sales: detailFieldValue(item, spec.salesAliases, spec.sales)
    }))
    .filter((row) => row.link || row.price || row.sales);
}

function pricingRows(item: Opportunity) {
  const snapshot = snapshotOf(item);
  const pricing = isRecord(snapshot.pricing_snapshot) ? snapshot.pricing_snapshot : {};
  return pricingSpecs
    .map((spec) => ({ column: detailFieldColumn(item, spec.aliases, spec.column), label: spec.label, value: detailFieldValue(item, spec.aliases, spec.column) || valueText(pricing[spec.label]) }))
    .filter((row) => row.value);
}

function detailFieldColumn(item: Opportunity, aliases: readonly string[], fallbackColumn: string) {
  const aliasKeys = new Set(aliases.map(normalizeFieldKey));
  for (const [column, headers] of Object.entries(headersByColumn(item))) {
    if (Array.isArray(headers) && headers.some((header) => typeof header === "string" && aliasKeys.has(normalizeFieldKey(header)))) return column;
  }
  return fallbackColumn;
}

function detailFieldRows(item: Opportunity, specs: DetailFieldSpec[]) {
  return specs
    .map((spec) => ({
      column: spec.column,
      label: headerLabel(item, spec.column) || spec.label,
      value: spec.value?.(item) || detailFieldValue(item, spec.aliases || [spec.label], spec.column)
    }))
    .filter((row) => row.value);
}

function detailFieldValue(item: Opportunity, aliases: readonly string[], fallbackColumn: string) {
  const fields = snapshotFields(item);
  for (const alias of aliases) {
    const value = fields[normalizeFieldKey(alias)];
    const text = valueText(value);
    if (text) return text;
  }
  return snapshotColumnText(item, fallbackColumn);
}

function headerLabel(item: Opportunity, column: string) {
  const headers = headersByColumn(item)[column];
  return Array.isArray(headers) ? headers.filter(Boolean).join(" / ") : "";
}

function headersByColumn(item?: Opportunity | null): Record<string, unknown> {
  const headers = snapshotOf(item).headers_by_column;
  return isRecord(headers) ? headers : {};
}

function sourceFieldRows(item: Opportunity) {
  const fields = snapshotFields(item);
  return Object.entries(fields)
    .map(([key, value]) => ({ key, value: valueText(value) }))
    .filter((row) => row.value);
}

function snapshotOf(item?: Opportunity | null): Record<string, unknown> {
  return isRecord(item?.snapshot) ? item.snapshot : {};
}

function snapshotCells(item?: Opportunity | null): Record<string, unknown> {
  const cells = snapshotOf(item).cells;
  return isRecord(cells) ? cells : {};
}

function snapshotFields(item?: Opportunity | null): Record<string, unknown> {
  const fields = snapshotOf(item).fields_by_header;
  return isRecord(fields) ? fields : {};
}

function snapshotFieldsByColumn(item?: Opportunity | null): Record<string, unknown> {
  const fields = snapshotOf(item).fields_by_column;
  return isRecord(fields) ? fields : {};
}

function editableSourceCellRows(item: Opportunity) {
  const snapshot = snapshotOf(item);
  const allowed = Array.isArray(snapshot.allowed_columns) ? snapshot.allowed_columns.filter((column): column is string => typeof column === "string") : Object.keys(snapshotFieldsByColumn(item));
  return allowed
    .filter((column) => columnNumber(column) >= columnNumber("M") && columnNumber(column) <= columnNumber("BX"))
    .sort((left, right) => columnNumber(left) - columnNumber(right))
    .map((column) => ({
      column,
      label: headerLabel(item, column) || column,
      value: snapshotColumnText(item, column)
    }));
}

function snapshotColumnText(item: Opportunity, column: string) {
  return valueText(snapshotFieldsByColumn(item)[column]) || valueText(snapshotCells(item)[column]);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function valueText(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function isHttpUrl(value: string) {
  return /^https?:\/\//i.test(value.trim());
}

function normalizeFieldKey(value: string) {
  return value.replace(/\u00a0/g, " ").split(/\s+/).join("");
}

function columnsBetween(start: string, end: string) {
  const first = columnNumber(start);
  const last = columnNumber(end);
  return Array.from({ length: last - first + 1 }, (_, index) => columnName(first + index));
}

function columnNumber(column: string) {
  return column.split("").reduce((total, char) => total * 26 + char.charCodeAt(0) - 64, 0);
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

function claimResultLabel(value?: string | null) {
  if (value === "claim") return "认领";
  if (value === "reject") return "不认领";
  return value || "-";
}

function reviewStatusLabel(value?: string | null) {
  if (value === "approved") return "通过";
  if (value === "confirmed_reject") return "确认不认领";
  if (value === "returned_for_supplement") return "退回补充";
  return value || "-";
}

function ProductThumb(props: { item?: Opportunity | null; small?: boolean }) {
  const src = imageSrc(props.item?.image_url);
  const className = props.small ? "thumb small" : "thumb";
  const [open, setOpen] = useState(false);
  const alt = props.item?.sub_sku_name || props.item?.main_sku_name || props.item?.sub_sku || "商品图片";
  return (
    <>
      <div className={className}>
        {src ? (
          <button className="thumb-button" type="button" onClick={() => setOpen(true)} title="查看大图">
            <img src={src} alt={alt} />
          </button>
        ) : (
          "图"
        )}
      </div>
      {open && src && (
        <div className="image-preview" role="dialog" aria-modal="true" onClick={() => setOpen(false)}>
          <button className="image-preview-close" type="button" onClick={() => setOpen(false)}>
            <X size={18} />
          </button>
          <img src={src} alt={alt} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  );
}

function imageSrc(url?: string | null) {
  if (!url) return "";
  if (url.startsWith("/uploaded-sources/")) return `${API_BASE}${url}`;
  if (url.startsWith(`${OSS_PUBLIC_BASE}/`)) return `${API_BASE}/claims/evidence-images/proxy?url=${encodeURIComponent(url)}&token=${encodeURIComponent(getAuthToken())}`;
  return url;
}

function groupToAssignmentItem(group: ProductGroup): AssignmentPreviewItem {
  return {
    main_sku: group.main_sku,
    sub_sku_count: group.items.length,
    suggested_assignee: null,
    match_reason: "待生成推荐",
    opportunity_ids: group.items.map((item) => item.id)
  };
}

function AssignView(props: {
  groups: ProductGroup[];
  assignmentGroups: ProductGroup[];
  tasks: Task[];
  previewItems: AssignmentPreviewItem[];
  hasGeneratedRecommendations: boolean;
  assignmentDrafts: Record<string, string>;
  setAssignmentDrafts: (value: Record<string, string>) => void;
  profilePanelOpen: boolean;
  setProfilePanelOpen: Dispatch<SetStateAction<boolean>>;
  operatorProfiles: OperatorAssignmentProfile[];
  setOperatorProfiles: (value: OperatorAssignmentProfile[]) => void;
  list: ListState;
  setList: Dispatch<SetStateAction<ListState>>;
  newProfile: Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "assignment_priority" | "enabled">;
  setNewProfile: (value: Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "assignment_priority" | "enabled">) => void;
  onSaveProfiles: () => void;
  onAddProfile: () => void;
  onDeleteProfile: (profileId: string) => void;
  onPreview: () => void;
  onAssign: () => void;
}) {
  const [siteFilter, setSiteFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [operatorFilter, setOperatorFilter] = useState("");
  const [draggedProfileId, setDraggedProfileId] = useState<string | null>(null);
  const [dragOverProfileId, setDragOverProfileId] = useState<string | null>(null);
  useEffect(() => {
    if (!props.profilePanelOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") props.setProfilePanelOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [props.profilePanelOpen, props.setProfilePanelOpen]);
  const patchProfile = (id: string, patch: Partial<OperatorAssignmentProfile>) => {
    props.setOperatorProfiles(props.operatorProfiles.map((profile) => (profile.id === id ? { ...profile, ...patch } : profile)));
  };
  const sortedProfiles = sortOperatorProfiles(props.operatorProfiles);
  const enabledProfiles = sortedProfiles.filter((profile) => profile.enabled);
  const profileGroups = groupOperatorProfilesBySite(sortedProfiles);
  const workload = assignmentWorkload(enabledProfiles, props.groups, props.tasks, props.previewItems, props.assignmentDrafts);
  const pendingGroups = props.assignmentGroups;
  const filteredItems = filterAssignmentItems(props.previewItems, props.assignmentGroups, props.assignmentDrafts, {
    query: props.list.query,
    site: siteFilter,
    category: categoryFilter,
    operator: operatorFilter
  });
  const siteOptions = Array.from(new Set(props.assignmentGroups.flatMap((group) => group.items.map((item) => normalizeSiteText(item.site || item.country)).filter(Boolean)))).sort();
  const categoryOptions = Array.from(new Set(props.assignmentGroups.flatMap((group) => group.items.map((item) => item.category_level1?.trim()).filter((value): value is string => Boolean(value))))).sort();
  const pageItemsList = pageItems(filteredItems, props.list);
  const selectedCount = props.previewItems.filter((item) => props.assignmentDrafts[assignmentItemKey(item)]).length;
  const childSelectedCount = props.previewItems.reduce(
    (sum, item) => sum + (props.assignmentDrafts[assignmentItemKey(item)] ? item.sub_sku_count : 0),
    0
  );
  const patchDraft = (item: AssignmentPreviewItem, assignee: string) => {
    props.setAssignmentDrafts({ ...props.assignmentDrafts, [assignmentItemKey(item)]: assignee });
  };
  const moveProfile = (profileId: string, delta: -1 | 1) => {
    props.setOperatorProfiles(moveOperatorWithinSite(props.operatorProfiles, profileId, delta));
  };
  const dropProfile = (targetId: string) => {
    if (draggedProfileId) props.setOperatorProfiles(reorderOperatorWithinSite(props.operatorProfiles, draggedProfileId, targetId));
    setDraggedProfileId(null);
    setDragOverProfileId(null);
  };

  return (
    <div className="assign-layout">
      <section className="info assignment-table-panel">
        <div className="assignment-commandbar">
          <div className="assignment-command-title">
            <h3>待分配主 SKU</h3>
            <span className="tag">已选 {selectedCount} 组 / {childSelectedCount} 子 SKU</span>
            <span className="tag">未分配 {props.previewItems.length ? props.previewItems.length - selectedCount : pendingGroups.length} 组</span>
          </div>
          <select className="assignment-compact-select" aria-label="按站点筛选" value={siteFilter} onChange={(event) => {
            setSiteFilter(event.target.value);
            props.setList((current) => ({ ...current, page: 1 }));
          }}>
            <option value="">全部站点</option>
            {siteOptions.map((site) => <option key={site} value={site}>{site}</option>)}
          </select>
          <select className="assignment-compact-select category" aria-label="按一级类目筛选" value={categoryFilter} onChange={(event) => {
            setCategoryFilter(event.target.value);
            props.setList((current) => ({ ...current, page: 1 }));
          }}>
            <option value="">全部一级类目</option>
            {categoryOptions.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
          <select className="assignment-compact-select" aria-label="按运营筛选" value={operatorFilter} onChange={(event) => {
            setOperatorFilter(event.target.value);
            props.setList((current) => ({ ...current, page: 1 }));
          }}>
            <option value="">全部运营</option>
            {enabledProfiles.map((profile) => <option key={profile.id} value={profile.operator_name}>{profile.operator_name}</option>)}
          </select>
          <button className="btn small assignment-clear" type="button" onClick={() => {
            setSiteFilter("");
            setCategoryFilter("");
            setOperatorFilter("");
            props.setList((current) => ({ ...current, query: "", page: 1 }));
          }}>
            <X size={14} />清空
          </button>
          <ListControls
            label="分配台"
            list={props.list}
            total={filteredItems.length}
            searchPlaceholder="搜索主 SKU / 子 SKU / 商品名，多个关键词用空格分隔"
            setList={(patch) => props.setList((current) => ({ ...current, ...patch }))}
          />
        </div>
        <div className="assignment-workload-grid">
          {enabledProfiles.map((profile) => {
            const load = workload[profile.operator_name] || emptyAssignmentLoad();
            const maxGroups = Math.max(1, ...Object.values(workload).map((item) => item.groups));
            return (
              <div className="assignment-workload-card" key={profile.id}>
                <div className="assignment-operator-head">
                  <div className="assignment-operator-name">
                    {profile.assignment_priority > 0 && (
                      <span className={`priority-badge priority-${Math.min(profile.assignment_priority, 3)}`}>优先 {profile.assignment_priority}</span>
                    )}
                    <b>{profile.operator_name}</b>
                  </div>
                  <span className="tag">{profile.key_site || "-"}</span>
                </div>
                <div className="operator-category-tags">
                  {profile.key_category1 && <span title={`重点品类1：${profile.key_category1}`}>品类1 · {profile.key_category1}</span>}
                  {profile.key_category2 && <span title={`重点品类2：${profile.key_category2}`}>品类2 · {profile.key_category2}</span>}
                  {!profile.key_category1 && !profile.key_category2 && <span className="muted">未配置重点品类</span>}
                </div>
                <div className="assignment-load-bar">
                  <span style={{ width: `${Math.max(8, (load.groups / maxGroups) * 100)}%` }} />
                </div>
                <p>
                  <b>{load.groups}</b> 组 / <b>{load.subSkus}</b> 子 SKU
                  {(load.draftGroups > 0 || load.draftSubSkus > 0) && (
                    <span className="muted">，本次 +{load.draftGroups} 组 / +{load.draftSubSkus} 子 SKU</span>
                  )}
                </p>
              </div>
            );
          })}
        </div>
        {!props.previewItems.length ? (
          <p className="muted">没有待分配的主 SKU 组。</p>
        ) : !filteredItems.length ? (
          <EmptySmall text="当前搜索条件下没有待分配 SKU。" />
        ) : (
          <div className="assignment-table-scroll">
            <div className="assignment-table">
              <div className="assignment-row head">
                <span>图片</span>
                <span>商品重点信息</span>
                <span>系统推荐</span>
                <span>推荐依据</span>
                <span>最终分配 / 状态</span>
              </div>
            {pageItemsList.map((item) => (
              <AssignmentTableRow
                enabledProfiles={enabledProfiles}
                group={props.assignmentGroups.find((group) => group.items.some((opportunity) => item.opportunity_ids.includes(opportunity.id)))}
                item={item}
                key={assignmentItemKey(item)}
                onChange={patchDraft}
                selectedAssignee={props.assignmentDrafts[assignmentItemKey(item)] || ""}
                showRecommendation={props.hasGeneratedRecommendations}
                suggestedProfile={props.operatorProfiles.find((profile) => profile.operator_name === item.suggested_assignee)}
                workload={workload}
              />
            ))}
            </div>
          </div>
        )}
      </section>
      {props.profilePanelOpen && (
        <div className="assignment-config-overlay" role="dialog" aria-modal="true" aria-label="运营配置">
          <button className="assignment-config-backdrop" type="button" aria-label="关闭运营配置" onClick={() => props.setProfilePanelOpen(false)} />
          <section className="assignment-config-drawer">
            <div className="assignment-config-header">
              <div>
                <h3>
                  <Users size={17} />
                  运营配置
                </h3>
                <p className="muted">维护站点、重点品类、同负载优先级和站点内顺序；保存后下一次生成推荐生效。</p>
              </div>
              <div className="action-row">
                <button className="btn primary" onClick={props.onSaveProfiles}>
                  <Save size={15} />
                  保存运营配置
                </button>
                <button className="btn" type="button" title="关闭" onClick={() => props.setProfilePanelOpen(false)}>
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="assignment-config-body">
              <div className="profile-table">
                <div className="profile-row head">
                  <span>启用</span>
                  <span>运营</span>
                  <span>重点站点</span>
                  <span>重点品类1</span>
                  <span>重点品类2</span>
                  <span>优先级</span>
                  <span>排序</span>
                  <span>删除</span>
                </div>
                {profileGroups.flatMap((profileGroup) => profileGroup.items.map((profile, profileIndex) => (
                  <div
                    className={`profile-row${draggedProfileId === profile.id ? " dragging" : ""}${dragOverProfileId === profile.id ? " drag-over" : ""}`}
                    data-site={profileGroup.site}
                    key={profile.id}
                    onDragOver={(event) => {
                      const source = props.operatorProfiles.find((item) => item.id === draggedProfileId);
                      if (!source || normalizeSiteText(source.key_site) !== normalizeSiteText(profile.key_site)) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                      setDragOverProfileId(profile.id);
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      dropProfile(profile.id);
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={profile.enabled}
                      onChange={(event) => patchProfile(profile.id, { enabled: event.target.checked })}
                      aria-label={`${profile.operator_name} 是否启用`}
                    />
                    <input value={profile.operator_name} onChange={(event) => patchProfile(profile.id, { operator_name: event.target.value })} />
                    <input value={profile.key_site || ""} onChange={(event) => patchProfile(profile.id, { key_site: event.target.value })} />
                    <input value={profile.key_category1 || ""} onChange={(event) => patchProfile(profile.id, { key_category1: event.target.value })} />
                    <input value={profile.key_category2 || ""} onChange={(event) => patchProfile(profile.id, { key_category2: event.target.value })} />
                    <input
                      type="number"
                      value={profile.assignment_priority || 0}
                      onChange={(event) => patchProfile(profile.id, { assignment_priority: Number(event.target.value || 0) })}
                    />
                    <div className="action-row compact-actions profile-sort-actions">
                      <button
                        aria-label={`拖拽调整 ${profile.operator_name} 的同站点顺序`}
                        className="btn profile-drag-handle"
                        draggable
                        onDragEnd={() => {
                          setDraggedProfileId(null);
                          setDragOverProfileId(null);
                        }}
                        onDragStart={(event) => {
                          event.dataTransfer.effectAllowed = "move";
                          event.dataTransfer.setData("text/plain", profile.id);
                          setDraggedProfileId(profile.id);
                        }}
                        title="拖拽调整同站点顺序"
                        type="button"
                      >
                        <GripVertical size={14} />
                      </button>
                      <button className="btn" disabled={profileIndex === 0} onClick={() => moveProfile(profile.id, -1)} title="在同站点上移" type="button">
                        <ArrowUp size={14} />
                      </button>
                      <button className="btn" disabled={profileIndex === profileGroup.items.length - 1} onClick={() => moveProfile(profile.id, 1)} title="在同站点下移" type="button">
                        <ArrowDown size={14} />
                      </button>
                    </div>
                    <div className="action-row compact-actions">
                      <button className="btn" onClick={() => props.onDeleteProfile(profile.id)} title="删除">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                )))}
                <div className="profile-row new">
                  <input
                    type="checkbox"
                    checked={props.newProfile.enabled}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, enabled: event.target.checked })}
                    aria-label="新运营是否启用"
                  />
                  <input
                    value={props.newProfile.operator_name}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, operator_name: event.target.value })}
                    placeholder="运营"
                  />
                  <input
                    value={props.newProfile.key_site || ""}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, key_site: event.target.value })}
                    placeholder="站点缩写，如 PH / TH / SG"
                  />
                  <input
                    value={props.newProfile.key_category1 || ""}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, key_category1: event.target.value })}
                    placeholder="重点品类1"
                  />
                  <input
                    value={props.newProfile.key_category2 || ""}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, key_category2: event.target.value })}
                    placeholder="重点品类2"
                  />
                  <input
                    type="number"
                    value={props.newProfile.assignment_priority || 0}
                    onChange={(event) => props.setNewProfile({ ...props.newProfile, assignment_priority: Number(event.target.value || 0) })}
                    placeholder="优先级"
                  />
                  <span />
                  <button className="btn primary" onClick={props.onAddProfile}>
                    <Plus size={15} />
                    新增
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function assignmentItemKey(item: AssignmentPreviewItem) {
  return item.opportunity_ids.length ? [...item.opportunity_ids].sort().join("|") : item.main_sku;
}

function emptyAssignmentLoad(): AssignmentLoad {
  return { groups: 0, subSkus: 0, draftGroups: 0, draftSubSkus: 0 };
}

function assignmentWorkload(
  profiles: OperatorAssignmentProfile[],
  groups: ProductGroup[],
  tasks: Task[],
  previewItems: AssignmentPreviewItem[],
  drafts: Record<string, string>
) {
  const byName = Object.fromEntries(profiles.map((profile) => [profile.operator_name, emptyAssignmentLoad()]));
  const groupByOpportunityId = new Map<string, ProductGroup>();
  for (const group of groups) {
    for (const item of group.items) {
      groupByOpportunityId.set(item.id, group);
    }
  }
  const assignedGroupKeys: Record<string, Set<string>> = Object.fromEntries(profiles.map((profile) => [profile.operator_name, new Set<string>()]));
  for (const task of tasks) {
    if (task.task_type !== "sales_claim" || task.status !== "pending" || !task.assignee_name || !task.opportunity_id) continue;
    const load = byName[task.assignee_name];
    const group = groupByOpportunityId.get(task.opportunity_id);
    if (!load || !group) continue;
    assignedGroupKeys[task.assignee_name].add(group.key);
    load.subSkus += 1;
  }
  for (const profile of profiles) {
    byName[profile.operator_name].groups = assignedGroupKeys[profile.operator_name].size;
  }
  for (const item of previewItems) {
    const assignee = drafts[assignmentItemKey(item)];
    const load = assignee ? byName[assignee] : undefined;
    if (!load) continue;
    load.groups += 1;
    load.subSkus += item.sub_sku_count;
    load.draftGroups += 1;
    load.draftSubSkus += item.sub_sku_count;
  }
  return byName;
}

function operatorProfileBrief(profile: OperatorAssignmentProfile) {
  return `${profile.key_site || "-"} · 品类1 ${profile.key_category1 || "-"} · 品类2 ${profile.key_category2 || "-"} · 优先级 ${profile.assignment_priority || 0}`;
}

function operatorOptionLabel(profile: OperatorAssignmentProfile, load: AssignmentLoad) {
  return `${profile.operator_name}｜${profile.key_site || "-"}｜${profile.key_category1 || "-"} / ${profile.key_category2 || "-"}｜优先级${profile.assignment_priority || 0}｜${load.groups}组/${load.subSkus}子SKU`;
}

function AssignmentTableRow(props: {
  enabledProfiles: OperatorAssignmentProfile[];
  group?: ProductGroup;
  item: AssignmentPreviewItem;
  selectedAssignee: string;
  showRecommendation: boolean;
  suggestedProfile?: OperatorAssignmentProfile;
  workload: Record<string, AssignmentLoad>;
  onChange: (item: AssignmentPreviewItem, assignee: string) => void;
}) {
  const first = props.group?.first;
  const productName = first?.main_sku_name || first?.sub_sku_name || first?.keyword || "未填产品名";
  const site = first?.site || first?.country || "-";
  const category = first?.category_level1 || "-";
  const selectedProfile = props.enabledProfiles.find((profile) => profile.operator_name === props.selectedAssignee);
  const profileGroups = groupOperatorProfilesBySite(props.enabledProfiles);
  return (
    <div className="assignment-row">
      <div className="assignment-cell thumb-cell">
        <ProductThumb item={first} />
      </div>
      <div className="assignment-cell">
        <div className="title-row compact">
          <h2>{props.item.main_sku}</h2>
          <span className="tag">子 SKU {props.item.sub_sku_count}</span>
        </div>
        <div className="tag-row">
          <span className="tag">{site}</span>
          <span className="tag">{category}</span>
        </div>
        <p>
          <b>{productName}</b>
        </p>
        <p className="muted">{first?.reason || first?.keyword || "暂无开品理由"}</p>
      </div>
      <div className="assignment-cell">
        {!props.showRecommendation ? (
          <span className="tag">待生成推荐</span>
        ) : props.item.suggested_assignee ? (
          <>
            <b>{props.item.suggested_assignee}</b>
            <p className="muted">{props.suggestedProfile ? operatorProfileBrief(props.suggestedProfile) : "未找到人员配置"}</p>
          </>
        ) : (
          <span className="tag">未推荐运营</span>
        )}
      </div>
      <div className="assignment-cell assignment-reason">
        {(props.showRecommendation
          ? assignmentMatchLines(props.item, first, props.suggestedProfile)
          : ["点击生成推荐后填入系统推荐；也可以直接在最终分配列手动选择运营"]
        ).map((line) => (
          <p className={assignmentReasonClass(line)} key={line}>{line}</p>
        ))}
      </div>
      <div className="assignment-cell assignment-final-cell">
        <select className="assignment-select" value={props.selectedAssignee} onChange={(event) => props.onChange(props.item, event.target.value)}>
          <option value="">未分配</option>
          {profileGroups.map((profileGroup) => (
            <optgroup key={profileGroup.site} label={profileGroup.site}>
              {profileGroup.items.map((profile) => (
                <option key={profile.id} value={profile.operator_name}>
                  {operatorOptionLabel(profile, props.workload[profile.operator_name] || emptyAssignmentLoad())}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {selectedProfile && <p className="muted full-profile">{operatorProfileBrief(selectedProfile)}</p>}
        <span className={props.selectedAssignee ? "pill green" : "pill amber"}>{props.selectedAssignee ? "可提交" : "待决定"}</span>
      </div>
    </div>
  );
}

function AssignmentPreviewCard(props: {
  group?: ProductGroup;
  item: AssignmentPreviewItem;
  profile?: OperatorAssignmentProfile;
}) {
  const first = props.group?.first;
  const productName = first?.main_sku_name || first?.sub_sku_name || first?.keyword || "未填产品名";
  const site = first?.site || first?.country || "-";
  const category = first?.category_level1 || "-";
  return (
    <article className="assignment-preview-card">
      <ProductThumb item={first} />
      <div>
        <div className="title-row">
          <h2>{props.item.main_sku}</h2>
          <span className="tag">子 SKU {props.item.sub_sku_count}</span>
          <span className="tag">{site}</span>
          <span className="tag">{category}</span>
        </div>
        <p>
          <b>{productName}</b>
        </p>
        <p className="muted">{first?.reason || first?.keyword || "暂无开品理由"}</p>
      </div>
      <div className="assignment-match">
        <h4>{props.item.suggested_assignee || "未推荐运营"}</h4>
        <p>{props.item.match_reason || "无匹配原因"}</p>
        <ul>
          {assignmentMatchLines(props.item, first, props.profile).map((line) => (
            <li className={assignmentReasonClass(line)} key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function assignmentMatchLines(item: AssignmentPreviewItem, opportunity?: Opportunity, profile?: OperatorAssignmentProfile) {
  const site = opportunity?.site || opportunity?.country || "-";
  const category = opportunity?.category_level1 || "-";
  const skuSite = siteDisplay(site);
  const profileSite = siteDisplay(profile?.key_site || "-");
  if (!profile) return [`无站点匹配：没有启用运营的重点站点等于 SKU 站点 ${skuSite}`, `SKU品类：${category}`];
  const lines = [`站点匹配：SKU站点 ${skuSite} = ${profile.operator_name}重点站点 ${profileSite}`];
  if (sameCategoryText(category, profile.key_category1)) {
    lines.push(`品类1匹配：SKU品类 ${category} = ${profile.operator_name}品类1 ${profile.key_category1}`);
  } else if (sameCategoryText(category, profile.key_category2)) {
    lines.push(`品类2匹配：SKU品类 ${category} = ${profile.operator_name}品类2 ${profile.key_category2}`);
  } else {
    lines.push(`品类未匹配：SKU品类 ${category} 不在 ${profile.operator_name}品类1/品类2`);
  }
  if (item.match_reason?.includes("负载均衡")) {
    lines.push("负载均衡：先选择当前主 SKU 组数更少的运营，负载相同时再看品类");
  } else if (item.match_reason?.includes("负载更低")) {
    lines.push("负载更低：同站点候选中优先选择当前主 SKU 组数更少的运营");
  }
  if ((profile.assignment_priority || 0) > 0) {
    lines.push(`优先级：同负载时优先级 ${profile.assignment_priority}`);
  }
  return lines;
}

function assignmentReasonClass(line: string) {
  if (line.startsWith("站点匹配")) return "assignment-reason-line site";
  if (line.startsWith("品类1匹配") || line.startsWith("品类2匹配")) return "assignment-reason-line category";
  if (line.startsWith("无站点匹配") || line.startsWith("品类未匹配")) return "assignment-reason-line miss";
  if (line.startsWith("负载")) return "assignment-reason-line balance";
  return "assignment-reason-line";
}

function siteDisplay(value?: string | null) {
  const raw = value?.trim();
  const normalized = normalizeSiteText(raw);
  if (!raw) return "-";
  return normalized && normalized !== raw.toUpperCase() ? `${raw}(${normalized})` : raw;
}

function sameText(left?: string | null, right?: string | null) {
  return Boolean(left?.trim() && right?.trim() && left.trim() === right.trim());
}

function sameCategoryText(left?: string | null, right?: string | null) {
  const leftText = normalizeCategoryText(left);
  const rightText = normalizeCategoryText(right);
  return Boolean(leftText && rightText && leftText === rightText);
}

function normalizeCategoryText(value?: string | null) {
  const text = value?.trim().replace(/\s+/g, "");
  if (!text) return "";
  if (text.includes("汽") && text.includes("摩")) return "汽摩配";
  if (text.includes("家居") || text.includes("厨卫")) return "家居厨卫";
  if (text.includes("商") && (text.includes("办") || text.includes("工业"))) return "商办工业";
  if (text.includes("户外") || text.includes("运动")) return "户外运动";
  return text;
}

function ClaimView(props: {
  rows: Opportunity[];
  activeOperator: string;
  drafts: Record<string, ClaimDraft>;
  setDrafts: Dispatch<SetStateAction<Record<string, ClaimDraft>>>;
  list: ListState;
  setList: Dispatch<SetStateAction<ListState>>;
  detailChildId: string | null;
  setDetailChildId: (value: string | null) => void;
  onOpenDetail: (group: ProductGroup, childId?: string | null) => void;
  onRemoveSelfClaim: (id: string) => void;
  onSubmit: (payload: unknown | unknown[]) => Promise<boolean>;
}) {
  const periods = useMemo(() => businessPeriodsByNewest(props.rows), [props.rows]);
  const newestPeriod = useMemo(() => latestBusinessPeriod(props.rows), [props.rows]);
  const [businessPeriod, setBusinessPeriod] = useState("");
  const [claimStatus, setClaimStatus] = useState("");
  const workflowRows = useMemo(
    () => filterOperatorClaimRows(props.rows, { businessPeriod, status: claimStatus as "" | "pending" | "claimed_pending_review" | "rejected_pending_review" | "returned" }),
    [businessPeriod, claimStatus, props.rows]
  );
  const filteredRows = useMemo(() => filterOpportunitiesBySearch(workflowRows, props.list.query), [workflowRows, props.list.query]);
  const claimGroups = useMemo(() => groupOpportunities(filteredRows), [filteredRows]);
  const allClaimGroups = useMemo(() => groupOpportunities(props.rows), [props.rows]);
  const pageGroups = pageItems(claimGroups, props.list);
  const drawerItem = props.detailChildId ? props.rows.find((item) => item.id === props.detailChildId) || null : null;
  const drawerGroup = drawerItem ? allClaimGroups.find((group) => group.items.some((item) => item.id === drawerItem.id)) || groupOpportunities([drawerItem])[0] : null;
  const drawerGroupSequence = drawerGroup && claimGroups.some((group) => group.key === drawerGroup.key) ? claimGroups : allClaimGroups;
  const drawerGroupIndex = drawerGroup ? drawerGroupSequence.findIndex((group) => group.key === drawerGroup.key) : -1;
  const previousDrawerGroup = drawerGroupIndex > 0 ? drawerGroupSequence[drawerGroupIndex - 1] : null;
  const nextDrawerGroup = drawerGroupIndex >= 0 && drawerGroupIndex < drawerGroupSequence.length - 1 ? drawerGroupSequence[drawerGroupIndex + 1] : null;
  const [syncRejectToGroup, setSyncRejectToGroup] = useState(true);

  useEffect(() => {
    setBusinessPeriod((current) => (current && periods.includes(current) ? current : newestPeriod));
  }, [newestPeriod, periods]);

  useEffect(() => {
    if (props.detailChildId && !props.rows.some((item) => item.id === props.detailChildId)) props.setDetailChildId(null);
  }, [props.detailChildId, props.rows, props.setDetailChildId]);

  function draftFor(item: Opportunity): ClaimDraft {
    return props.drafts[item.id] || draftForOpportunity(item);
  }

  function patchDraft(itemId: string, patch: Partial<ClaimDraft>, group?: ProductGroup | null, syncReject = false) {
    const item = props.rows.find((row) => row.id === itemId);
    props.setDrafts((current) => {
      const seeded = current[itemId] || !item ? current : { ...current, [itemId]: draftForOpportunity(item) };
      return patchClaimDraftGroup(
        seeded,
        itemId,
        patch,
        group?.items.map((item) => item.id),
        syncReject,
        group?.items[0]?.id === itemId
      );
    });
  }

  function setMode(itemId: string, mode: "claim" | "reject", group?: ProductGroup | null, syncReject = false) {
    patchDraft(itemId, { mode }, group, syncReject);
  }

  function buildPayload(item: Opportunity, draft: ClaimDraft, requireComplete: boolean) {
    const dailySales = draft.claimDailySales.trim();
    const rejectReason = draft.rejectReason.trim();
    const researchConclusion = draft.researchConclusion.trim();
    if (draft.mode === "claim" && !dailySales) {
      if (requireComplete) window.alert("认领时必须填写认领单销");
      return null;
    }
    if (draft.mode === "reject" && !rejectReason) {
      if (requireComplete) window.alert("不认领时必须填写不认领原因");
      return null;
    }
    const note =
      draft.evidenceImages.length
        ? JSON.stringify({
            evidence_images: draft.evidenceImages.map((image) => ({
              name: image.name,
              type: image.type,
              size: image.size,
              url: image.url || image.previewUrl,
              previewUrl: image.url ? undefined : image.previewUrl
            }))
          })
        : item.latest_claim_note || "";
    return {
      opportunity_id: item.id,
      salesperson_name: props.activeOperator,
      claim_result: draft.mode,
      claim_source: claimSourceFor(item),
      claim_daily_sales: draft.mode === "claim" ? Number(dailySales) : undefined,
      reject_reason: draft.mode === "reject" ? rejectReason : undefined,
      feedback_summary: researchConclusion || undefined,
      note
    };
  }

  async function submitItem(item: Opportunity) {
    const draft = draftFor(item);
    if (!props.activeOperator) {
      window.alert("请先在右上角选择当前运营");
      return;
    }
    const payload = buildPayload(item, draft, true);
    if (!payload) return;
    const submitted = await props.onSubmit(payload);
    if (!submitted) return;
    props.setDrafts((current) => {
      const next = { ...current };
      delete next[item.id];
      return next;
    });
    if (isSelfClaimPoolItem(item)) props.onRemoveSelfClaim(item.id);
  }

  async function submitComplete(items: Opportunity[]) {
    if (!props.activeOperator) {
      window.alert("请先在右上角选择当前运营");
      return;
    }
    const readyItems: { item: Opportunity; payload: unknown }[] = [];
    for (const item of items) {
      if (claimSubmissionState(item, props.drafts[item.id]) === "submitted") continue;
      const payload = buildPayload(item, draftFor(item), false);
      if (payload) readyItems.push({ item, payload });
    }
    if (!readyItems.length) {
      window.alert("没有已填写未提交的子 SKU");
      return;
    }
    const submitted = await props.onSubmit(readyItems.map((entry) => entry.payload));
    if (!submitted) return;
    props.setDrafts((current) => {
      const next = { ...current };
      for (const entry of readyItems) delete next[entry.item.id];
      return next;
    });
    for (const entry of readyItems) {
      if (isSelfClaimPoolItem(entry.item)) props.onRemoveSelfClaim(entry.item.id);
    }
  }

  function addEvidence(itemId: string, images: EvidenceImage[]) {
    if (!images.length) return;
    const item = props.rows.find((row) => row.id === itemId);
    props.setDrafts((current) => {
      const seeded = current[itemId] || !item ? current : { ...current, [itemId]: draftForOpportunity(item) };
      const draft = seeded[itemId] || draftForId();
      return patchClaimDraftGroup(seeded, itemId, { evidenceImages: [...draft.evidenceImages, ...images] });
    });
  }

  function removeEvidence(itemId: string, imageId: string) {
    const item = props.rows.find((row) => row.id === itemId);
    props.setDrafts((current) => {
      const seeded = current[itemId] || !item ? current : { ...current, [itemId]: draftForOpportunity(item) };
      const draft = seeded[itemId] || draftForId();
      return patchClaimDraftGroup(seeded, itemId, { evidenceImages: draft.evidenceImages.filter((image) => image.id !== imageId) });
    });
  }

  return (
    <div className="claim-workspace">
      <section className="claim-list-pane">
        <div className="claim-workflow-filters">
          <select aria-label="业务期数" value={businessPeriod} onChange={(event) => {
            setBusinessPeriod(event.target.value);
            props.setList((current) => ({ ...current, page: 1 }));
          }}>
            <option value="">全部期数</option>
            {periods.map((period) => <option key={period} value={period}>{period}</option>)}
          </select>
          <select aria-label="操作状态" value={claimStatus} onChange={(event) => {
            setClaimStatus(event.target.value);
            props.setList((current) => ({ ...current, page: 1 }));
          }}>
            <option value="">全部操作状态</option>
            {operatorClaimStatusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
        <ListControls label="运营认领" list={props.list} total={filteredRows.length} setList={(patch) => props.setList((current) => ({ ...current, ...patch }))} />
        {!props.rows.length && <EmptySmall text="没有待认领任务或财根机会池记录。" />}
        {!!props.rows.length && !filteredRows.length && <EmptySmall text="当前搜索条件下没有待认领任务。" />}
        {!!filteredRows.length && (
          <div className="claim-bulkbar">
            <span>每个子 SKU 一行；可在列表填，也可打开右侧详情边看边填。</span>
            <button className="btn primary" onClick={() => void submitComplete(filteredRows)}>
              <Send size={15} />
              一键提交全部未提交
            </button>
          </div>
        )}
        {pageGroups.map((group) => (
          <article className="group-item claim-main-card" key={group.key}>
            <div className="claim-group-head">
              <div>
                <div className="title-row">
                  <button className="sku-title-link" type="button" onClick={() => props.onOpenDetail(group)}>
                    {group.main_sku}
                  </button>
                  {statusPill(group.status)}
                  <span className="tag">{group.items.length} 个子 SKU</span>
                </div>
                <p className="muted">{group.first.main_sku_name || group.first.keyword || "暂无商品名"}</p>
                <p className="muted">开品理由：{groupReason(group)}</p>
              </div>
              <button className="btn" onClick={() => void submitComplete(group.items)}>
                提交本组未提交
              </button>
            </div>
            <div className="claim-child-list compact">
              {group.items.map((item) => {
                const draft = draftFor(item);
                return (
                  <section className={props.detailChildId === item.id ? "claim-row-card active" : "claim-row-card"} key={item.id}>
                    <ProductThumb item={item} small />
                    <div className="claim-row-info">
                      <div className="title-row compact">
                        <button className="sku-title-link small-title" type="button" onClick={() => props.onOpenDetail(group, item.id)}>
                          {item.sub_sku}
                        </button>
                        {statusPill(item.current_status)}
                      </div>
                      <p>
                        <b>{item.sub_sku_name || item.keyword || "-"}</b>
                      </p>
                      <div className="claim-row-meta">
                        {item.latest_claim_result && <span>上次：{item.latest_claim_result === "claim" ? "认领" : "不认领"}</span>}
                        {item.current_status === "returned_for_supplement" && item.latest_review_comment && <span className="red">退回：{item.latest_review_comment}</span>}
                      </div>
                    </div>
                    <ClaimDraftEditor
                      compact
                      draft={draft}
                      item={item}
                      onAddEvidence={(images) => addEvidence(item.id, images)}
                      onMode={(mode) => setMode(item.id, mode)}
                      onPatch={(patch) => patchDraft(item.id, patch)}
                      onRemoveEvidence={(imageId) => removeEvidence(item.id, imageId)}
                      onRemoveSelfClaim={() => props.onRemoveSelfClaim(item.id)}
                      onSubmit={() => void submitItem(item)}
                      showRemove={isSelfClaimPoolItem(item)}
                      submitDisabled={claimSubmissionState(item, props.drafts[item.id]) === "submitted"}
                      submitText={claimSubmitButtonText(item, props.drafts[item.id])}
                    />
                    <button className="btn small" type="button" onClick={() => props.onOpenDetail(group, item.id)}>
                      详情
                    </button>
                  </section>
                );
              })}
            </div>
          </article>
        ))}
      </section>
      {drawerItem && drawerGroup && (
        <ClaimDetailDrawer
          drafts={props.drafts}
          group={drawerGroup}
          groupIndex={drawerGroupIndex >= 0 ? drawerGroupIndex + 1 : 1}
          groupTotal={drawerGroupSequence.length || 1}
          nextGroup={nextDrawerGroup}
          onAddEvidence={(item, images) => addEvidence(item.id, images)}
          onClose={() => props.setDetailChildId(null)}
          onMode={(item, mode) => setMode(item.id, mode, drawerGroup, syncRejectToGroup)}
          onNextGroup={() => nextDrawerGroup && props.setDetailChildId(nextDrawerGroup.items[0]?.id || null)}
          onPatch={(item, patch) => patchDraft(item.id, patch, drawerGroup, syncRejectToGroup)}
          onPreviousGroup={() => previousDrawerGroup && props.setDetailChildId(previousDrawerGroup.items[0]?.id || null)}
          onRemoveEvidence={(item, imageId) => removeEvidence(item.id, imageId)}
          onRemoveSelfClaim={(item) => props.onRemoveSelfClaim(item.id)}
          onSubmitGroup={() => void submitComplete(drawerGroup.items)}
          previousGroup={previousDrawerGroup}
          syncRejectToGroup={syncRejectToGroup}
          onSyncRejectToGroupChange={setSyncRejectToGroup}
        />
      )}
    </div>
  );
}

function claimSubmitButtonText(item: Opportunity, draft?: ClaimDraft) {
  const state = claimSubmissionState(item, draft);
  if (state === "submitted") return "已提交";
  return item.latest_claim_result ? "提交修改" : "提交";
}

function ClaimSubmissionBadge(props: { item: Opportunity; draft?: ClaimDraft }) {
  const state = claimSubmissionState(props.item, props.draft);
  const label = state === "submitted" ? "已提交" : state === "dirty" ? "已填写未提交" : "待填写";
  return (
    <span className={`claim-save-state ${state}`}>
      {label}
      {state === "submitted" && <small>待主管复核</small>}
    </span>
  );
}

function ClaimDraftEditor(props: {
  item: Opportunity;
  draft: ClaimDraft;
  compact?: boolean;
  showRemove?: boolean;
  submitDisabled?: boolean;
  submitText: string;
  onMode: (mode: "claim" | "reject") => void;
  onPatch: (patch: Partial<ClaimDraft>) => void;
  onAddEvidence: (images: EvidenceImage[]) => void;
  onRemoveEvidence: (imageId: string) => void;
  onSubmit: () => void;
  onRemoveSelfClaim?: () => void;
}) {
  const { draft } = props;
  const primaryLabel = draft.mode === "claim" ? "认领单销" : "不认领原因";
  return (
    <div className={props.compact ? "claim-editor compact" : "claim-editor drawer"}>
      <div className="mode-tabs">
        <button className={draft.mode === "claim" ? "mode-tab active" : "mode-tab"} type="button" onClick={() => props.onMode("claim")}>
          <CheckCircle2 size={15} />
          认领
        </button>
        <button className={draft.mode === "reject" ? "mode-tab active reject" : "mode-tab"} type="button" onClick={() => props.onMode("reject")}>
          <XCircle size={15} />
          不认领
        </button>
      </div>
      <div className="claim-editor-field primary-field">
        <span>{primaryLabel}</span>
        {draft.mode === "claim" ? (
          <input
            aria-label="认领单销"
            min="0"
            onChange={(event) => props.onPatch({ claimDailySales: event.target.value })}
            placeholder="单销"
            step="0.01"
            type="number"
            value={draft.claimDailySales}
          />
        ) : (
          <RejectReasonPicker
            onChange={(rejectReason) => props.onPatch({ rejectReason })}
            value={draft.rejectReason}
          />
        )}
      </div>
      <label className="claim-editor-field conclusion-field">
        <span>调研结论</span>
        {props.compact ? (
          <input
            onChange={(event) => props.onPatch({ researchConclusion: event.target.value })}
            onPaste={(event) => pasteClaimEvidence(event, props.item.id, props.onAddEvidence)}
            placeholder="结论"
            value={draft.researchConclusion}
          />
        ) : (
          <textarea
            onChange={(event) => props.onPatch({ researchConclusion: event.target.value })}
            onPaste={(event) => pasteClaimEvidence(event, props.item.id, props.onAddEvidence)}
            placeholder="可选，导出到市场监控 AK"
            rows={3}
            value={draft.researchConclusion}
          />
        )}
      </label>
      <EvidencePicker
        compact={props.compact}
        images={draft.evidenceImages}
        onFiles={(files) => readEvidenceFiles(files, props.item.id).then(props.onAddEvidence)}
        onRemove={props.onRemoveEvidence}
      />
      <div className="claim-editor-actions">
        <ClaimSubmissionBadge draft={props.draft} item={props.item} />
        {props.showRemove && props.onRemoveSelfClaim && (
          <button className="btn small" type="button" onClick={props.onRemoveSelfClaim}>
            <Trash2 size={14} />
            移除
          </button>
        )}
        <button className="btn primary" disabled={props.submitDisabled} type="button" onClick={props.onSubmit}>
          <Send size={15} />
          {props.submitText}
        </button>
      </div>
    </div>
  );
}

function ClaimDetailDrawer(props: {
  group: ProductGroup;
  drafts: Record<string, ClaimDraft>;
  groupIndex: number;
  groupTotal: number;
  previousGroup: ProductGroup | null;
  nextGroup: ProductGroup | null;
  syncRejectToGroup: boolean;
  onClose: () => void;
  onPreviousGroup: () => void;
  onNextGroup: () => void;
  onSyncRejectToGroupChange: (checked: boolean) => void;
  onMode: (item: Opportunity, mode: "claim" | "reject") => void;
  onPatch: (item: Opportunity, patch: Partial<ClaimDraft>) => void;
  onAddEvidence: (item: Opportunity, images: EvidenceImage[]) => void;
  onRemoveEvidence: (item: Opportunity, imageId: string) => void;
  onSubmitGroup: () => void;
  onRemoveSelfClaim: (item: Opportunity) => void;
}) {
  const first = props.group.first;
  const moduleTabs: { key: ClaimDrawerModuleKey; label: string; columns: string[] }[] = [
    { key: "market", label: "市场调研", columns: columnsBetween("Z", "AN") },
    { key: "pricing", label: "价格 / 毛利", columns: columnsBetween("AO", "AV") },
    { key: "development", label: "开发询价 / 包装", columns: columnsBetween("M", "Y") },
    {
      key: "cost",
      label: "成本 / 备货汇总",
      columns: columnsBetween("AW", "BX").filter((column) => !isSourceClaimInputLabel(headerLabel(first, column) || selection1ColumnLabel(column)))
    }
  ];
  const [activeModule, setActiveModule] = useState<ClaimDrawerModuleKey>("market");
  const activeTab = moduleTabs.find((tab) => tab.key === activeModule) || moduleTabs[0];
  const basicColumns = columnsBetween("A", "L").filter((column) => !["I", "J"].includes(column));
  const dirtyCount = props.group.items.filter((item) => claimSubmissionState(item, props.drafts[item.id]) === "dirty").length;
  const summaryMeta = [first.site || first.country, first.developer_department, first.developer_name, first.category_level1, first.product_type]
    .filter(Boolean)
    .join(" · ");

  useEffect(() => {
    setActiveModule("market");
  }, [props.group.key]);

  return (
    <div className="claim-detail-overlay" role="dialog" aria-modal="true">
      <button className="claim-detail-backdrop" type="button" onClick={props.onClose}>
        <span>关闭详情</span>
      </button>
      <aside className="claim-detail-drawer">
        <header className="claim-drawer-head">
          <div className="drawer-title-row">
            <div>
              <h2>{props.group.main_sku}</h2>
              <p>{first.main_sku_name || first.keyword || "未命名商品"} · {props.group.items.length} 个子 SKU</p>
            </div>
            <div className="drawer-header-actions">
              <span className="tag">第 {props.groupIndex} / {props.groupTotal} 组</span>
              <button className="btn small" type="button" onClick={props.onClose}>
                <X size={14} />
                关闭
              </button>
            </div>
          </div>
        </header>
        <div className="claim-drawer-body">
          <details className="claim-basic-details">
            <summary>
              <ProductThumb item={first} small />
              <span className="claim-basic-summary">
                <b>{summaryMeta || "基础信息"}</b>
                <span>{first.keyword || first.main_sku_name || "-"} · {groupReason(props.group)}</span>
              </span>
              <span className="tag">基础信息 A-L</span>
            </summary>
            <div className="claim-basic-grid">
              {basicColumns.map((column) => (
                <span key={column}>
                  <b>{column} · {headerLabel(first, column) || column}</b>
                  {renderMaybeLink(snapshotColumnText(first, column) || "-")}
                </span>
              ))}
            </div>
          </details>

          {props.group.items.some((item) => item.current_status === "returned_for_supplement" && item.latest_review_comment) && (
            <div className="return-reason">本组存在主管退回项，请在右侧认领栏查看退回原因。</div>
          )}

          <div className="claim-matrix-toolbar">
            <div className="claim-module-tabs">
              {moduleTabs.map((tab) => (
                <button className={activeModule === tab.key ? "claim-module-tab active" : "claim-module-tab"} key={tab.key} type="button" onClick={() => setActiveModule(tab.key)}>
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="claim-matrix-actions">
              <label className="sync-check">
                <input checked={props.syncRejectToGroup} onChange={(event) => props.onSyncRejectToGroupChange(event.target.checked)} type="checkbox" />
                不认领自动填充其他未填写子 SKU
              </label>
              <span className="tag">{activeTab.columns[0]}-{activeTab.columns[activeTab.columns.length - 1]}</span>
              <button className="btn primary" type="button" onClick={props.onSubmitGroup}>
                <Send size={15} />
                提交本主 SKU 未提交项{dirtyCount ? `（${dirtyCount}）` : ""}
              </button>
            </div>
          </div>

          <ClaimMatrixTable
            columns={activeTab.columns}
            drafts={props.drafts}
            group={props.group}
            onAddEvidence={props.onAddEvidence}
            onMode={props.onMode}
            onPatch={props.onPatch}
            onRemoveEvidence={props.onRemoveEvidence}
            onRemoveSelfClaim={props.onRemoveSelfClaim}
          />
        </div>
        <button
          aria-label="上一个主 SKU"
          className="claim-group-nav previous"
          disabled={!props.previousGroup}
          type="button"
          onClick={props.onPreviousGroup}
        >
          <ChevronLeft size={20} />
          <span>上一组</span>
        </button>
        <button
          aria-label="下一个主 SKU"
          className="claim-group-nav next"
          disabled={!props.nextGroup}
          type="button"
          onClick={props.onNextGroup}
        >
          <ChevronRight size={20} />
          <span>下一组</span>
        </button>
      </aside>
    </div>
  );
}

function ClaimMatrixTable(props: {
  group: ProductGroup;
  columns: string[];
  drafts: Record<string, ClaimDraft>;
  onMode: (item: Opportunity, mode: "claim" | "reject") => void;
  onPatch: (item: Opportunity, patch: Partial<ClaimDraft>) => void;
  onAddEvidence: (item: Opportunity, images: EvidenceImage[]) => void;
  onRemoveEvidence: (item: Opportunity, imageId: string) => void;
  onRemoveSelfClaim: (item: Opportunity) => void;
}) {
  return (
    <div className="claim-matrix-wrap">
      <table className="claim-matrix-table">
        <thead>
          <tr>
            <th className="claim-matrix-sticky-left">子 SKU（I-J）</th>
            {props.columns.map((column) => (
              <th className={claimMatrixColumnClass(props.group.first, column)} key={column}>
                {column} · {headerLabel(props.group.first, column) || column}
              </th>
            ))}
            <th className="claim-matrix-sticky-right">认领填写与调研图片</th>
          </tr>
        </thead>
        <tbody>
          {props.group.items.map((item) => (
            <tr key={item.id}>
              <td className="claim-matrix-sticky-left">
                <div className="claim-matrix-sku">
                  <ProductThumb item={item} small />
                  <span>
                    <b>{item.sub_sku}</b>
                    <span>{item.sub_sku_name || item.keyword || "-"}</span>
                    {statusPill(item.current_status)}
                  </span>
                </div>
              </td>
              {props.columns.map((column) => (
                <td className={claimMatrixColumnClass(item, column)} key={column}>
                  {renderMaybeLink(formatBusinessValue(snapshotColumnText(item, column), headerLabel(item, column) || selection1ColumnLabel(column)) || "-")}
                </td>
              ))}
              <td className="claim-matrix-sticky-right">
                <ClaimMatrixDraftEditor
                  draft={props.drafts[item.id] || draftForOpportunity(item)}
                  item={item}
                  onAddEvidence={(images) => props.onAddEvidence(item, images)}
                  onMode={(mode) => props.onMode(item, mode)}
                  onPatch={(patch) => props.onPatch(item, patch)}
                  onRemoveEvidence={(imageId) => props.onRemoveEvidence(item, imageId)}
                  onRemoveSelfClaim={() => props.onRemoveSelfClaim(item)}
                  showRemove={isSelfClaimPoolItem(item)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function claimMatrixColumnClass(item: Opportunity, column: string) {
  const classes = [];
  if (isHttpUrl(snapshotColumnText(item, column))) classes.push("wide");
  const group = competitorGroupForColumn(column);
  if (group) classes.push("competitor-group", `competitor-${group.key}`);
  return classes.join(" ");
}

function ClaimMatrixDraftEditor(props: {
  item: Opportunity;
  draft: ClaimDraft;
  showRemove: boolean;
  onMode: (mode: "claim" | "reject") => void;
  onPatch: (patch: Partial<ClaimDraft>) => void;
  onAddEvidence: (images: EvidenceImage[]) => void;
  onRemoveEvidence: (imageId: string) => void;
  onRemoveSelfClaim: () => void;
}) {
  return (
    <div className="claim-matrix-editor">
      <div className="mode-tabs">
        <button className={props.draft.mode === "claim" ? "mode-tab active" : "mode-tab"} type="button" onClick={() => props.onMode("claim")}>
          <CheckCircle2 size={14} />认领
        </button>
        <button className={props.draft.mode === "reject" ? "mode-tab active reject" : "mode-tab"} type="button" onClick={() => props.onMode("reject")}>
          <XCircle size={14} />不认领
        </button>
      </div>
      <div className="claim-editor-field">
        <span>{props.draft.mode === "claim" ? "认领单销" : "不认领原因"}</span>
        {props.draft.mode === "claim" ? (
          <input
            aria-label="认领单销"
            min="0"
            onChange={(event) => props.onPatch({ claimDailySales: event.target.value })}
            placeholder="单销"
            step="0.01"
            type="number"
            value={props.draft.claimDailySales}
          />
        ) : (
          <RejectReasonPicker
            onChange={(rejectReason) => props.onPatch({ rejectReason })}
            value={props.draft.rejectReason}
          />
        )}
      </div>
      <label className="claim-editor-field conclusion-field">
        <span>调研结论</span>
        <input
          onChange={(event) => props.onPatch({ researchConclusion: event.target.value })}
          onPaste={(event) => pasteClaimEvidence(event, props.item.id, props.onAddEvidence)}
          placeholder="结论"
          value={props.draft.researchConclusion}
        />
      </label>
      <EvidencePicker
        compact
        images={props.draft.evidenceImages}
        onFiles={(files) => readEvidenceFiles(files, props.item.id).then(props.onAddEvidence)}
        onRemove={props.onRemoveEvidence}
      />
      <ClaimSubmissionBadge draft={props.draft} item={props.item} />
      {props.showRemove && (
        <button className="btn small" type="button" onClick={props.onRemoveSelfClaim}>
          <Trash2 size={14} />移除
        </button>
      )}
      {props.item.current_status === "returned_for_supplement" && props.item.latest_review_comment && (
        <span className="claim-matrix-return">退回：{props.item.latest_review_comment}</span>
      )}
    </div>
  );
}

function draftForId(): ClaimDraft {
  return createClaimDraft<EvidenceImage>();
}

function draftForOpportunity(item: Opportunity): ClaimDraft {
  const draft = createClaimDraftFromLatest<EvidenceImage>(item);
  return {
    ...draft,
    evidenceImages: parseClaimEvidenceImages(item.latest_claim_note).map((image, index) => ({
      id: `saved-${item.id}-${index}`,
      name: image.name,
      type: image.type,
      size: image.size,
      previewUrl: imageSrc(image.url || image.previewUrl || ""),
      url: image.url || image.previewUrl
    }))
  };
}

function reviewDraftFor(item?: Opportunity | null): ReviewDraft {
  return {
    reviewerName: "练玉君",
    reviewStatus: item?.current_status === "claim_rejected" ? "confirmed_not_claim" : "approved",
    reviewComment: ""
  };
}

function RejectReasonPicker(props: { value: string; onChange: (value: string) => void }) {
  const parsed = parseRejectReason(props.value);
  const summary = props.value || "请选择或填写原因";

  return (
    <details className="reject-reason-picker">
      <summary aria-label="不认领原因" title={props.value}>{parsed.selected.length ? `已选 ${parsed.selected.length} 项 · ${summary}` : summary}</summary>
      <div className="reject-reason-menu">
        <div className="reject-reason-options">
          {REJECT_REASON_OPTIONS.map((option) => (
            <label className="reject-reason-option" key={option}>
              <input
                checked={parsed.selected.includes(option)}
                onChange={(event) => props.onChange(formatRejectReason(
                  event.target.checked
                    ? [...parsed.selected, option]
                    : parsed.selected.filter((item) => item !== option),
                  parsed.custom
                ))}
                type="checkbox"
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
        <label className="reject-reason-custom">
          <span>其他原因</span>
          <input
            onChange={(event) => props.onChange(formatRejectReason(parsed.selected, event.target.value))}
            placeholder="其他原因"
            value={parsed.custom}
          />
        </label>
      </div>
    </details>
  );
}

function pasteClaimEvidence(
  event: ClipboardEvent<HTMLInputElement | HTMLTextAreaElement>,
  opportunityId: string,
  onAdd: (images: EvidenceImage[]) => void
) {
  const files = imageFiles(event.clipboardData.files);
  if (files.length) void readEvidenceFiles(files, opportunityId).then(onAdd).catch(showUploadError);
}

function showUploadError(error: unknown) {
  window.alert(error instanceof Error && error.message ? error.message : "图片上传失败");
}

function EvidencePicker(props: {
  images: EvidenceImage[];
  onFiles: (files: FileList | File[]) => Promise<void>;
  onRemove: (imageId: string) => void;
  compact?: boolean;
}) {
  const [preview, setPreview] = useState<EvidenceImage | null>(null);
  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    const files = imageFiles(event.currentTarget.files);
    event.currentTarget.value = "";
    if (files.length) void props.onFiles(files).catch(showUploadError);
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    const files = imageFiles(event.dataTransfer.files);
    if (files.length) void props.onFiles(files).catch(showUploadError);
  }
  function handlePaste(event: ClipboardEvent<HTMLLabelElement>) {
    const files = imageFiles(event.clipboardData.files);
    if (files.length) void props.onFiles(files).catch(showUploadError);
  }

  return (
    <div className={props.compact ? "evidence-block compact" : "evidence-block"}>
      <label
        className={props.compact ? "evidence-zone compact" : "evidence-zone"}
        tabIndex={0}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        onPaste={handlePaste}
      >
        <Upload size={props.compact ? 14 : 18} />
        <b>{props.compact ? (props.images.length ? `${props.images.length} 张` : "图片") : "添加调研图片"}</b>
        <span>{props.compact ? "上传" : "粘贴 / 拖拽 / 选择，可多张"}</span>
        <input type="file" accept="image/*" multiple onChange={handleInput} />
      </label>
      {!!props.images.length && (
        <div className="evidence-list">
          {props.images.map((image) => (
            <div className="evidence-item" key={image.id}>
              <button className="evidence-thumb-button" type="button" onClick={() => setPreview(image)} title="查看大图">
                <img src={image.previewUrl} alt={image.name} />
              </button>
              <span>{image.name || "剪贴板图片"}</span>
              <button className="evidence-thumb-remove" type="button" onClick={() => props.onRemove(image.id)} title="删除图片">
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {preview && (
        <div className="image-preview" role="dialog" aria-modal="true" onClick={() => setPreview(null)}>
          <button className="image-preview-close" type="button" onClick={() => setPreview(null)}>
            <X size={18} />
          </button>
          <img src={preview.previewUrl} alt={preview.name} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function ReviewView(props: {
  rows: Opportunity[];
  target: Opportunity | null;
  setTarget: (value: Opportunity | null) => void;
  drafts: Record<string, ReviewDraft>;
  setDrafts: Dispatch<SetStateAction<Record<string, ReviewDraft>>>;
  list: ListState;
  setList: Dispatch<SetStateAction<ListState>>;
  onOpenDetail: (item: Opportunity) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onBulkReview: (items: Opportunity[], action: "approve" | "reject", reviewComment?: string) => Promise<void>;
}) {
  const [reviewType, setReviewType] = useState<"claim_submitted" | "claim_rejected">("claim_submitted");
  const [selectedReviewIds, setSelectedReviewIds] = useState<string[]>([]);
  const searchRows = useMemo(() => filterOpportunitiesBySearch(props.rows, props.list.query), [props.rows, props.list.query]);
  const filteredRows = useMemo(() => searchRows.filter((item) => item.current_status === reviewType), [reviewType, searchRows]);
  const pageRows = pageItems(filteredRows, props.list);
  const targetIsNotClaim = props.target?.current_status === "claim_rejected";
  const targetIsClaim = props.target?.current_status === "claim_submitted";
  const selectedReviewRows = filteredRows.filter((item) => selectedReviewIds.includes(item.id));
  const reviewDraft = props.target ? props.drafts[props.target.id] || reviewDraftFor(props.target) : reviewDraftFor(null);
  const reviewDecision = reviewDraft.reviewStatus;

  function patchReviewDraft(patch: Partial<ReviewDraft>) {
    if (!props.target) return;
    props.setDrafts((current) => ({
      ...current,
      [props.target!.id]: { ...(current[props.target!.id] || reviewDraftFor(props.target)), ...patch }
    }));
  }

  useEffect(() => {
    setSelectedReviewIds((current) => {
      const next = current.filter((id) => filteredRows.some((item) => item.id === id));
      return next.length === current.length ? current : next;
    });
  }, [filteredRows]);

  function changeReviewType(value: "claim_submitted" | "claim_rejected") {
    setReviewType(value);
    setSelectedReviewIds([]);
    props.setTarget(null);
    props.setList((current) => ({ ...current, page: 1 }));
  }

  function toggleReview(item: Opportunity, checked: boolean) {
    setSelectedReviewIds((current) => (checked ? Array.from(new Set([...current, item.id])) : current.filter((id) => id !== item.id)));
  }

  async function bulkApprove() {
    await props.onBulkReview(selectedReviewRows, "approve");
    setSelectedReviewIds([]);
  }

  async function bulkReject() {
    const reason = window.prompt("请输入批量拒绝原因，商品将退回运营补充", "");
    if (!reason?.trim()) return;
    await props.onBulkReview(selectedReviewRows, "reject", reason.trim());
    setSelectedReviewIds([]);
  }

  return (
    <div className="review-layout">
      <section className="group-list">
        <div className="mode-tabs review-type-tabs" aria-label="复核类型筛选">
          <button className={reviewType === "claim_submitted" ? "mode-tab active" : "mode-tab"} type="button" onClick={() => changeReviewType("claim_submitted")}>
            运营认领待复核（{searchRows.filter((item) => item.current_status === "claim_submitted").length}）
          </button>
          <button className={reviewType === "claim_rejected" ? "mode-tab active reject" : "mode-tab"} type="button" onClick={() => changeReviewType("claim_rejected")}>
            运营不认领待复核（{searchRows.filter((item) => item.current_status === "claim_rejected").length}）
          </button>
        </div>
        <ListControls label="主管复核" list={props.list} total={filteredRows.length} setList={(patch) => props.setList((current) => ({ ...current, ...patch }))} />
        {filteredRows.length > 0 && (
          <div className="claim-bulkbar review-bulkbar">
            <label className="checkline">
              <input
                checked={selectedReviewIds.length === filteredRows.length}
                onChange={(event) => setSelectedReviewIds(event.target.checked ? filteredRows.map((item) => item.id) : [])}
                type="checkbox"
              />
              已选 {selectedReviewIds.length} / {filteredRows.length} 个{reviewType === "claim_submitted" ? "认领" : "不认领"}复核
            </label>
            <button className="btn primary" disabled={!selectedReviewIds.length} onClick={bulkApprove}>
              <CheckCircle2 size={15} />
              批量通过
            </button>
            <button className="btn danger" disabled={!selectedReviewIds.length} onClick={bulkReject}>
              <XCircle size={15} />
              批量拒绝
            </button>
          </div>
        )}
        {!props.rows.length && <EmptySmall text="没有待主管复核的认领或不认领任务。" />}
        {!!props.rows.length && !filteredRows.length && <EmptySmall text="当前搜索条件下没有待复核任务。" />}
        {pageRows.map((item) => (
          <article className={`group-item compact${props.target?.id === item.id ? " active" : ""}`} key={item.id}>
            <div className="sku-group">
              <input
                aria-label={`选择 ${item.main_sku} 批量复核`}
                checked={selectedReviewIds.includes(item.id)}
                className="card-check"
                onChange={(event) => toggleReview(item, event.target.checked)}
                type="checkbox"
              />
              <ProductThumb item={item} />
              <div>
                <div className="title-row">
                  <button className="sku-title-link" type="button" onClick={() => props.onOpenDetail(item)} title="查看商品详情">
                    {item.main_sku}
                  </button>
                  {statusPill(item.current_status)}
                  <span className="tag">{item.current_status === "claim_submitted" ? "运营已认领" : "运营不认领"}</span>
                </div>
                <p>
                  <button className="text-link" type="button" onClick={() => props.onOpenDetail(item)}>{item.sub_sku}</button> · {item.sub_sku_name || item.keyword || "-"}
                </p>
                <p className="muted">
                  {item.latest_claim_salesperson || "运营"}提交了{item.current_status === "claim_submitted" ? "认领" : "不认领"}，主管不代改运营填写内容。
                </p>
                {item.current_status === "claim_submitted" && (
                  <p className="muted">认领单销：{formatBusinessNumber(item.latest_claim_daily_sales) || "未填写"}</p>
                )}
                {item.current_status === "claim_rejected" && item.latest_reject_reason && (
                  <p className="muted">不认领原因：{item.latest_reject_reason}</p>
                )}
              </div>
              <div className="review-card-actions">
                <button className="btn primary" onClick={() => props.setTarget(item)}>
                  复核
                </button>
              </div>
            </div>
          </article>
        ))}
      </section>
      <section className="form-card">
        <h3>
          <ShieldCheck size={16} />
          {props.target ? "主管复核" : "选择左侧任务"}
        </h3>
        {props.target ? (
          <form className="form" onSubmit={props.onSubmit}>
            <OperatorSubmissionSummary item={props.target} />
            <label>
              复核人
              <input name="reviewer_name" required value={reviewDraft.reviewerName} onChange={(event) => patchReviewDraft({ reviewerName: event.target.value })} />
            </label>
            {targetIsClaim && (
              <label>
                复核结果
                <select name="review_status" value={reviewDecision} onChange={(event) => patchReviewDraft({ reviewStatus: event.target.value })}>
                  <option value="approved">通过认领</option>
                  <option value="returned_for_supplement">退回补充</option>
                </select>
              </label>
            )}
            {targetIsNotClaim && (
              <label>
                复核结果
                <select name="review_status" value={reviewDecision} onChange={(event) => patchReviewDraft({ reviewStatus: event.target.value })}>
                  <option value="confirmed_not_claim">确认不认领</option>
                  <option value="returned_for_supplement">退回补充</option>
                </select>
              </label>
            )}
            {(targetIsClaim || targetIsNotClaim) && reviewDecision === "returned_for_supplement" && (
              <label>
                退回原因
                <textarea name="review_comment" rows={4} required value={reviewDraft.reviewComment} onChange={(event) => patchReviewDraft({ reviewComment: event.target.value })} placeholder="说明需要运营补充什么内容" />
              </label>
            )}
            <div className="action-row">
              <button className="btn primary" type="submit">
                提交复核
              </button>
              <button className="btn" type="button" onClick={() => props.setTarget(null)}>
                取消
              </button>
            </div>
          </form>
        ) : (
          <p className="muted">信息不完整时退回运营补充；通过后进入导出中心。</p>
        )}
      </section>
    </div>
  );
}

function OperatorSubmissionSummary({ item, title = "运营提交内容" }: { item: Opportunity; title?: string }) {
  const evidenceImages = parseSubmittedEvidenceImages(item.latest_claim_note);
  const isNotClaim = item.latest_claim_result === "reject" || item.current_status === "claim_rejected";
  const [previewImage, setPreviewImage] = useState<SubmittedEvidenceImage | null>(null);

  return (
    <div className="operator-submission">
      <h4>{title}</h4>
      <div className="submission-row">
        <span>提交人</span>
        <b>{item.latest_claim_salesperson || "运营"}</b>
      </div>
      <div className="submission-row">
        <span>提交结果</span>
        <b>{isNotClaim ? "不认领" : "认领"}</b>
      </div>
      {!isNotClaim && (
        <div className="submission-row">
          <span>认领单销</span>
          <b>{formatBusinessNumber(item.latest_claim_daily_sales) || "未填写"}</b>
        </div>
      )}
      {isNotClaim && (
        <div className="submission-row">
          <span>不认领原因</span>
          <p>{item.latest_reject_reason || "未填写"}</p>
        </div>
      )}
      {item.latest_feedback_summary && (
        <div className="submission-row">
          <span>调研结论</span>
          <p>{item.latest_feedback_summary}</p>
        </div>
      )}
      {!!evidenceImages.length && (
        <div className="submission-row">
          <span>图片附件</span>
          <div className="submitted-evidence-list">
            {evidenceImages.map((image, index) => (
              <div className="submitted-evidence-item" key={`${image.name}-${index}`}>
                {image.previewUrl ? (
                  <button className="submitted-evidence-thumb" type="button" onClick={() => setPreviewImage(image)} title="查看大图">
                    <img src={image.previewUrl} alt={image.name} />
                  </button>
                ) : (
                  <div>图</div>
                )}
                <p title={image.name}>{image.name}</p>
                <small>{[image.type, image.size ? formatFileSize(image.size) : ""].filter(Boolean).join(" · ")}</small>
              </div>
            ))}
          </div>
        </div>
      )}
      {previewImage?.previewUrl && (
        <div className="image-preview" role="dialog" aria-modal="true" onClick={() => setPreviewImage(null)}>
          <button className="image-preview-close" type="button" onClick={() => setPreviewImage(null)}>
            <X size={18} />
          </button>
          <img src={previewImage.previewUrl} alt={previewImage.name} onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </div>
  );
}

function StockView({
  rows,
  periods,
  list,
  setList,
  onStatus
}: {
  rows: AvailableStockingItem[];
  periods: ExportPeriodSummary[];
  list: ListState;
  setList: Dispatch<SetStateAction<ListState>>;
  onStatus: (message: string) => void;
}) {
  const [selectedPeriod, setSelectedPeriod] = useState("");
  const [busyDownloads, setBusyDownloads] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setSelectedPeriod((current) => selectExportPeriod(periods, current));
  }, [periods]);

  const periodRows = filterRowsForExportPeriod(rows, selectedPeriod);
  const filteredRows = periodRows.filter((row) => stockItemMatches(row, list.query));
  const pageRows = pageItems(filteredRows, list);

  function viewPeriod(businessPeriod: string) {
    setSelectedPeriod(businessPeriod);
    setList((current) => ({ ...current, page: 1 }));
  }

  async function downloadPeriod(period: ExportPeriodSummary, exportType: "stocking" | "traceability") {
    const busyKey = `${exportType}:${period.business_period}`;
    setBusyDownloads((current) => ({ ...current, [busyKey]: true }));
    try {
      if (exportType === "stocking") {
        await api.availableStockingExport(exportPeriodFilter(period.business_period));
        onStatus(`已导出 ${period.business_period} 海外仓备货表`);
      } else {
        await api.traceabilityExport(exportPeriodFilter(period.business_period));
        onStatus(`已导出 ${period.business_period} 中央字段追溯表`);
      }
    } catch (error) {
      onStatus(error instanceof Error ? error.message : "导出失败");
    } finally {
      setBusyDownloads(({ [busyKey]: _, ...current }) => current);
    }
  }

  return (
    <div>
      <div className="table-wrap export-periods-wrap">
        <table className="export-periods-table">
          <thead>
            <tr>
              <th>业务期数</th>
              <th>海外仓备货表</th>
              <th>中央字段追溯表</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {!periods.length && (
              <tr>
                <td colSpan={4}>暂无可导出的业务期数</td>
              </tr>
            )}
            {periods.map((period) => {
              const stockingBusy = Boolean(busyDownloads[`stocking:${period.business_period}`]);
              const traceabilityBusy = Boolean(busyDownloads[`traceability:${period.business_period}`]);
              return (
                <tr key={period.business_period} className={period.business_period === selectedPeriod ? "export-period-row active" : "export-period-row"}>
                  <td>{period.business_period}</td>
                  <td>{period.stocking_count}</td>
                  <td>{period.traceability_count}</td>
                  <td>
                    <div className="export-period-actions">
                      <button className="btn blue" type="button" onClick={() => viewPeriod(period.business_period)}>
                        查看明细
                      </button>
                      <button
                        className="btn primary"
                        type="button"
                        disabled={period.stocking_count <= 0 || stockingBusy}
                        onClick={() => void downloadPeriod(period, "stocking")}
                      >
                        <Download size={15} />
                        导出海外仓表
                      </button>
                      <button
                        className="btn"
                        type="button"
                        disabled={period.traceability_count <= 0 || traceabilityBusy}
                        onClick={() => void downloadPeriod(period, "traceability")}
                      >
                        <Download size={15} />
                        导出中央追溯表
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <ListControls label="导出中心" list={list} total={filteredRows.length} setList={(patch) => setList((current) => ({ ...current, ...patch }))} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>操作状态</th>
              <th>时间</th>
              <th>备货类型</th>
              <th>选品数据源</th>
              <th>运营</th>
              <th>主 SKU</th>
              <th>子 SKU</th>
              <th>成本价</th>
              <th>单个体积</th>
              <th>备货单销</th>
              <th>备货数量</th>
              <th>备货国家</th>
              <th>备货仓库</th>
              <th>货值</th>
              <th>体积</th>
              <th>补货原因</th>
            </tr>
          </thead>
          <tbody>
            {!periodRows.length && (
              <tr>
                <td colSpan={16}>{selectedPeriod ? `${selectedPeriod} 暂无可导出记录` : "请选择业务期数查看明细"}</td>
              </tr>
            )}
            {!!periodRows.length && !filteredRows.length && (
              <tr>
                <td colSpan={16}>{selectedPeriod} 当前搜索条件下没有可导出记录</td>
              </tr>
            )}
            {pageRows.map((row) => (
              <tr key={row.claim_record_id}>
                <td>{row.operation_status}</td>
                <td>{formatDate(row.time)}</td>
                <td>{row.stocking_type}</td>
                <td>{row.selection_source}</td>
                <td>{row.salesperson_name || ""}</td>
                <td>{row.main_sku}</td>
                <td>{row.sub_sku}</td>
                <td>{row.cost_price ?? ""}</td>
                <td>{row.unit_volume ?? ""}</td>
                <td>{formatBusinessNumber(row.claim_daily_sales)}</td>
                <td>{row.quantity}</td>
                <td>{row.stocking_country || ""}</td>
                <td>{row.warehouse || ""}</td>
                <td>{row.amount ?? ""}</td>
                <td>{row.unit_volume == null ? "" : Number((row.unit_volume * row.quantity).toFixed(6))}</td>
                <td>{row.replenishment_reason || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ArrivalPreviewView({
  date,
  preview,
  list,
  setDate,
  setList,
  onLoad
}: {
  date: string;
  preview: PlmArrivalPreview | null;
  list: ListState;
  setDate: (value: string) => void;
  setList: Dispatch<SetStateAction<ListState>>;
  onLoad: () => void;
}) {
  const filteredItems = (preview?.items || []).filter((item) => arrivalItemMatches(item, list.query));
  const pageRows = pageItems(filteredItems, list);
  return (
    <div className="arrival-preview">
      <div className="action-row stock-actions">
        <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        <button className="btn primary" onClick={onLoad}>
          <RefreshCw size={15} />
          刷新预览
        </button>
      </div>
      {preview && (
        <>
          <div className="metrics">
            <div className="metric">
              <span>总到货</span>
              <b>{preview.row_count}</b>
            </div>
            <div className="metric">
              <span>新品到货</span>
              <b>{preview.new_arrival_count}</b>
            </div>
            <div className="metric">
              <span>老品补货</span>
              <b>{preview.restock_count}</b>
            </div>
            <div className="metric">
              <span>无法判断</span>
              <b>{preview.unknown_count}</b>
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>运营</th>
                  <th>新品</th>
                  <th>老品</th>
                  <th>无法判断</th>
                  <th>合计</th>
                </tr>
              </thead>
              <tbody>
                {preview.by_salesperson.map((row) => (
                  <tr key={row.salesperson_name}>
                    <td>{row.salesperson_name}</td>
                    <td>{row.new_arrival_count}</td>
                    <td>{row.restock_count}</td>
                    <td>{row.unknown_count}</td>
                    <td>{row.total_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ListControls label="PLM 到货明细" list={list} total={filteredItems.length} setList={(patch) => setList((current) => ({ ...current, ...patch }))} />
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>类型</th>
                  <th>运营</th>
                  <th>子 SKU</th>
                  <th>主 SKU</th>
                  <th>国家</th>
                  <th>海外仓</th>
                  <th>最后入库</th>
                  <th>首次上架</th>
                  <th>可发</th>
                  <th>真仓库存</th>
                  <th>单销</th>
                </tr>
              </thead>
              <tbody>
                {!pageRows.length && (
                  <tr>
                    <td colSpan={11}>当前条件下没有到货记录</td>
                  </tr>
                )}
                {pageRows.map((item, index) => (
                  <tr key={`${item.sub_sku || index}-${item.latest_storage_time || ""}`}>
                    <td>{arrivalTypeLabel(item.arrival_type)}</td>
                    <td>{item.salesperson_name}</td>
                    <td>{item.sub_sku || ""}</td>
                    <td>{item.main_sku || ""}</td>
                    <td>{item.country || ""}</td>
                    <td>{item.warehouse || ""}</td>
                    <td>{item.latest_storage_time || ""}</td>
                    <td>{item.first_listing_time || ""}</td>
                    <td>{item.available_quantity ?? ""}</td>
                    <td>{item.real_stock_quantity ?? ""}</td>
                    <td>{formatBusinessNumber(item.daily_sales)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {!preview && <div className="empty-state">请选择日期并刷新 PLM 到货预览</div>}
    </div>
  );
}

function Toolbar({
  activeView,
  assignSummary,
  onPreview,
  onCancelPreview,
  hasAssignmentPreview,
  onAssign,
  onOpenProfilePanel
}: {
  activeView: ViewKey;
  assignSummary: {
    enabledCount: number;
    groupCount: number;
    childCount: number;
    selectedGroupCount: number;
    unassignedGroupCount: number;
  };
  onPreview: () => void;
  onCancelPreview: () => void;
  hasAssignmentPreview: boolean;
  onAssign: () => void;
  onOpenProfilePanel: () => void;
}) {
  if (activeView === "assign") {
    return (
      <div className="toolbar">
        <span className="tag">启用运营：{assignSummary.enabledCount}</span>
        <span className="tag">待分配主 SKU 组：{assignSummary.groupCount}</span>
        <span className="tag">待分配子 SKU：{assignSummary.childCount}</span>
        <span className="tag">已选最终分配：{assignSummary.selectedGroupCount}</span>
        <span className="tag">仍未分配：{assignSummary.unassignedGroupCount}</span>
        <button className="btn" onClick={onPreview}>
          生成推荐
        </button>
        <button className="btn" disabled={!hasAssignmentPreview} onClick={onCancelPreview}>
          <X size={15} />
          取消推荐
        </button>
        <span className="assignment-primary-actions">
          <button className="btn primary" onClick={onAssign}>
            <WandSparkles size={15} />
            提交分配
          </button>
          <button className="btn assignment-config-trigger" type="button" onClick={onOpenProfilePanel}>
            <Users size={15} />
            运营配置
          </button>
        </span>
      </div>
    );
  }
  if (activeView === "pool") {
    return (
      <div className="toolbar">
        <span className="tag">只展示选品2/财根可自领机会；选品1在分配台处理</span>
        <span className="pill gray">状态优先</span>
      </div>
    );
  }
  return null;
}

function ListControls({
  label,
  list,
  total,
  searchPlaceholder,
  setList
}: {
  label: string;
  list: ListState;
  total: number;
  searchPlaceholder?: string;
  setList: (patch: Partial<ListState>) => void;
}) {
  const pages = listPageCount(total, list.pageSize);
  const page = clampPage(list.page, pages);
  const start = total ? (page - 1) * list.pageSize + 1 : 0;
  const end = Math.min(total, page * list.pageSize);
  return (
    <div className="list-controls">
      <label className="list-search">
        <Search size={16} />
        <input
          value={list.query}
          onChange={(event) => setList({ query: event.target.value, page: 1 })}
          placeholder={searchPlaceholder || `${label}搜索：主 SKU / 子 SKU / 商品名 / 站点 / 类目 / 运营 / 状态`}
        />
      </label>
      <select value={list.pageSize} onChange={(event) => setList({ pageSize: Number(event.target.value), page: 1 })}>
        {[20, 50, 100, 200].map((size) => (
          <option key={size} value={size}>
            {size} 条/页
          </option>
        ))}
      </select>
      <span className="tag">{start}-{end} / {total}</span>
      <button className="btn" disabled={page <= 1} onClick={() => setList({ page: page - 1 })}>
        上一页
      </button>
      <span className="tag">第 {page} / {pages} 页</span>
      <button className="btn" disabled={page >= pages} onClick={() => setList({ page: page + 1 })}>
        下一页
      </button>
    </div>
  );
}

function pageItems<T>(items: T[], list: ListState): T[] {
  const page = clampPage(list.page, listPageCount(items.length, list.pageSize));
  const start = (page - 1) * list.pageSize;
  return items.slice(start, start + list.pageSize);
}

function listPageCount(total: number, pageSize: number) {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}

function clampPage(page: number, pages: number) {
  return Math.min(Math.max(1, page), pages);
}

function filterGroupsBySearch(groups: ProductGroup[], query: string) {
  const needle = normalizeSearch(query);
  if (!needle) return groups;
  return groups.filter((group) => groupSearchText(group).includes(needle));
}

function filterOpportunitiesBySearch(items: Opportunity[], query: string) {
  const needle = normalizeSearch(query);
  if (!needle) return items;
  return items.filter((item) => opportunitySearchText(item).includes(needle));
}

function stockItemMatches(row: AvailableStockingItem, query: string) {
  const needle = normalizeSearch(query);
  if (!needle) return true;
  return normalizeSearch([
    row.operation_status,
    row.stocking_type,
    row.selection_source,
    row.salesperson_name,
    row.main_sku,
    row.sub_sku,
    row.site,
    row.stocking_country,
    row.warehouse,
    row.replenishment_reason,
    row.review_status
  ].join(" ")).includes(needle);
}

function arrivalItemMatches(row: PlmArrivalPreview["items"][number], query: string) {
  const needle = normalizeSearch(query);
  if (!needle) return true;
  return normalizeSearch([
    arrivalTypeLabel(row.arrival_type),
    row.salesperson_name,
    row.sub_sku,
    row.main_sku,
    row.country,
    row.warehouse,
    row.latest_storage_time,
    row.first_listing_time
  ].join(" ")).includes(needle);
}

function arrivalTypeLabel(value: string) {
  if (value === "new_arrival") return "新品到货";
  if (value === "restock") return "老品补货";
  return "无法判断";
}

function groupSearchText(group: ProductGroup) {
  return normalizeSearch([
    group.main_sku,
    ownerText(group),
    statusLabel(group.status),
    healthLabel(group),
    group.items.map(opportunitySearchText).join(" ")
  ].join(" "));
}

function opportunitySearchText(item: Opportunity) {
  return normalizeSearch([
    item.main_sku,
    item.sub_sku,
    item.main_sku_name,
    item.sub_sku_name,
    item.keyword,
    item.site,
    item.country,
    item.category_level1,
    item.developer_name,
    item.latest_claim_salesperson,
    item.source_sheet,
    item.source_type,
    statusLabel(item.current_status)
  ].join(" "));
}

function normalizeSearch(value: string) {
  return value.toLowerCase().replace(/\s+/g, "");
}

function StatusCell({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="status-cell">
      <span>{label}</span>
      <b>{value ?? "-"}</b>
    </div>
  );
}

function EmptySmall({ text }: { text: string }) {
  return <div className="empty-small">{text}</div>;
}

function groupOpportunities(items: Opportunity[]): ProductGroup[] {
  return groupByBusinessIdentity(items).map(({ key, items: groupItems }) => ({
    key,
    main_sku: groupItems[0].main_sku,
    items: groupItems,
    first: groupItems[0],
    status: summarizeStatus(groupItems)
  }));
}

function toPendingAssignmentGroup(group: ProductGroup): ProductGroup | null {
  const pendingItems = group.items.filter((item) => item.current_status === "pending_assignment");
  if (!pendingItems.length) return null;
  return {
    ...group,
    items: pendingItems,
    first: pendingItems[0],
    status: summarizeStatus(pendingItems)
  };
}

function filterDashboardGroups(groups: ProductGroup[], filters: DashboardFilters) {
  const query = filters.query.trim().toLowerCase();
  return groups.filter((group) => {
    if (filters.status && statusLabel(group.status) !== filters.status && !group.items.some((item) => statusLabel(item.current_status) === filters.status)) return false;
    if (filters.health && healthLabel(group) !== filters.health) return false;
    if (filters.site && !group.items.some((item) => fieldValue(item.site || item.country) === filters.site)) return false;
    if (filters.owner && ownerText(group) !== filters.owner) return false;
    if (filters.category && !group.items.some((item) => fieldValue(item.category_level1) === filters.category)) return false;
    if (filters.source && !group.items.some((item) => sourceLabel(item) === filters.source)) return false;
    if (!query) return true;
    return group.items.some((item) =>
      [item.main_sku, item.sub_sku, item.main_sku_name, item.sub_sku_name, item.keyword, item.site, item.country, item.category_level1, ownerText(group), statusLabel(item.current_status)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  });
}

function buildDashboardOptions(groups: ProductGroup[]) {
  const statuses = new Set<string>();
  const sites = new Set<string>();
  const owners = new Set<string>();
  const categories = new Set<string>();
  const sources = new Set<string>();
  for (const group of groups) {
    statuses.add(group.status);
    owners.add(ownerText(group));
    for (const item of group.items) {
      statuses.add(item.current_status);
      if (item.site || item.country) sites.add(fieldValue(item.site || item.country));
      if (item.category_level1) categories.add(fieldValue(item.category_level1));
      sources.add(sourceLabel(item));
    }
  }
  return {
    statuses: Array.from(statuses).map(statusLabel).sort(),
    sites: Array.from(sites).sort(),
    owners: Array.from(owners).sort(),
    categories: Array.from(categories).sort(),
    sources: Array.from(sources).sort()
  };
}

function healthLabel(group: ProductGroup) {
  if (group.items.some((item) => !item.main_sku || !item.sub_sku)) return "异常";
  if (group.status === "mixed" || group.items.some((item) => ["returned_for_supplement", "claim_rejected"].includes(item.current_status))) return "需关注";
  return "正常";
}

function fieldValue(value: string | null | undefined) {
  return value || "未填";
}

function sourceLabel(item: Opportunity) {
  return item.source_sheet || item.source_type || "未填来源";
}

function groupReason(group: ProductGroup) {
  return group.items.find((item) => item.reason)?.reason || "暂无开品理由";
}

function summarizeStatus(items: Opportunity[]) {
  const statuses = new Set(items.map((item) => item.current_status));
  return statuses.size === 1 ? items[0].current_status : "mixed";
}

function statusLabel(status: string) {
  return statusMeta[status]?.label || status;
}

function statusPill(status: string) {
  const meta = statusMeta[status] || { label: status, klass: "gray" };
  return <span className={`pill ${meta.klass}`}>{meta.label}</span>;
}

function primaryActionLabel(group: ProductGroup) {
  if (group.items.some((item) => item.current_status === "pending_assignment")) return "去分配";
  if (group.items.some(isOperatorClaimItem)) return "去认领";
  return "";
}

function poolPrimaryLabel(group: ProductGroup, role: RoleKey) {
  if (role === "manager" && group.items.some((item) => item.current_status === "pending_assignment")) return "去分配";
  if (role === "operator" && group.items.some(isSelfClaimPoolItem)) return "加入认领";
  return "";
}

function ownerText(group: ProductGroup) {
  const owner = group.items.find((item) => item.developer_name)?.developer_name;
  return owner || "未分配";
}

function buildStats(opportunities: Opportunity[], tasks: Task[], availableStocking: AvailableStockingItem[]) {
  const byStatus = opportunities.reduce<Record<string, number>>((acc, item) => {
    acc[item.current_status] = (acc[item.current_status] || 0) + 1;
    return acc;
  }, {});
  return {
    assigned: byStatus.assigned || 0,
    returned: byStatus.returned_for_supplement || 0,
    selfClaimPool: opportunities.filter((item) => isCaigenOpportunity(item) && ["pending_assignment", "open_claim_pool"].includes(item.current_status)).length,
    ready: availableStocking.length,
    sourceTodo: 2,
    pendingAssign: byStatus.pending_assignment || 0,
    pendingReview: tasks.filter((task) => task.task_type === "manager_review" && task.status === "pending").length || (byStatus.claim_submitted || 0) + (byStatus.claim_rejected || 0)
  };
}

function roleMetrics(role: RoleKey, stats: ReturnType<typeof buildStats>): [string, number][] {
  if (role === "operator") {
    return [
      ["待认领", stats.assigned],
      ["待补充", stats.returned],
      ["可自认领", stats.selfClaimPool],
      ["已通过", stats.ready]
    ];
  }
  return [
    ["待导入", stats.sourceTodo],
    ["待分配", stats.pendingAssign],
    ["待复核", stats.pendingReview],
    ["可导出", stats.ready]
  ];
}

function viewIcon(view: ViewKey) {
  if (view === "dashboard") return <LayoutDashboard size={16} />;
  const item = flowItems.find((entry) => entry.view === view);
  return item?.icon;
}

function formatFileSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function parseSubmittedEvidenceImages(note?: string | null): SubmittedEvidenceImage[] {
  return parseClaimEvidenceImages(note).map((image) => ({
    name: image.name,
    type: image.type,
    size: image.size,
    previewUrl: imageSrc(image.url || image.previewUrl || "") || undefined
  }));
}

async function readEvidenceFiles(files: FileList | File[], opportunityId: string) {
  return Promise.all(imageFiles(files).map((file) => readEvidenceFile(file, opportunityId)));
}

async function readEvidenceFile(file: File, opportunityId: string): Promise<EvidenceImage> {
  const uploaded = await api.uploadClaimEvidence(opportunityId, file);
  return {
    id: typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${file.name}`,
    name: uploaded.name || file.name || "clipboard-image.png",
    type: uploaded.type || file.type,
    size: uploaded.size || file.size,
    previewUrl: imageSrc(uploaded.url),
    url: uploaded.url
  };
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : "";
}

function previousDateText() {
  const date = new Date();
  date.setDate(date.getDate() - 1);
  return date.toISOString().slice(0, 10);
}

function formatDateTime(value?: string | null) {
  return value ? value.replace("T", " ").slice(0, 16) : "-";
}

export default App;
