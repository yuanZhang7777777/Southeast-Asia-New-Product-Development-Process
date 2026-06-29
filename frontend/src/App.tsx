import {
  BarChart3,
  Bell,
  CheckCircle2,
  ClipboardList,
  PackageCheck,
  RefreshCw,
  Send,
  Settings,
  Truck,
  Upload,
  UserPlus
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, NotificationLog, Opportunity, RoleMapping, StockingRequest, Task } from "./api";

type TabKey = "tasks" | "opportunities" | "assignments" | "claimReview" | "stocking" | "arrivalSummary" | "admin";

const tabs: { key: TabKey; label: string; icon: typeof ClipboardList }[] = [
  { key: "tasks", label: "我的待办", icon: ClipboardList },
  { key: "opportunities", label: "新品机会池", icon: Upload },
  { key: "assignments", label: "分配台", icon: UserPlus },
  { key: "claimReview", label: "认领审核", icon: CheckCircle2 },
  { key: "stocking", label: "备货草稿", icon: PackageCheck },
  { key: "arrivalSummary", label: "到货总结", icon: Truck },
  { key: "admin", label: "管理后台", icon: Settings }
];

const sampleItems = [
  {
    source_type: "ph_site_sheet",
    source_file: "东南亚海外仓新品表-PH.xlsx",
    source_sheet: "新品",
    source_row: 2,
    country: "PH",
    site: "PH",
    main_sku: "MAIN-DEMO-001",
    sub_sku: "SUB-DEMO-001",
    keyword: "storage rack",
    snapshot: { A: "MAIN-DEMO-001", B: "SUB-DEMO-001" }
  },
  {
    source_type: "ph_site_sheet",
    source_file: "东南亚海外仓新品表-PH.xlsx",
    source_sheet: "新品",
    source_row: 3,
    country: "PH",
    site: "PH",
    main_sku: "MAIN-DEMO-001",
    sub_sku: "SUB-DEMO-002",
    keyword: "storage rack",
    snapshot: { A: "MAIN-DEMO-001", B: "SUB-DEMO-002" }
  }
];

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>("tasks");
  const [status, setStatus] = useState("checking");
  const [message, setMessage] = useState("");
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [stocking, setStocking] = useState<StockingRequest[]>([]);
  const [notifications, setNotifications] = useState<NotificationLog[]>([]);
  const [roles, setRoles] = useState<RoleMapping[]>([]);
  const [assigneeFilter, setAssigneeFilter] = useState("");
  const [candidates, setCandidates] = useState("销售A,销售B");
  const [preview, setPreview] = useState<{ main_sku: string; sub_sku_count: number; suggested_assignee?: string | null }[]>([]);
  const [assignee, setAssignee] = useState("销售A");
  const [selectedOpportunityId, setSelectedOpportunityId] = useState("");
  const [salesperson, setSalesperson] = useState("销售A");
  const [dailySales, setDailySales] = useState("2");
  const [reviewer, setReviewer] = useState("主管A");
  const [roleName, setRoleName] = useState("");
  const [roleValue, setRoleValue] = useState("sales");

  const opportunityIds = useMemo(() => opportunities.map((item) => item.id), [opportunities]);
  const currentOpportunityId = selectedOpportunityId || opportunities[0]?.id || "";

  async function refresh() {
    try {
      const [health, opportunityList, taskList, stockingList, noticeList, roleList] = await Promise.all([
        api.health(),
        api.opportunities(),
        api.tasks(assigneeFilter),
        api.stocking(),
        api.notifications(),
        api.roleMappings()
      ]);
      setStatus(health.status);
      setOpportunities(opportunityList);
      setTasks(taskList);
      setStocking(stockingList);
      setNotifications(noticeList);
      setRoles(roleList);
      setMessage("已刷新");
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "请求失败");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function runAction(label: string, action: () => Promise<unknown>) {
    try {
      await action();
      setMessage(`${label}完成`);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${label}失败`);
    }
  }

  function candidateList() {
    return candidates
      .split(/[,\n，]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  async function submitRole(event: FormEvent) {
    event.preventDefault();
    if (!roleName.trim()) return;
    await runAction("人员映射", () => api.createRoleMapping({ name: roleName.trim(), role: roleValue }));
    setRoleName("");
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">新</span>
          <div>
            <strong>东南亚新品流程</strong>
            <span>{status}</span>
          </div>
        </div>
        <nav className="nav">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button key={tab.key} className={activeTab === tab.key ? "active" : ""} onClick={() => setActiveTab(tab.key)}>
                <Icon size={18} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>{tabs.find((tab) => tab.key === activeTab)?.label}</h1>
            <p>{message || "MVP 闭环工作台"}</p>
          </div>
          <button className="icon-button" title="刷新" onClick={refresh}>
            <RefreshCw size={18} />
          </button>
        </header>

        {activeTab === "tasks" && (
          <section className="panel">
            <div className="toolbar">
              <input value={assigneeFilter} onChange={(event) => setAssigneeFilter(event.target.value)} placeholder="责任人" />
              <button onClick={refresh}>
                <RefreshCw size={16} />
                刷新
              </button>
            </div>
            <DataTable
              columns={["节点", "类型", "责任人", "角色", "状态", "截止时间"]}
              rows={tasks.map((task) => [task.node_code, task.task_type, task.assignee_name || "-", task.assignee_role || "-", task.status, task.deadline_at || "-"])}
            />
          </section>
        )}

        {activeTab === "opportunities" && (
          <section className="panel">
            <div className="toolbar">
              <button onClick={() => runAction("导入样例", () => api.importOpportunities(sampleItems))}>
                <Upload size={16} />
                导入样例
              </button>
            </div>
            <OpportunityTable opportunities={opportunities} onPick={setSelectedOpportunityId} />
          </section>
        )}

        {activeTab === "assignments" && (
          <section className="grid">
            <div className="panel">
              <h2>分配预览</h2>
              <label>
                候选销售
                <textarea value={candidates} onChange={(event) => setCandidates(event.target.value)} />
              </label>
              <button onClick={() => runAction("预览", async () => setPreview((await api.assignmentPreview(opportunityIds, candidateList())).items))}>
                <ClipboardList size={16} />
                预览
              </button>
              <DataTable columns={["主 SKU", "子 SKU 数", "建议责任人"]} rows={preview.map((item) => [item.main_sku, item.sub_sku_count, item.suggested_assignee || "-"])} />
            </div>
            <div className="panel">
              <h2>确认分配</h2>
              <label>
                责任人
                <input value={assignee} onChange={(event) => setAssignee(event.target.value)} />
              </label>
              <button onClick={() => runAction("确认分配", () => api.assignmentConfirm(opportunityIds, assignee))}>
                <UserPlus size={16} />
                确认
              </button>
            </div>
          </section>
        )}

        {activeTab === "claimReview" && (
          <section className="grid">
            <div className="panel">
              <h2>销售认领</h2>
              <OpportunitySelect opportunities={opportunities} value={currentOpportunityId} onChange={setSelectedOpportunityId} />
              <label>
                销售
                <input value={salesperson} onChange={(event) => setSalesperson(event.target.value)} />
              </label>
              <label>
                认领单销
                <input type="number" min="0" value={dailySales} onChange={(event) => setDailySales(event.target.value)} />
              </label>
              <button
                onClick={() =>
                  runAction("认领", () =>
                    api.claim({
                      opportunity_id: currentOpportunityId,
                      salesperson_name: salesperson,
                      claim_result: "claim",
                      claim_daily_sales: Number(dailySales),
                      feedback_summary: "MVP 工作台提交"
                    })
                  )
                }
              >
                <Send size={16} />
                提交
              </button>
            </div>
            <div className="panel">
              <h2>主管审核</h2>
              <OpportunitySelect opportunities={opportunities} value={currentOpportunityId} onChange={setSelectedOpportunityId} />
              <label>
                主管
                <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} />
              </label>
              <button
                onClick={() =>
                  runAction("审核", () =>
                    api.review({
                      opportunity_id: currentOpportunityId,
                      reviewer_name: reviewer,
                      review_status: "approved",
                      review_comment: "MVP 工作台通过"
                    })
                  )
                }
              >
                <CheckCircle2 size={16} />
                通过
              </button>
            </div>
          </section>
        )}

        {activeTab === "stocking" && (
          <section className="panel">
            <DataTable
              columns={["主 SKU", "子 SKU", "销售", "单销", "建议数量", "国家", "仓库", "状态"]}
              rows={stocking.map((item) => [
                item.main_sku || "-",
                item.sub_sku || "-",
                item.salesperson_name || "-",
                item.daily_sales ?? "-",
                item.quantity,
                item.country || "-",
                item.warehouse || "-",
                item.status
              ])}
            />
          </section>
        )}

        {activeTab === "arrivalSummary" && (
          <section className="grid">
            <div className="panel">
              <h2>到货记录</h2>
              <OpportunitySelect opportunities={opportunities} value={currentOpportunityId} onChange={setSelectedOpportunityId} />
              <button
                onClick={() =>
                  runAction("到货记录", () =>
                    api.arrival({ opportunity_id: currentOpportunityId, warehouse: "PH 海外仓", arrived_quantity: 60, listing_status: "pending" })
                  )
                }
              >
                <Truck size={16} />
                记录
              </button>
            </div>
            <div className="panel">
              <h2>四周总结</h2>
              <OpportunitySelect opportunities={opportunities} value={currentOpportunityId} onChange={setSelectedOpportunityId} />
              <button
                onClick={() =>
                  runAction("四周总结", () =>
                    api.summary({ opportunity_id: currentOpportunityId, summary_user: reviewer, achieved: true, conclusion: "继续观察", next_action: "保留补货入口" })
                  )
                }
              >
                <BarChart3 size={16} />
                保存
              </button>
            </div>
            <div className="panel wide">
              <h2>通知日志</h2>
              <button
                onClick={() =>
                  runAction("测试通知", () =>
                    api.notify({ receiver_name: salesperson, title: "新品流程测试通知", dedupe_key: `test:${currentOpportunityId || "none"}`, channel: "work_notice" })
                  )
                }
              >
                <Bell size={16} />
                测试
              </button>
              <DataTable columns={["接收人", "渠道", "标题", "状态", "去重键"]} rows={notifications.map((item) => [item.receiver_name || "-", item.channel, item.message_title, item.send_status, item.dedupe_key])} />
            </div>
          </section>
        )}

        {activeTab === "admin" && (
          <section className="grid">
            <form className="panel" onSubmit={submitRole}>
              <h2>人员映射</h2>
              <label>
                姓名
                <input value={roleName} onChange={(event) => setRoleName(event.target.value)} />
              </label>
              <label>
                角色
                <select value={roleValue} onChange={(event) => setRoleValue(event.target.value)}>
                  <option value="sales">sales</option>
                  <option value="manager">manager</option>
                  <option value="developer">developer</option>
                  <option value="ops">ops</option>
                </select>
              </label>
              <button type="submit">
                <UserPlus size={16} />
                保存
              </button>
            </form>
            <div className="panel">
              <h2>角色列表</h2>
              <DataTable columns={["姓名", "角色", "小组", "站点", "状态"]} rows={roles.map((role) => [role.name, role.role, role.group_name || "-", role.site || "-", role.enabled ? "启用" : "停用"])} />
            </div>
          </section>
        )}
      </section>
    </main>
  );
}

function OpportunitySelect({ opportunities, value, onChange }: { opportunities: Opportunity[]; value: string; onChange: (value: string) => void }) {
  return (
    <label>
      新品机会
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {opportunities.map((item) => (
          <option key={item.id} value={item.id}>
            {item.main_sku} / {item.sub_sku}
          </option>
        ))}
      </select>
    </label>
  );
}

function OpportunityTable({ opportunities, onPick }: { opportunities: Opportunity[]; onPick: (id: string) => void }) {
  return (
    <DataTable
      columns={["站点", "主 SKU", "子 SKU", "关键词", "状态", "来源", "行号"]}
      rows={opportunities.map((item) => [
        item.site || item.country || "-",
        item.main_sku,
        item.sub_sku,
        item.keyword || "-",
        item.current_status,
        item.source_file || "-",
        item.source_row || "-"
      ])}
      onRowClick={(index) => onPick(opportunities[index].id)}
    />
  );
}

function DataTable({ columns, rows, onRowClick }: { columns: string[]; rows: (string | number)[][]; onRowClick?: (index: number) => void }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="empty">
                暂无数据
              </td>
            </tr>
          ) : (
            rows.map((row, rowIndex) => (
              <tr key={rowIndex} onClick={() => onRowClick?.(rowIndex)}>
                {row.map((cell, cellIndex) => (
                  <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default App;
