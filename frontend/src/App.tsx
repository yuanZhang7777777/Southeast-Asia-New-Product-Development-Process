import {
  ArrowLeft,
  CheckCircle2,
  ClipboardPen,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
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
import { ChangeEvent, ClipboardEvent, DragEvent, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  API_BASE,
  api,
  AssignmentPreviewItem,
  AuthSession,
  AvailableStockingItem,
  getAuthToken,
  Opportunity,
  OperatorAssignmentProfile,
  Selection1ImportResponse,
  setAuthToken,
  Task
} from "./api";

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
type ViewKey = "dashboard" | "source" | "pool" | "assign" | "claim" | "review" | "stock";

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

type ClaimDraft = {
  mode: "claim" | "reject";
  claimDailySales: string;
  rejectReason: string;
  evidenceImages: EvidenceImage[];
};

type AssignmentLoad = {
  groups: number;
  subSkus: number;
  draftGroups: number;
  draftSubSkus: number;
};

const flowItems: { view: ViewKey; roles: RoleKey[]; icon: ReactNode; label: string }[] = [
  { view: "source", roles: ["manager"], icon: <FileSpreadsheet size={16} />, label: "源表导入" },
  { view: "pool", roles: ["operator", "manager"], icon: <Database size={16} />, label: "新品机会池" },
  { view: "assign", roles: ["manager"], icon: <UserRoundPlus size={16} />, label: "分配台" },
  { view: "claim", roles: ["operator"], icon: <ClipboardPen size={16} />, label: "运营认领" },
  { view: "review", roles: ["manager"], icon: <ShieldCheck size={16} />, label: "主管复核" },
  { view: "stock", roles: ["manager"], icon: <Download size={16} />, label: "导出中心" }
];

const viewMeta: Record<ViewKey, { title: string; desc: string }> = {
  dashboard: { title: "商品看板", desc: "按主 SKU 分组查看全部商品当前状态，展开可看子 SKU 状态。" },
  source: { title: "源表导入", desc: "第一版只导入两张内部反馈表，写入平台数据库，不提供在线表自动写回入口。" },
  pool: { title: "新品机会池", desc: "默认按状态优先展示主 SKU 分组；展开后查看子 SKU 明细和来源追溯。" },
  assign: { title: "分配台", desc: "主管按主 SKU 整组生成推荐，可逐行调整最终分配；系统先按站点过滤候选人，再看重点品类1、重点品类2和负载。" },
  claim: { title: "运营认领", desc: "分配任务必须认领或不认领；财根机会池允许其他销售员自认领，人数不限。" },
  review: { title: "主管复核", desc: "主管只能通过、确认不认领或退回补充，不允许代改运营填写内容。" },
  stock: { title: "导出中心", desc: "只导出 Excel。按子 SKU 明细出行，同一子 SKU 被不同销售员认领时另起一行。" }
};

const statusMeta: Record<string, { label: string; klass: string }> = {
  pending_assignment: { label: "待分配", klass: "amber" },
  open_claim_pool: { label: "财根机会池", klass: "amber" },
  assigned: { label: "待认领", klass: "amber" },
  returned_for_supplement: { label: "已驳回-待运营补充", klass: "red" },
  claim_submitted: { label: "待复核-认领", klass: "amber" },
  claim_rejected: { label: "待复核-不认领", klass: "red" },
  ready_for_stocking: { label: "可备货", klass: "green" },
  confirmed_not_claim: { label: "已确认不认领", klass: "gray" },
  已确认不认领: { label: "已确认不认领", klass: "gray" },
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

const operatorClaimStatuses = new Set(["assigned", "open_claim_pool", "returned_for_supplement"]);
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
  return item.source_type === "selection2_caigen_claim_feedback" || item.source_file?.includes("财根");
}

function isSelfClaimPoolItem(item: Opportunity) {
  return item.current_status === "open_claim_pool" || (item.current_status === "pending_assignment" && isCaigenOpportunity(item));
}

function isOperatorClaimItem(item: Opportunity) {
  return operatorClaimStatuses.has(item.current_status) || isSelfClaimPoolItem(item);
}

function isVisibleOperatorClaimItem(item: Opportunity, assignedOpportunityIds: Set<string>) {
  if (isSelfClaimPoolItem(item)) return true;
  if (!operatorClaimStatuses.has(item.current_status)) return false;
  return assignedOpportunityIds.has(item.id);
}

function isPoolItem(item: Opportunity, role: RoleKey) {
  if (role === "manager") return item.current_status === "pending_assignment" || isOperatorClaimItem(item);
  return isOperatorClaimItem(item);
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
  const [activeOperator, setActiveOperator] = useState("");
  const [availableStocking, setAvailableStocking] = useState<AvailableStockingItem[]>([]);
  const [lastImport, setLastImport] = useState<Selection1ImportResponse | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [source1Sheet, setSource1Sheet] = useState("开发0623期");
  const [source2Sheet, setSource2Sheet] = useState("5.26期");
  const [source1File, setSource1File] = useState<File | null>(null);
  const [source2File, setSource2File] = useState<File | null>(null);
  const [previewItems, setPreviewItems] = useState<AssignmentPreviewItem[]>([]);
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, string>>({});
  const [reviewTarget, setReviewTarget] = useState<Opportunity | null>(null);
  const [detailGroupKey, setDetailGroupKey] = useState<string | null>(null);
  const [dashboardFilters, setDashboardFilters] = useState<DashboardFilters>(defaultDashboardFilters);
  const [newProfile, setNewProfile] = useState<Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "enabled">>({
    operator_name: "",
    key_site: "",
    key_category1: "",
    key_category2: "",
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
          .filter((task) => task.task_type === "sales_claim" && task.status === "pending" && task.assignee_name === activeOperator)
          .map((task) => task.opportunity_id)
          .filter((id): id is string => Boolean(id))
      ),
    [activeOperator, tasks]
  );
  const claimRows = useMemo(
    () => opportunities.filter((item) => isVisibleOperatorClaimItem(item, activeOperatorTaskOpportunityIds)),
    [activeOperatorTaskOpportunityIds, opportunities]
  );
  const reviewRows = useMemo(
    () => opportunities.filter((item) => ["claim_submitted", "claim_rejected"].includes(item.current_status)),
    [opportunities]
  );
  const detailGroup = useMemo(
    () => (detailGroupKey ? groups.find((group) => group.key === detailGroupKey) || null : null),
    [detailGroupKey, groups]
  );
  const stats = useMemo(() => buildStats(opportunities, tasks, availableStocking), [opportunities, tasks, availableStocking]);

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
    if (activeRole !== "operator") return;
    if (authSession?.operator_name) {
      if (activeOperator !== authSession.operator_name) setActiveOperator(authSession.operator_name);
      return;
    }
    if (activeOperator && operatorProfiles.some((profile) => profile.enabled && profile.operator_name === activeOperator)) return;
    setActiveOperator(operatorProfiles.find((profile) => profile.enabled)?.operator_name || "");
  }, [activeOperator, activeRole, authSession, operatorProfiles]);

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
    setOperatorProfiles([]);
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
    const [health, opportunityList, taskList, stockingList, profileList] = await Promise.all([
      loadPart("健康检查", api.health, { status: "error", environment: "unknown" }),
      loadPart("机会池", api.opportunities, []),
      loadPart("待办", api.tasks, []),
      loadPart("导出中心", api.availableStocking, []),
      loadPart("人员配置", api.operatorProfiles, [])
    ]);
    setHealthStatus(health.status);
    setOpportunities(opportunityList);
    setTasks(taskList);
    setAvailableStocking(stockingList);
    setOperatorProfiles(profileList);
    if (!options.silent || failures.length) {
      setStatusMessage(failures.length ? `部分数据未加载：${failures.join("、")}` : "已刷新");
    }
    if (!options.silent) setLoading(false);
  }

  async function runAction(label: string, action: () => Promise<unknown>) {
    setLoading(true);
    setStatusMessage(`${label}中...`);
    try {
      await action();
      setStatusMessage(`${label}完成`);
      await refresh();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : `${label}失败`);
    } finally {
      setLoading(false);
    }
  }

  async function importSelection(kind: 1 | 2) {
    await runAction(`导入选品${kind}`, async () => {
      const selectedFile = kind === 1 ? source1File : source2File;
      if (!selectedFile) throw new Error(`请先选择选品${kind}反馈表 Excel 文件`);
      const result =
        kind === 1
          ? await api.importSelection1File(source1Sheet, selectedFile)
          : await api.importSelection2File(source2Sheet, selectedFile);
      setLastImport(result);
      setActiveView("pool");
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

  async function submitAssignments() {
    await runAction("提交分配", async () => {
      if (!assignmentItems.length) throw new Error("没有待分配的主 SKU 组");
      const idsByAssignee = new Map<string, string[]>();
      for (const item of assignmentItems) {
        const assignee = assignmentDrafts[assignmentItemKey(item)];
        if (!assignee) continue;
        idsByAssignee.set(assignee, [...(idsByAssignee.get(assignee) || []), ...item.opportunity_ids]);
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
    await runAction(Array.isArray(payload) ? "批量提交认领" : "提交认领", async () => {
      const payloads = Array.isArray(payload) ? payload : [payload];
      for (const item of payloads) {
        await api.claim(item);
      }
    });
  }

  async function updateOpportunityDetails(id: string, payload: unknown) {
    await runAction("保存 SKU 信息", async () => {
      const updated = await api.updateOpportunity(id, payload);
      setDetailGroupKey(`${updated.source_type || ""}|${updated.main_sku}`);
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
          enabled: profile.enabled
        });
      }
    });
  }

  async function addProfile() {
    await runAction("新增人员配置", async () => {
      if (!newProfile.operator_name.trim()) throw new Error("销售员不能为空");
      await api.createOperatorProfile(newProfile);
      setNewProfile({ operator_name: "", key_site: "", key_category1: "", key_category2: "", enabled: true });
    });
  }

  async function removeProfile(profileId: string) {
    await runAction("删除人员配置", async () => {
      await api.deleteOperatorProfile(profileId);
    });
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewTarget) return;
    const form = new FormData(event.currentTarget);
    await runAction("提交复核", async () => {
      await api.review({
        opportunity_id: reviewTarget.id,
        reviewer_name: String(form.get("reviewer_name") || "练玉君"),
        review_status: String(form.get("review_status") || "approved"),
        review_comment: String(form.get("review_comment") || "")
      });
      setReviewTarget(null);
    });
  }

  async function approveClaimReviews(items: Opportunity[]) {
    if (!items.length) return;
    await runAction("批量通过认领", async () => {
      for (const item of items) {
        await api.review({
          opportunity_id: item.id,
          reviewer_name: "练玉君",
          review_status: "approved",
          review_comment: "批量通过认领"
        });
      }
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
                {operatorProfiles
                  .filter((profile) => profile.enabled)
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
        <section className="panel hub">
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
          <span className="hub-note">第一版冻结：只做导入、认领复核和导出；不做在线表自动写回入口</span>
        </section>

        <nav className="panel flow">
          {visibleFlow.map((item, index) => (
            <span className="flow-node" key={item.view}>
              {index > 0 && <span className="arrow">→</span>}
              <button className={activeView === item.view ? "flow-step active" : "flow-step"} onClick={() => setActiveView(item.view)}>
                {item.icon}
                {item.label}
              </button>
            </span>
          ))}
        </nav>

        <section className="layout">
          <div className="panel screen">
            <div className="screen-top">
              <div>
                <h1>
                  {viewIcon(activeView)}
                  {meta.title}
                </h1>
                <p>{meta.desc}</p>
              </div>
              <Toolbar activeView={activeView} assignSummary={assignSummary} onPreview={previewAssignments} onAssign={submitAssignments} />
            </div>
            {statusMessage && <div className={statusMessage.includes("失败") || statusMessage.includes("Error") ? "notice red" : "notice"}>{statusMessage}</div>}
            <div className="screen-body">
            {detailGroup ? (
              <ProductDetailView
                group={detailGroup}
                activeRole={activeRole}
                onBack={() => setDetailGroupKey(null)}
                onUpdate={updateOpportunityDetails}
              />
            ) : (
            <>
            {activeView === "source" && (
              <SourceView
                loading={loading}
                source1File={source1File}
                source1Sheet={source1Sheet}
                source2File={source2File}
                source2Sheet={source2Sheet}
                lastImport={lastImport}
                setSource1File={setSource1File}
                setSource1Sheet={setSource1Sheet}
                setSource2File={setSource2File}
                setSource2Sheet={setSource2Sheet}
                onImport={importSelection}
              />
            )}
            {activeView === "dashboard" && (
              <DashboardView
                groups={dashboardGroups}
                allCount={groups.length}
                filters={dashboardFilters}
                options={dashboardOptions}
                expanded={expanded}
                setFilter={(key, value) => setDashboardFilters((current) => ({ ...current, [key]: value }))}
                clearFilters={() => setDashboardFilters(defaultDashboardFilters)}
                toggle={(key) => setExpanded((current) => ({ ...current, [key]: !current[key] }))}
                onOpenDetail={(group) => setDetailGroupKey(group.key)}
                goImport={() => {
                  setActiveRole("manager");
                  setActiveView("source");
                }}
              />
            )}
            {activeView === "pool" && (
              <PoolView
                activeRole={activeRole}
                groups={poolGroups}
                expanded={expanded}
                toggle={(key) => setExpanded((current) => ({ ...current, [key]: !current[key] }))}
                onOpenDetail={(group) => setDetailGroupKey(group.key)}
                goAssign={() => {
                  setActiveRole("manager");
                  setActiveView("assign");
                }}
                goClaim={(opportunity) => {
                  setActiveRole("operator");
                  setActiveView("claim");
                }}
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
                operatorProfiles={operatorProfiles}
                setOperatorProfiles={setOperatorProfiles}
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
              <ClaimView rows={claimRows} activeOperator={activeOperator} onSubmit={submitClaimPayload} />
            )}
            {activeView === "review" && (
              <ReviewView rows={reviewRows} target={reviewTarget} setTarget={setReviewTarget} onSubmit={submitReview} onBulkApprove={approveClaimReviews} />
            )}
            {activeView === "stock" && <StockView rows={availableStocking} />}
            </>
            )}
            </div>
          </div>

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
        </section>
      </main>
    </div>
  );
}

function DashboardView(props: {
  groups: ProductGroup[];
  allCount: number;
  filters: DashboardFilters;
  options: ReturnType<typeof buildDashboardOptions>;
  expanded: Record<string, boolean>;
  setFilter: (key: keyof DashboardFilters, value: string) => void;
  clearFilters: () => void;
  toggle: (key: string) => void;
  onOpenDetail: (group: ProductGroup) => void;
  goImport: () => void;
}) {
  return (
    <div className="dashboard">
      <div className="dashboard-filters">
        <label className="wide">
          搜索
          <input
            value={props.filters.query}
            onChange={(event) => props.setFilter("query", event.target.value)}
            placeholder="主 SKU / 子 SKU / 商品名 / 关键词"
          />
        </label>
        <FilterSelect label="状态" value={props.filters.status} options={props.options.statuses} onChange={(value) => props.setFilter("status", value)} />
        <FilterSelect label="健康标签" value={props.filters.health} options={["正常", "需关注", "异常"]} onChange={(value) => props.setFilter("health", value)} />
        <FilterSelect label="站点" value={props.filters.site} options={props.options.sites} onChange={(value) => props.setFilter("site", value)} />
        <FilterSelect label="运营" value={props.filters.owner} options={props.options.owners} onChange={(value) => props.setFilter("owner", value)} />
        <FilterSelect label="类目" value={props.filters.category} options={props.options.categories} onChange={(value) => props.setFilter("category", value)} />
        <FilterSelect label="来源批次" value={props.filters.source} options={props.options.sources} onChange={(value) => props.setFilter("source", value)} />
        <button className="btn" onClick={props.clearFilters}>
          清空
        </button>
      </div>
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
          {props.groups.map((group) => (
            <ProductGroupCard
              group={group}
              expanded={Boolean(props.expanded[group.key])}
              key={group.key}
              onToggle={() => props.toggle(group.key)}
              onOpenDetail={() => props.onOpenDetail(group)}
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
  source2File: File | null;
  source2Sheet: string;
  lastImport: Selection1ImportResponse | null;
  setSource1File: (value: File | null) => void;
  setSource1Sheet: (value: string) => void;
  setSource2File: (value: File | null) => void;
  setSource2Sheet: (value: string) => void;
  onImport: (kind: 1 | 2) => void;
}) {
  return (
    <div className="source-grid">
      <ImportCard
        title="选品1：海外仓开发部门开发新品认领-反馈"
        desc="按中央表截断到“开发是否接受核价结果”之前的字段对齐，后接内部认领字段。"
        sheet={props.source1Sheet}
        file={props.source1File}
        setSheet={props.setSource1Sheet}
        setFile={props.setSource1File}
        buttonText="导入选品1反馈表"
        disabled={props.loading}
        onImport={() => props.onImport(1)}
      />
      <ImportCard
        title="选品2：海外仓财根团队开发新品认领-反馈"
        desc="作为财根机会池来源；主销售员必须处理，其他销售员可自认领。"
        sheet={props.source2Sheet}
        file={props.source2File}
        setSheet={props.setSource2Sheet}
        setFile={props.setSource2File}
        buttonText="导入选品2反馈表"
        disabled={props.loading}
        onImport={() => props.onImport(2)}
      />
      {props.lastImport && (
        <section className="info import-result">
          <h3>
            <FileCheck2 size={16} />
            最近导入结果
          </h3>
          <div className="status-grid">
            <StatusCell label="Sheet" value={props.lastImport.source_sheet} />
            <StatusCell label="入池" value={props.lastImport.imported_count} />
            <StatusCell label="新增" value={props.lastImport.created_count} />
            <StatusCell label="更新" value={props.lastImport.updated_count} />
            <StatusCell label="跳过" value={props.lastImport.skipped_count} />
            <StatusCell label="任务" value={props.lastImport.task_count} />
          </div>
        </section>
      )}
    </div>
  );
}

function ImportCard(props: {
  title: string;
  desc: string;
  sheet: string;
  file: File | null;
  buttonText: string;
  disabled: boolean;
  setSheet: (value: string) => void;
  setFile: (value: File | null) => void;
  onImport: () => void;
}) {
  async function takeFileList(files: FileList | null) {
    const file = files?.[0] || null;
    props.setFile(file);
    if (!file) return;
    try {
      const result = await api.excelSheets(file);
      if (result.default_sheet) props.setSheet(result.default_sheet);
    } catch {
      // Keep the typed sheet name when the workbook cannot be inspected locally.
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
        <label>
          Sheet
          <input value={props.sheet} onChange={(event) => props.setSheet(event.target.value)} />
        </label>
        <label
          className="upload-zone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            void takeFileList(event.dataTransfer.files);
          }}
        >
          <Upload size={20} />
          <b>{props.file ? props.file.name : "拖拽 Excel 到这里，或点击选择文件"}</b>
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
        <button className="btn primary" disabled={props.disabled || !props.file} onClick={props.onImport}>
          <Upload size={15} />
          {props.buttonText}
        </button>
      </div>
    </section>
  );
}

function PoolView(props: {
  activeRole: RoleKey;
  groups: ProductGroup[];
  expanded: Record<string, boolean>;
  toggle: (key: string) => void;
  onOpenDetail: (group: ProductGroup) => void;
  goAssign: () => void;
  goClaim: (opportunity: Opportunity) => void;
  goImport: () => void;
}) {
  if (!props.groups.length) {
    return (
      <section className="empty-state">
        <Database size={28} />
        <h3>还没有导入机会数据</h3>
        <p>先导入选品1和选品2反馈表，导入后这里会按主 SKU 分组展示。</p>
        <button className="btn primary" onClick={props.goImport}>
          去源表导入
        </button>
      </section>
    );
  }
  return (
    <div className="group-list">
      {props.groups.map((group) => (
        <ProductGroupCard
          group={group}
          expanded={Boolean(props.expanded[group.key])}
          key={group.key}
          onToggle={() => props.toggle(group.key)}
          onOpenDetail={() => props.onOpenDetail(group)}
          onPrimary={() => {
            if (props.activeRole === "manager" && group.items.some((item) => item.current_status === "pending_assignment")) props.goAssign();
            else if (props.activeRole === "operator" && group.items.some(isOperatorClaimItem)) props.goClaim(group.items[0]);
            else props.toggle(group.key);
          }}
          primaryLabel={poolPrimaryLabel(group, props.activeRole)}
          showPrimary={Boolean(poolPrimaryLabel(group, props.activeRole))}
        />
      ))}
    </div>
  );
}

function ProductGroupCard(props: {
  group: ProductGroup;
  expanded: boolean;
  onToggle: () => void;
  onOpenDetail: () => void;
  onPrimary?: () => void;
  primaryLabel?: string;
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
            <span className="tag">{ownerText(group)}</span>
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
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

const competitorSpecs = [
  { label: "最低价", link: "Z", price: "AA", sales: "AB" },
  { label: "Most orders", link: "AC", price: "AD", sales: "AE" },
  { label: "月销次高", link: "AF", price: "AG", sales: "AH" },
  { label: "月销第三高", link: "AI", price: "AJ", sales: "AK" },
  { label: "新晋", link: "AL", price: "AM", sales: "AN" }
];

const pricingSpecs = [
  ["AO", "参考单销"],
  ["AP", "参考定价"],
  ["AQ", "一次毛利额"],
  ["AR", "一次毛利额(RMB)"],
  ["AS", "一次毛利率"],
  ["AT", "预估单销"],
  ["AU", "推广期定价"],
  ["AV", "推广期利润率"]
] as const;

function hasOperatorSubmission(item: Opportunity) {
  return Boolean(item.latest_claim_result || item.latest_claim_salesperson || item.latest_reject_reason || item.latest_feedback_summary || item.latest_claim_note);
}

type SkuEditDraft = {
  main_sku: string;
  sub_sku: string;
  main_sku_name: string;
  sub_sku_name: string;
  site: string;
  country: string;
  category_level1: string;
  image_url: string;
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
    image_url: item.image_url || "",
    edit_reason: ""
  };
}

function ProductDetailView(props: {
  group: ProductGroup;
  activeRole: RoleKey;
  onBack: () => void;
  onUpdate: (id: string, payload: unknown) => Promise<void>;
}) {
  const { group } = props;
  const item = group.first;
  const imageItem = group.items.find((child) => child.image_url) || item;
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

  async function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingItem) return;
    if (!editDraft.edit_reason.trim()) {
      window.alert("请填写修改原因");
      return;
    }
    await props.onUpdate(editingItem.id, {
      ...editDraft,
      edit_reason: editDraft.edit_reason.trim()
    });
    setEditingItem(null);
  }
  return (
    <div className="detail-page">
      <div className="detail-toolbar">
        <button className="btn" type="button" onClick={props.onBack}>
          <ArrowLeft size={16} />
          返回
        </button>
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
        <h3>子 SKU 明细</h3>
        <div className="table-wrap detail-table-wrap">
          <table className="detail-table">
            <thead>
              <tr>
                <th>图片</th>
                <th>子 SKU</th>
                <th>商品名</th>
                <th>站点</th>
                <th>类目</th>
                <th>状态</th>
                <th>来源行</th>
                {props.activeRole === "manager" && <th>操作</th>}
              </tr>
            </thead>
            <tbody>
              {group.items.map((child) => (
                <tr key={child.id}>
                  <td>
                    <ProductThumb item={child} small />
                  </td>
                  <td>
                    <b>{child.sub_sku}</b>
                  </td>
                  <td>{child.sub_sku_name || child.main_sku_name || "-"}</td>
                  <td>{child.site || child.country || "-"}</td>
                  <td>{child.category_level1 || "-"}</td>
                  <td>{statusLabel(child.current_status)}</td>
                  <td>{child.source_sheet || "-"} · {child.source_row || "-"}</td>
                  {props.activeRole === "manager" && (
                    <td>
                      <button className="btn" type="button" onClick={() => startEdit(child)}>
                        <ClipboardPen size={14} />
                        编辑
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
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
                图片地址
                <input value={editDraft.image_url} onChange={(event) => patchEditDraft("image_url", event.target.value)} />
              </label>
            </div>
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

      <section className="detail-section">
        <h3>竞品链接与价格参考（Z:AV）</h3>
        <div className="detail-subsku-list">
          {group.items.map((child, index) => (
            <details className="detail-subsku" key={child.id} open={index === 0}>
              <summary>
                <span>{child.sub_sku}</span>
                <span className="muted">{child.sub_sku_name || child.main_sku_name || "未命名商品"}</span>
              </summary>
              {hasOperatorSubmission(child) && <OperatorSubmissionSummary item={child} />}
              <CompetitorTable item={child} />
              <PricingGrid item={child} />
            </details>
          ))}
        </div>
      </section>

      <section className="detail-section">
        <h3>认领与复核</h3>
        <div className="table-wrap detail-table-wrap">
          <table className="detail-table">
            <thead>
              <tr>
                <th>子 SKU</th>
                <th>运营</th>
                <th>认领结果</th>
                <th>不认领原因/备注</th>
                <th>主管复核</th>
                <th>复核意见</th>
              </tr>
            </thead>
            <tbody>
              {group.items.map((child) => (
                <tr key={child.id}>
                  <td>{child.sub_sku}</td>
                  <td>{child.latest_claim_salesperson || child.developer_name || "-"}</td>
                  <td>{claimResultLabel(child.latest_claim_result)}</td>
                  <td>{child.latest_reject_reason || child.latest_claim_note || child.latest_feedback_summary || "-"}</td>
                  <td>{reviewStatusLabel(child.latest_review_status)}</td>
                  <td>{child.latest_review_comment || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="detail-section">
        <h3>源表字段</h3>
        <div className="detail-subsku-list">
          {group.items.map((child, index) => (
            <details className="detail-subsku" key={child.id} open={index === 0}>
              <summary>
                <span>{child.sub_sku}</span>
                <span className="muted">{child.source_file || "-"} · {child.source_sheet || "-"} · 行 {child.source_row || "-"}</span>
              </summary>
              <SourceFieldsTable item={child} />
            </details>
          ))}
        </div>
      </section>
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
          {rows.map((row) => (
            <tr key={row.label}>
              <td>{row.label}</td>
              <td>{row.linkColumn}</td>
              <td>{renderLinkCell(row.link)}</td>
              <td>{row.priceColumn}</td>
              <td>{row.price || "-"}</td>
              <td>{row.salesColumn}</td>
              <td>{row.sales || "-"}</td>
            </tr>
          ))}
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
          <b>{row.value}</b>
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
    <a href={value} target="_blank" rel="noreferrer" className="link-inline">
      打开链接
      <ExternalLink size={14} />
    </a>
  );
}

function renderMaybeLink(value: string) {
  if (!isHttpUrl(value)) return value;
  return (
    <a href={value} target="_blank" rel="noreferrer" className="link-inline">
      {value}
      <ExternalLink size={14} />
    </a>
  );
}

function competitorRows(item: Opportunity) {
  const cells = snapshotCells(item);
  return competitorSpecs
    .map((spec) => ({
      label: spec.label,
      linkColumn: spec.link,
      priceColumn: spec.price,
      salesColumn: spec.sales,
      link: valueText(cells[spec.link]),
      price: valueText(cells[spec.price]),
      sales: valueText(cells[spec.sales])
    }))
    .filter((row) => row.link || row.price || row.sales);
}

function pricingRows(item: Opportunity) {
  const cells = snapshotCells(item);
  const snapshot = snapshotOf(item);
  const pricing = isRecord(snapshot.pricing_snapshot) ? snapshot.pricing_snapshot : {};
  return pricingSpecs
    .map(([column, label]) => ({ column, label, value: valueText(cells[column]) || valueText(pricing[label]) }))
    .filter((row) => row.value);
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
  if (url.startsWith(`${OSS_PUBLIC_BASE}/`)) return `${API_BASE}/claims/evidence-images/proxy?url=${encodeURIComponent(url)}`;
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
  operatorProfiles: OperatorAssignmentProfile[];
  setOperatorProfiles: (value: OperatorAssignmentProfile[]) => void;
  newProfile: Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "enabled">;
  setNewProfile: (value: Pick<OperatorAssignmentProfile, "operator_name" | "key_site" | "key_category1" | "key_category2" | "enabled">) => void;
  onSaveProfiles: () => void;
  onAddProfile: () => void;
  onDeleteProfile: (profileId: string) => void;
  onPreview: () => void;
  onAssign: () => void;
}) {
  const patchProfile = (id: string, patch: Partial<OperatorAssignmentProfile>) => {
    props.setOperatorProfiles(props.operatorProfiles.map((profile) => (profile.id === id ? { ...profile, ...patch } : profile)));
  };
  const enabledProfiles = props.operatorProfiles.filter((profile) => profile.enabled);
  const workload = assignmentWorkload(enabledProfiles, props.groups, props.tasks, props.previewItems, props.assignmentDrafts);
  const pendingGroups = props.assignmentGroups;
  const selectedCount = props.previewItems.filter((item) => props.assignmentDrafts[assignmentItemKey(item)]).length;
  const childSelectedCount = props.previewItems.reduce(
    (sum, item) => sum + (props.assignmentDrafts[assignmentItemKey(item)] ? item.sub_sku_count : 0),
    0
  );
  const patchDraft = (item: AssignmentPreviewItem, assignee: string) => {
    props.setAssignmentDrafts({ ...props.assignmentDrafts, [assignmentItemKey(item)]: assignee });
  };

  return (
    <div className="assign-layout">
      <section className="info assignment-table-panel">
        <div className="section-head">
          <h3>待分配主 SKU</h3>
          <div className="action-row">
            <span className="tag">已选 {selectedCount} 组 / {childSelectedCount} 子 SKU</span>
            <span className="tag">未分配 {props.previewItems.length ? props.previewItems.length - selectedCount : pendingGroups.length} 组</span>
          </div>
        </div>
        <div className="assignment-workload-grid">
          {enabledProfiles.map((profile) => {
            const load = workload[profile.operator_name] || emptyAssignmentLoad();
            const maxGroups = Math.max(1, ...Object.values(workload).map((item) => item.groups));
            return (
              <div className="assignment-workload-card" key={profile.id}>
                <div className="section-head compact">
                  <b>{profile.operator_name}</b>
                  <span className="tag">{profile.key_site || "-"}</span>
                </div>
                <p className="muted">{operatorProfileBrief(profile)}</p>
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
            {props.previewItems.map((item) => (
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
      <section className="info assignment-config-panel">
        <div className="section-head">
          <h3>
            <Users size={16} />
            运营配置
          </h3>
          <button className="btn primary" onClick={props.onSaveProfiles}>
            <Save size={15} />
            保存运营配置
          </button>
        </div>
        <p className="muted">第一版只维护销售员、重点站点、重点品类1、重点品类2。新增或调整后，下一次生成推荐立即生效。</p>
        <div className="profile-table">
          <div className="profile-row head">
            <span>启用</span>
            <span>销售员</span>
            <span>重点站点</span>
            <span>重点品类1</span>
            <span>重点品类2</span>
            <span>删除</span>
          </div>
          {props.operatorProfiles.map((profile) => (
            <div className="profile-row" key={profile.id}>
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
              <div className="action-row compact-actions">
                <button className="btn" onClick={() => props.onDeleteProfile(profile.id)} title="删除">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))}
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
              placeholder="销售员"
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
            <button className="btn primary" onClick={props.onAddProfile}>
              <Plus size={15} />
              新增
            </button>
          </div>
        </div>
      </section>
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
  return `${profile.key_site || "-"} · 品类1 ${profile.key_category1 || "-"} · 品类2 ${profile.key_category2 || "-"}`;
}

function operatorOptionLabel(profile: OperatorAssignmentProfile, load: AssignmentLoad) {
  return `${profile.operator_name}｜${profile.key_site || "-"}｜${profile.key_category1 || "-"} / ${profile.key_category2 || "-"}｜${load.groups}组/${load.subSkus}子SKU`;
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
          {props.enabledProfiles.map((profile) => (
            <option key={profile.id} value={profile.operator_name}>
              {operatorOptionLabel(profile, props.workload[profile.operator_name] || emptyAssignmentLoad())}
            </option>
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
    lines.push("负载均衡：同站点候选里品类优先级相同时，按当前负载更少推荐");
  } else if (item.match_reason?.includes("负载更低")) {
    lines.push("负载更低：同等匹配优先级下，选择当前负载更低的运营");
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

function normalizeSiteText(value?: string | null) {
  const text = value?.trim();
  if (!text) return "";
  const upper = text.toUpperCase();
  const aliases: Record<string, string> = {
    菲律宾: "PH",
    菲: "PH",
    PH: "PH",
    泰国: "TH",
    泰: "TH",
    TH: "TH",
    越南: "VN",
    越: "VN",
    VN: "VN",
    马来西亚: "MY",
    马来: "MY",
    MY: "MY",
    新加坡: "SG",
    SG: "SG",
    印度尼西亚: "ID",
    印尼: "ID",
    ID: "ID"
  };
  return aliases[text] || aliases[upper] || upper;
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
  onSubmit: (payload: unknown | unknown[]) => Promise<void>;
}) {
  const [drafts, setDrafts] = useState<Record<string, ClaimDraft>>({});
  const claimGroups = useMemo(() => groupOpportunities(props.rows), [props.rows]);

  function draftFor(item: Opportunity): ClaimDraft {
    return drafts[item.id] || { mode: "claim", claimDailySales: "", rejectReason: "", evidenceImages: [] };
  }

  function patchDraft(itemId: string, patch: Partial<ClaimDraft>) {
    setDrafts((current) => ({ ...current, [itemId]: { ...(current[itemId] || draftForId()), ...patch } }));
  }

  function setMode(itemId: string, mode: "claim" | "reject") {
    patchDraft(
      itemId,
      mode === "claim"
        ? { mode, rejectReason: "", evidenceImages: [] }
        : { mode, claimDailySales: "" }
    );
  }

  function buildPayload(item: Opportunity, draft: ClaimDraft, requireComplete: boolean) {
    const dailySales = draft.claimDailySales.trim();
    const rejectReason = draft.rejectReason.trim();
    if (draft.mode === "claim" && !dailySales) {
      if (requireComplete) window.alert("认领时必须填写认领单销");
      return null;
    }
    if (draft.mode === "reject" && !rejectReason) {
      if (requireComplete) window.alert("不认领时必须填写不认领原因");
      return null;
    }
    const note =
      draft.mode === "reject" && draft.evidenceImages.length
        ? JSON.stringify({
            evidence_images: draft.evidenceImages.map((image) => ({
              name: image.name,
              type: image.type,
              size: image.size,
              url: image.url || image.previewUrl,
              previewUrl: image.url ? undefined : image.previewUrl
            }))
          })
        : "";
    return {
      opportunity_id: item.id,
      salesperson_name: props.activeOperator,
      claim_result: draft.mode,
      claim_source: claimSourceFor(item),
      claim_daily_sales: draft.mode === "claim" ? Number(dailySales) : undefined,
      reject_reason: draft.mode === "reject" ? rejectReason : undefined,
      feedback_summary: "",
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
    await props.onSubmit(payload);
    setDrafts((current) => ({ ...current, [item.id]: draftForId() }));
  }

  async function submitComplete(items: Opportunity[]) {
    if (!props.activeOperator) {
      window.alert("请先在右上角选择当前运营");
      return;
    }
    const readyItems: { item: Opportunity; payload: unknown }[] = [];
    for (const item of items) {
      const payload = buildPayload(item, draftFor(item), false);
      if (payload) readyItems.push({ item, payload });
    }
    if (!readyItems.length) {
      window.alert("没有已填写完整的子 SKU");
      return;
    }
    await props.onSubmit(readyItems.map((entry) => entry.payload));
    setDrafts((current) => {
      const next = { ...current };
      for (const entry of readyItems) next[entry.item.id] = draftForId();
      return next;
    });
  }

  function addEvidence(itemId: string, images: EvidenceImage[]) {
    if (!images.length) return;
    const current = drafts[itemId] || draftForId();
    patchDraft(itemId, { evidenceImages: [...current.evidenceImages, ...images] });
  }

  function removeEvidence(itemId: string, imageId: string) {
    const current = drafts[itemId] || draftForId();
    patchDraft(itemId, { evidenceImages: current.evidenceImages.filter((image) => image.id !== imageId) });
  }

  return (
    <div className="claim-card-list">
      {!props.rows.length && <EmptySmall text="没有待认领任务或财根机会池记录。" />}
      {!!props.rows.length && (
        <div className="claim-bulkbar">
          <span>按主 SKU 分组展示；可逐个提交，也可一键提交已填写完整的子 SKU。</span>
          <button className="btn primary" onClick={() => void submitComplete(props.rows)}>
            <Send size={15} />
            一键提交全部已填写
          </button>
        </div>
      )}
      {claimGroups.map((group) => (
        <article className="group-item claim-main-card" key={group.key}>
          <div className="claim-group-head">
            <div>
              <div className="title-row">
                <h2>{group.main_sku}</h2>
                {statusPill(group.status)}
                <span className="tag">{group.items.length} 个子 SKU</span>
              </div>
              <p className="muted">{group.first.main_sku_name || group.first.keyword || "暂无商品名"}</p>
              <p className="muted">开品理由：{groupReason(group)}</p>
            </div>
            <button className="btn" onClick={() => void submitComplete(group.items)}>
              提交本组已填写
            </button>
          </div>
          <div className="claim-child-list">
            {group.items.map((item) => {
              const draft = draftFor(item);
              return (
                <section className="claim-child-card" key={item.id}>
                  <div className="sku-group claim-card-top">
                    <ProductThumb item={item} />
                    <div>
                      <div className="title-row">
                        <h3>{item.sub_sku}</h3>
                        {statusPill(item.current_status)}
                        <span className="tag">{claimTypeLabel(item)}</span>
                        {item.latest_claim_result && <span className="tag">上次：{item.latest_claim_result === "claim" ? "认领" : "不认领"}</span>}
                      </div>
                      <p>
                        <b>{item.sub_sku_name || item.keyword || "-"}</b>
                      </p>
                      <div className="tag-row">
                        <span className="tag">{item.site || item.country || "未填站点"}</span>
                        <span className="tag">{item.category_level1 || "未填类目"}</span>
                        <span className="tag">当前运营：{props.activeOperator || "未选择"}</span>
                      </div>
                      {item.current_status === "returned_for_supplement" && item.latest_review_comment && (
                        <div className="return-reason">主管退回原因：{item.latest_review_comment}</div>
                      )}
                      {item.current_status === "returned_for_supplement" && hasOperatorSubmission(item) && (
                        <OperatorSubmissionSummary item={item} title="上次不认领记录" />
                      )}
                    </div>
                  </div>
                  <div className="claim-inline">
                    <div className="mode-tabs">
                      <button className={draft.mode === "claim" ? "mode-tab active" : "mode-tab"} onClick={() => setMode(item.id, "claim")}>
                        <CheckCircle2 size={15} />
                        认领
                      </button>
                      <button className={draft.mode === "reject" ? "mode-tab active reject" : "mode-tab"} onClick={() => setMode(item.id, "reject")}>
                        <XCircle size={15} />
                        不认领
                      </button>
                    </div>
                    {draft.mode === "claim" ? (
                      <div className="claim-fields">
                        <label>
                          认领单销（日销）
                          <input
                            type="number"
                            min="0"
                            step="0.01"
                            value={draft.claimDailySales}
                            onChange={(event) => patchDraft(item.id, { claimDailySales: event.target.value })}
                            placeholder="备货数量 = 认领单销 × 30"
                          />
                        </label>
                      </div>
                    ) : (
                      <div className="claim-fields">
                        <label>
                          不认领原因
                          <textarea
                            rows={3}
                            value={draft.rejectReason}
                            onChange={(event) => patchDraft(item.id, { rejectReason: event.target.value })}
                            placeholder="填写不认领原因，可补充调研判断"
                          />
                        </label>
                        <EvidencePicker
                          images={draft.evidenceImages}
                          onFiles={(files) => void readEvidenceFiles(files, item.id).then((images) => addEvidence(item.id, images))}
                          onRemove={(imageId) => removeEvidence(item.id, imageId)}
                        />
                      </div>
                    )}
                    <div className="action-row">
                      <button className="btn primary" onClick={() => void submitItem(item)}>
                        <Send size={15} />
                        提交{draft.mode === "claim" ? "认领" : "不认领"}
                      </button>
                    </div>
                  </div>
                </section>
              );
            })}
          </div>
        </article>
      ))}
    </div>
  );
}

function draftForId(): ClaimDraft {
  return { mode: "claim", claimDailySales: "", rejectReason: "", evidenceImages: [] };
}

function EvidencePicker(props: {
  images: EvidenceImage[];
  onFiles: (files: FileList | File[]) => void;
  onRemove: (imageId: string) => void;
}) {
  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    if (event.target.files) props.onFiles(event.target.files);
    event.currentTarget.value = "";
  }
  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    props.onFiles(event.dataTransfer.files);
  }
  function handlePaste(event: ClipboardEvent<HTMLLabelElement>) {
    const files = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith("image/"));
    if (files.length) {
      event.preventDefault();
      props.onFiles(files);
    }
  }

  return (
    <div className="evidence-block">
      <label
        className="evidence-zone"
        tabIndex={0}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
        onPaste={handlePaste}
      >
        <Upload size={18} />
        <b>粘贴、拖拽或选择调研图片</b>
        <span>JPG / PNG / WebP / GIF，可多张</span>
        <input type="file" accept="image/*" multiple onChange={handleInput} />
      </label>
      {!!props.images.length && (
        <div className="evidence-list">
          {props.images.map((image) => (
            <div className="evidence-item" key={image.id}>
              <img src={image.previewUrl} alt={image.name} />
              <span>{image.name || "剪贴板图片"}</span>
              <button className="btn" onClick={() => props.onRemove(image.id)} title="删除图片">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewView(props: {
  rows: Opportunity[];
  target: Opportunity | null;
  setTarget: (value: Opportunity | null) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onBulkApprove: (items: Opportunity[]) => Promise<void>;
}) {
  const [reviewDecision, setReviewDecision] = useState("approved");
  const [selectedClaimReviewIds, setSelectedClaimReviewIds] = useState<string[]>([]);
  const targetIsNotClaim = props.target?.current_status === "claim_rejected";
  const targetIsClaim = props.target?.current_status === "claim_submitted";
  const claimReviewRows = props.rows.filter((item) => item.current_status === "claim_submitted");
  const selectedClaimReviewRows = claimReviewRows.filter((item) => selectedClaimReviewIds.includes(item.id));

  useEffect(() => {
    setReviewDecision(props.target?.current_status === "claim_rejected" ? "confirmed_not_claim" : "approved");
  }, [props.target?.id, props.target?.current_status]);

  useEffect(() => {
    setSelectedClaimReviewIds((current) => {
      const next = current.filter((id) => claimReviewRows.some((item) => item.id === id));
      return next.length === current.length ? current : next;
    });
  }, [props.rows]);

  function toggleClaimReview(item: Opportunity, checked: boolean) {
    setSelectedClaimReviewIds((current) => (checked ? Array.from(new Set([...current, item.id])) : current.filter((id) => id !== item.id)));
  }

  async function bulkApprove() {
    await props.onBulkApprove(selectedClaimReviewRows);
    setSelectedClaimReviewIds([]);
  }

  return (
    <div className="review-layout">
      <section className="group-list">
        {claimReviewRows.length > 0 && (
          <div className="claim-bulkbar">
            <label className="checkline">
              <input
                checked={selectedClaimReviewIds.length === claimReviewRows.length}
                onChange={(event) => setSelectedClaimReviewIds(event.target.checked ? claimReviewRows.map((item) => item.id) : [])}
                type="checkbox"
              />
              已选 {selectedClaimReviewIds.length} / {claimReviewRows.length} 个认领复核
            </label>
            <button className="btn primary" disabled={!selectedClaimReviewIds.length} onClick={bulkApprove}>
              <CheckCircle2 size={15} />
              批量通过认领
            </button>
          </div>
        )}
        {!props.rows.length && <EmptySmall text="没有待主管复核的认领或不认领任务。" />}
        {props.rows.map((item) => (
          <article className={`group-item compact${props.target?.id === item.id ? " active" : ""}`} key={item.id}>
            <div className="sku-group">
              {item.current_status === "claim_submitted" && (
                <input
                  aria-label={`选择 ${item.main_sku} 批量通过`}
                  checked={selectedClaimReviewIds.includes(item.id)}
                  className="card-check"
                  onChange={(event) => toggleClaimReview(item, event.target.checked)}
                  type="checkbox"
                />
              )}
              <ProductThumb item={item} />
              <div>
                <div className="title-row">
                  <h2>{item.main_sku}</h2>
                  {statusPill(item.current_status)}
                  <span className="tag">{item.current_status === "claim_submitted" ? "运营已认领" : "运营不认领"}</span>
                </div>
                <p>
                  <b>{item.sub_sku}</b> · {item.sub_sku_name || item.keyword || "-"}
                </p>
                <p className="muted">
                  {item.latest_claim_salesperson || "运营"}提交了{item.current_status === "claim_submitted" ? "认领" : "不认领"}，主管不代改运营填写内容。
                </p>
                {item.current_status === "claim_rejected" && item.latest_reject_reason && (
                  <p className="muted">不认领原因：{item.latest_reject_reason}</p>
                )}
              </div>
              <button className="btn primary" onClick={() => props.setTarget(item)}>
                复核
              </button>
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
              <input name="reviewer_name" required defaultValue="练玉君" />
            </label>
            {targetIsClaim && (
              <div className="review-fixed-result">
                <span>复核结果</span>
                <b>通过认领</b>
                <input type="hidden" name="review_status" value="approved" />
              </div>
            )}
            {targetIsNotClaim && (
              <label>
                复核结果
                <select name="review_status" value={reviewDecision} onChange={(event) => setReviewDecision(event.target.value)}>
                  <option value="confirmed_not_claim">确认不认领</option>
                  <option value="returned_for_supplement">退回补充</option>
                </select>
              </label>
            )}
            {targetIsNotClaim && reviewDecision === "returned_for_supplement" && (
              <label>
                退回原因
                <textarea name="review_comment" rows={4} required placeholder="说明需要运营补充什么内容" />
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
      {isNotClaim && (
        <div className="submission-row">
          <span>不认领原因</span>
          <p>{item.latest_reject_reason || "未填写"}</p>
        </div>
      )}
      {item.latest_feedback_summary && (
        <div className="submission-row">
          <span>运营说明</span>
          <p>{item.latest_feedback_summary}</p>
        </div>
      )}
      {isNotClaim && (
        <div className="submission-row">
          <span>图片附件</span>
          {evidenceImages.length ? (
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
          ) : (
            <p className="muted">未上传图片附件</p>
          )}
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

function StockView({ rows }: { rows: AvailableStockingItem[] }) {
  return (
    <div>
      <div className="action-row stock-actions">
        <button className="btn" onClick={() => void api.traceabilityExport()}>
          <Download size={15} />
          导出中央字段追溯表
        </button>
        <button className="btn primary" onClick={() => void api.availableStockingExport()}>
          <Download size={15} />
          导出海外仓备货申请表
        </button>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>操作状态</th>
              <th>时间</th>
              <th>备货类型</th>
              <th>选品数据源</th>
              <th>销售员</th>
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
            {!rows.length && (
              <tr>
                <td colSpan={16}>暂无可导出记录</td>
              </tr>
            )}
            {rows.map((row) => (
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
                <td>{row.claim_daily_sales}</td>
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

function Toolbar({
  activeView,
  assignSummary,
  onPreview,
  onAssign
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
  onAssign: () => void;
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
        <button className="btn primary" onClick={onAssign}>
          <WandSparkles size={15} />
          提交分配
        </button>
      </div>
    );
  }
  if (activeView === "pool") {
    return (
      <div className="toolbar">
        <div className="search">
          <Search size={16} />
          主 SKU / 子 SKU / 关键词 / 产品名 / 站点 / 类目 / 运营 / 状态
        </div>
        <span className="pill gray">状态优先</span>
        <span className="pill gray">50 条/页</span>
      </div>
    );
  }
  return null;
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
  const map = new Map<string, Opportunity[]>();
  for (const item of items) {
    const key = `${item.source_type || ""}|${item.main_sku}`;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(item);
  }
  return Array.from(map.entries()).map(([key, groupItems]) => ({
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
  if (role === "operator" && group.items.some(isOperatorClaimItem)) return "去认领";
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
  if (!note) return [];
  try {
    const parsed = JSON.parse(note) as { evidence_images?: unknown };
    if (!Array.isArray(parsed.evidence_images)) return [];
    return parsed.evidence_images
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((item) => ({
        name: typeof item.name === "string" && item.name ? item.name : "图片附件",
        type: typeof item.type === "string" ? item.type : "",
        size: typeof item.size === "number" ? item.size : 0,
        previewUrl: evidenceImageSrc(item)
      }));
  } catch {
    return [];
  }
}

function evidenceImageSrc(item: Record<string, unknown>) {
  const source = typeof item.url === "string" ? item.url : typeof item.previewUrl === "string" ? item.previewUrl : "";
  return source ? imageSrc(source) : undefined;
}

async function readEvidenceFiles(files: FileList | File[], opportunityId: string) {
  const imageFiles = Array.from(files).filter((file) => file.type.startsWith("image/"));
  return Promise.all(imageFiles.map((file) => readEvidenceFile(file, opportunityId)));
}

async function readEvidenceFile(file: File, opportunityId: string): Promise<EvidenceImage> {
  try {
    const uploaded = await api.uploadClaimEvidence(opportunityId, file);
    return {
      id: typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${file.name}`,
      name: uploaded.name || file.name || "clipboard-image.png",
      type: uploaded.type || file.type,
      size: uploaded.size || file.size,
      previewUrl: imageSrc(uploaded.url),
      url: uploaded.url
    };
  } catch {
    // ponytail: if upload is down, keep the workflow usable by storing the data URL in the claim note.
  }
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve({
        id: typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${file.name}`,
        name: file.name || "clipboard-image.png",
        type: file.type,
        size: file.size,
        previewUrl: String(reader.result || "")
      });
    };
    reader.readAsDataURL(file);
  });
}

function formatDate(value: string) {
  return value ? value.slice(0, 10) : "";
}

export default App;
