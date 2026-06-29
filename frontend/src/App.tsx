import {
  Alert,
  App as AntdApp,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  Radio,
  Select,
  Space,
  Statistic,
  Steps,
  Table,
  Tabs,
  Tag,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import type { MenuProps } from "antd";
import {
  CheckCircle2,
  ClipboardList,
  Database,
  FileDown,
  ListChecks,
  PackageCheck,
  RefreshCw,
  Settings,
  Upload,
  UserCheck,
  UserPlus
} from "lucide-react";
import type { Key } from "react";
import { useEffect, useMemo, useState } from "react";
import { api, AvailableStockingItem, NotificationLog, Opportunity, RoleMapping, Selection1ImportResponse, Task } from "./api";

const { Header, Content, Sider } = Layout;
const { Text, Title } = Typography;

type PageKey = "workbench" | "sourceImport" | "opportunities" | "assignments" | "claim" | "review" | "stocking" | "admin";

type AssignmentPreviewItem = {
  main_sku: string;
  sub_sku_count: number;
  suggested_assignee?: string | null;
};

type AssignmentRow = {
  main_sku: string;
  site?: string | null;
  sub_sku_count: number;
  status: string;
  opportunity_ids: string[];
};

type OpportunityGroupRow = {
  key: string;
  isGroup: boolean;
  main_sku: string;
  main_sku_name?: string | null;
  sub_sku?: string | null;
  sub_sku_name?: string | null;
  site?: string | null;
  category_level1?: string | null;
  keyword?: string | null;
  developer_name?: string | null;
  current_status: string;
  source_sheet?: string | null;
  source_row?: number | null;
  source_file?: string | null;
  sub_sku_count: number;
  opportunity_ids: string[];
  record?: Opportunity;
  children?: OpportunityGroupRow[];
};

const pageMeta: Record<PageKey, { title: string; subtitle: string }> = {
  workbench: { title: "工作台", subtitle: "待办、状态和异常入口" },
  sourceImport: { title: "源表导入", subtitle: "选品1 单表入池" },
  opportunities: { title: "新品机会池", subtitle: "主 SKU 分组、子 SKU 明细" },
  assignments: { title: "分配台", subtitle: "按主 SKU 组选择并确认分配" },
  claim: { title: "销售认领", subtitle: "认领、不认领和反馈提交" },
  review: { title: "主管审核", subtitle: "通过、驳回或退回补充" },
  stocking: { title: "可备货清单", subtitle: "审核通过后的运营导出清单" },
  admin: { title: "配置与日志", subtitle: "人员映射、通知日志和基础配置" }
};

const menuItems: MenuProps["items"] = [
  {
    type: "group",
    label: "工作台",
    children: [{ key: "workbench", icon: <ClipboardList size={16} />, label: "我的工作台" }]
  },
  {
    type: "group",
    label: "选品前段",
    children: [
      { key: "sourceImport", icon: <Upload size={16} />, label: "源表导入" },
      { key: "opportunities", icon: <Database size={16} />, label: "新品机会池" },
      { key: "assignments", icon: <UserPlus size={16} />, label: "分配台" },
      { key: "claim", icon: <UserCheck size={16} />, label: "销售认领" },
      { key: "review", icon: <CheckCircle2 size={16} />, label: "主管审核" },
      { key: "stocking", icon: <PackageCheck size={16} />, label: "可备货清单" }
    ]
  },
  {
    type: "group",
    label: "配置与日志",
    children: [{ key: "admin", icon: <Settings size={16} />, label: "配置与日志" }]
  }
];

const statusMeta: Record<string, { label: string; color: string }> = {
  pending_assignment: { label: "待分配", color: "default" },
  open_claim_pool: { label: "开放自领", color: "geekblue" },
  assigned: { label: "待认领", color: "blue" },
  claim_submitted: { label: "待审核", color: "gold" },
  claim_rejected: { label: "不认领", color: "orange" },
  ready_for_stocking: { label: "可备货", color: "green" },
  review_rejected: { label: "审核驳回", color: "red" },
  review_returned: { label: "退回补充", color: "purple" },
  mixed: { label: "多状态", color: "cyan" }
};

function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#166f73",
          borderRadius: 6,
          fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", Arial, sans-serif'
        },
        components: {
          Card: { borderRadiusLG: 8 },
          Layout: { bodyBg: "#eef2f7", headerBg: "#ffffff", siderBg: "#17202e" },
          Menu: { darkItemBg: "#17202e", darkSubMenuItemBg: "#17202e", darkItemSelectedBg: "#263246" },
          Table: { headerBg: "#f6f8fb" }
        }
      }}
    >
      <AntdApp>
        <WorkflowApp />
      </AntdApp>
    </ConfigProvider>
  );
}

function WorkflowApp() {
  const { message, modal } = AntdApp.useApp();
  const [activePage, setActivePage] = useState<PageKey>("workbench");
  const [healthStatus, setHealthStatus] = useState("checking");
  const [statusMessage, setStatusMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [availableStocking, setAvailableStocking] = useState<AvailableStockingItem[]>([]);
  const [notifications, setNotifications] = useState<NotificationLog[]>([]);
  const [roles, setRoles] = useState<RoleMapping[]>([]);
  const [lastImport, setLastImport] = useState<Selection1ImportResponse | null>(null);
  const [candidateNames, setCandidateNames] = useState<string[]>(["销售A", "销售B"]);
  const [assigneeName, setAssigneeName] = useState("销售A");
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<Key[]>([]);
  const [previewItems, setPreviewItems] = useState<AssignmentPreviewItem[]>([]);
  const [detailOpportunity, setDetailOpportunity] = useState<Opportunity | null>(null);
  const [claimOpportunity, setClaimOpportunity] = useState<Opportunity | null>(null);
  const [reviewOpportunity, setReviewOpportunity] = useState<Opportunity | null>(null);
  const [claimForm] = Form.useForm();
  const [reviewForm] = Form.useForm();
  const claimResult = Form.useWatch("claim_result", claimForm);

  const activeMeta = pageMeta[activePage];
  const groupedOpportunities = useMemo(() => groupOpportunities(opportunities), [opportunities]);
  const opportunityGroupRows = useMemo(() => groupedOpportunities.map(toGroupTableRow), [groupedOpportunities]);
  const selectedOpportunityIds = useMemo(() => {
    const selected = new Set(selectedGroupKeys.map(String));
    return groupedOpportunities
      .filter((group) => selected.has(group.main_sku))
      .flatMap((group) => group.items.map((item) => item.id));
  }, [groupedOpportunities, selectedGroupKeys]);
  const siteFilters = useMemo(() => uniqueFilters(opportunities.map((item) => item.site || item.country || "")), [opportunities]);
  const statusFilters = useMemo(
    () => Object.entries(statusMeta).map(([value, meta]) => ({ text: meta.label, value })),
    []
  );
  const pendingClaimRows = useMemo(
    () =>
      opportunities.filter((item) =>
        ["pending_assignment", "open_claim_pool", "assigned", "claim_rejected", "review_returned"].includes(item.current_status)
      ),
    [opportunities]
  );
  const pendingReviewRows = useMemo(() => opportunities.filter((item) => item.current_status === "claim_submitted"), [opportunities]);
  const stats = useMemo(() => buildStats(opportunities, tasks, availableStocking), [opportunities, tasks, availableStocking]);

  async function refresh() {
    setLoading(true);
    try {
      const failures: string[] = [];
      async function loadPart<T>(label: string, loader: () => Promise<T>, fallback: T): Promise<T> {
        try {
          return await loader();
        } catch {
          failures.push(label);
          return fallback;
        }
      }
      const [health, opportunityList, taskList, availableStockingList, noticeList, roleList] = await Promise.all([
        loadPart("健康检查", api.health, { status: "error", environment: "unknown" }),
        loadPart("机会池", api.opportunities, []),
        loadPart("待办", api.tasks, []),
        loadPart("可备货清单", api.availableStocking, []),
        loadPart("通知日志", api.notifications, []),
        loadPart("人员映射", api.roleMappings, [])
      ]);
      setHealthStatus(health.status);
      setOpportunities(opportunityList);
      setTasks(taskList);
      setAvailableStocking(availableStockingList);
      setNotifications(noticeList);
      setRoles(roleList);
      setStatusMessage(failures.length ? `部分数据未加载：${failures.join("、")}` : "已刷新");
    } catch (error) {
      setHealthStatus("error");
      setStatusMessage(error instanceof Error ? error.message : "请求失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function runAction(label: string, action: () => Promise<unknown>) {
    try {
      await action();
      message.success(`${label}完成`);
      await refresh();
    } catch (error) {
      message.error(error instanceof Error ? error.message : `${label}失败`);
    }
  }

  async function handleImportSelection1(values: { source_sheet: string }) {
    await runAction("导入选品1", async () => {
      const result = await api.importSelection1(values.source_sheet || "开发0623期");
      setLastImport(result);
    });
  }

  async function handlePreviewAssignments() {
    if (selectedOpportunityIds.length === 0) {
      message.warning("请选择主 SKU 组");
      return;
    }
    if (candidateNames.length === 0) {
      message.warning("请填写候选销售");
      return;
    }
    const result = await api.assignmentPreview(selectedOpportunityIds, candidateNames);
    setPreviewItems(result.items);
  }

  function handleConfirmAssignments() {
    if (selectedOpportunityIds.length === 0) {
      message.warning("请选择主 SKU 组");
      return;
    }
    const targetAssignee = assigneeName || candidateNames[0];
    modal.confirm({
      title: "确认分配",
      content: `将 ${selectedGroupKeys.length} 个主 SKU 组、${selectedOpportunityIds.length} 条子 SKU 记录分配给 ${targetAssignee}`,
      okText: "确认分配",
      cancelText: "取消",
      onOk: () => runAction("确认分配", () => api.assignmentConfirm(selectedOpportunityIds, targetAssignee))
    });
  }

  function openClaimDrawer(opportunity: Opportunity) {
    setClaimOpportunity(opportunity);
    claimForm.setFieldsValue({
      salesperson_name: "销售A",
      claim_result: "claim",
      claim_daily_sales: undefined,
      reject_reason: "",
      feedback_summary: ""
    });
  }

  async function handleClaimSubmit(values: {
    salesperson_name: string;
    claim_result: "claim" | "reject";
    claim_daily_sales?: number;
    reject_reason?: string;
    feedback_summary?: string;
  }) {
    if (!claimOpportunity) return;
    await runAction("销售认领", () =>
      api.claim({
        opportunity_id: claimOpportunity.id,
        salesperson_name: values.salesperson_name,
        claim_result: values.claim_result,
        claim_daily_sales: values.claim_result === "claim" ? values.claim_daily_sales : undefined,
        reject_reason: values.claim_result === "reject" ? values.reject_reason : undefined,
        feedback_summary: values.feedback_summary
      })
    );
    setClaimOpportunity(null);
  }

  function openReviewDrawer(opportunity: Opportunity) {
    setReviewOpportunity(opportunity);
    reviewForm.setFieldsValue({ reviewer_name: "主管A", review_status: "approved", review_comment: "" });
  }

  async function handleReviewSubmit(values: { reviewer_name: string; review_status: string; review_comment?: string }) {
    if (!reviewOpportunity) return;
    await runAction("主管审核", () =>
      api.review({
        opportunity_id: reviewOpportunity.id,
        reviewer_name: values.reviewer_name,
        review_status: values.review_status,
        review_comment: values.review_comment
      })
    );
    setReviewOpportunity(null);
  }

  async function handleRoleSubmit(values: { name: string; role: string; site?: string; group_name?: string }) {
    await runAction("人员映射", () => api.createRoleMapping(values));
  }

  const opportunityColumns = buildOpportunityColumns(siteFilters, statusFilters, setDetailOpportunity);
  const assignmentColumns = buildAssignmentColumns();
  const claimColumns = buildActionOpportunityColumns("认领", openClaimDrawer);
  const reviewColumns = buildActionOpportunityColumns("审核", openReviewDrawer);
  const taskColumns = buildTaskColumns();
  const stockingColumns = buildStockingColumns();
  const notificationColumns = buildNotificationColumns();
  const roleColumns = buildRoleColumns();

  return (
    <Layout className="app-shell">
      <Sider width={248} breakpoint="lg" collapsedWidth={0} className="app-sider">
        <div className="brand-block">
          <span className="brand-mark">新</span>
          <div>
            <Text className="brand-title">东南亚新品流程</Text>
            <Tag color={healthStatus === "ok" ? "green" : "red"}>{healthStatus}</Tag>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[activePage]}
          items={menuItems}
          onClick={({ key }) => setActivePage(key as PageKey)}
        />
      </Sider>
      <Layout>
        <Header className="app-header">
          <div>
            <Title level={3}>{activeMeta.title}</Title>
            <Text type="secondary">{activeMeta.subtitle}</Text>
          </div>
          <Space>
            <Text type="secondary">{statusMessage}</Text>
            <Button icon={<RefreshCw size={16} />} loading={loading} onClick={refresh}>
              刷新
            </Button>
          </Space>
        </Header>
        <Content className="app-content">
          {healthStatus === "error" && <Alert className="page-alert" type="error" title={statusMessage || "接口请求失败"} showIcon />}
          {activePage === "workbench" && (
            <WorkbenchPage stats={stats} tasks={tasks} columns={taskColumns} loading={loading} onOpenPage={setActivePage} />
          )}
          {activePage === "sourceImport" && (
            <SourceImportPage lastImport={lastImport} loading={loading} onImport={handleImportSelection1} />
          )}
          {activePage === "opportunities" && (
            <Card>
              <Table
                rowKey="key"
                loading={loading}
                columns={opportunityColumns}
                dataSource={opportunityGroupRows}
                expandable={{ defaultExpandAllRows: false }}
                pagination={{ pageSize: 12, showSizeChanger: true }}
                scroll={{ x: 1100 }}
              />
            </Card>
          )}
          {activePage === "assignments" && (
            <AssignmentPage
              rows={groupedOpportunities}
              columns={assignmentColumns}
              selectedKeys={selectedGroupKeys}
              onSelectedKeysChange={setSelectedGroupKeys}
              candidateNames={candidateNames}
              onCandidateNamesChange={setCandidateNames}
              assigneeName={assigneeName}
              onAssigneeNameChange={setAssigneeName}
              previewItems={previewItems}
              onPreview={handlePreviewAssignments}
              onConfirm={handleConfirmAssignments}
            />
          )}
          {activePage === "claim" && (
            <Card>
              <Table
                rowKey="id"
                loading={loading}
                columns={claimColumns}
                dataSource={pendingClaimRows}
                pagination={{ pageSize: 10, showSizeChanger: true }}
                scroll={{ x: 920 }}
              />
            </Card>
          )}
          {activePage === "review" && (
            <Card>
              <Table
                rowKey="id"
                loading={loading}
                columns={reviewColumns}
                dataSource={pendingReviewRows}
                pagination={{ pageSize: 10, showSizeChanger: true }}
                scroll={{ x: 920 }}
              />
            </Card>
          )}
          {activePage === "stocking" && (
            <Card
              title="可备货清单"
              extra={
                <Button icon={<FileDown size={16} />} type="primary" onClick={() => window.open(api.availableStockingExportUrl(), "_blank")}>
                  导出 Excel
                </Button>
              }
            >
              <Table
                rowKey={(record) => `${record.main_sku}-${record.sub_sku}`}
                loading={loading}
                columns={stockingColumns}
                dataSource={availableStocking}
                pagination={{ pageSize: 10, showSizeChanger: true }}
                scroll={{ x: 1100 }}
              />
            </Card>
          )}
          {activePage === "admin" && (
            <AdminPage
              roles={roles}
              notifications={notifications}
              roleColumns={roleColumns}
              notificationColumns={notificationColumns}
              onRoleSubmit={handleRoleSubmit}
            />
          )}
        </Content>
      </Layout>

      <OpportunityDetailDrawer opportunity={detailOpportunity} onClose={() => setDetailOpportunity(null)} />

      <Drawer title="销售认领" size="large" open={Boolean(claimOpportunity)} onClose={() => setClaimOpportunity(null)} destroyOnClose>
        {claimOpportunity && <OpportunitySummary opportunity={claimOpportunity} />}
        <Form form={claimForm} layout="vertical" onFinish={handleClaimSubmit}>
          <Form.Item name="salesperson_name" label="销售员" rules={[{ required: true, message: "请输入销售员" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="claim_result" label="认领结果" rules={[{ required: true, message: "请选择认领结果" }]}>
            <Radio.Group
              options={[
                { label: "认领", value: "claim" },
                { label: "不认领", value: "reject" }
              ]}
            />
          </Form.Item>
          {claimResult !== "reject" && (
            <Form.Item name="claim_daily_sales" label="认领单销" rules={[{ required: true, message: "请输入认领单销" }]}>
              <InputNumber min={0} precision={2} className="full-width" />
            </Form.Item>
          )}
          {claimResult === "reject" && (
            <Form.Item name="reject_reason" label="不认领原因" rules={[{ required: true, message: "请输入不认领原因" }]}>
              <Input.TextArea rows={4} />
            </Form.Item>
          )}
          <Form.Item name="feedback_summary" label="反馈说明">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              提交
            </Button>
            <Button onClick={() => setClaimOpportunity(null)}>取消</Button>
          </Space>
        </Form>
      </Drawer>

      <Drawer title="主管审核" size="large" open={Boolean(reviewOpportunity)} onClose={() => setReviewOpportunity(null)} destroyOnClose>
        {reviewOpportunity && <OpportunitySummary opportunity={reviewOpportunity} />}
        <Form form={reviewForm} layout="vertical" onFinish={handleReviewSubmit}>
          <Form.Item name="reviewer_name" label="审核人" rules={[{ required: true, message: "请输入审核人" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="review_status" label="审核结果" rules={[{ required: true, message: "请选择审核结果" }]}>
            <Radio.Group
              options={[
                { label: "通过", value: "approved" },
                { label: "驳回", value: "rejected" },
                { label: "退回补充", value: "returned" }
              ]}
            />
          </Form.Item>
          <Form.Item name="review_comment" label="审核意见">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit">
              提交审核
            </Button>
            <Button onClick={() => setReviewOpportunity(null)}>取消</Button>
          </Space>
        </Form>
      </Drawer>
    </Layout>
  );
}

function WorkbenchPage({
  stats,
  tasks,
  columns,
  loading,
  onOpenPage
}: {
  stats: ReturnType<typeof buildStats>;
  tasks: Task[];
  columns: ColumnsType<Task>;
  loading: boolean;
  onOpenPage: (page: PageKey) => void;
}) {
  return (
    <Space orientation="vertical" size={16} className="full-width">
      <div className="stat-grid">
        <Card onClick={() => onOpenPage("opportunities")}>
          <Statistic title="机会总数" value={stats.total} />
        </Card>
        <Card onClick={() => onOpenPage("assignments")}>
          <Statistic title="待分配/认领" value={stats.pendingFront} />
        </Card>
        <Card onClick={() => onOpenPage("review")}>
          <Statistic title="待审核" value={stats.pendingReview} />
        </Card>
        <Card onClick={() => onOpenPage("stocking")}>
          <Statistic title="可备货" value={stats.readyStocking} />
        </Card>
      </div>
      <Card>
        <Steps
          current={Math.min(stats.flowCurrent, 4)}
          items={[
            { title: "入池", content: `${stats.total} 条` },
            { title: "分配", content: `${stats.assigned} 条` },
            { title: "认领", content: `${stats.claimSubmitted} 条` },
            { title: "审核", content: `${stats.pendingReview} 条` },
            { title: "可备货", content: `${stats.readyStocking} 条` }
          ]}
        />
      </Card>
      <Card title="我的待办">
        <Table rowKey="id" loading={loading} columns={columns} dataSource={tasks} pagination={{ pageSize: 8 }} />
      </Card>
    </Space>
  );
}

function SourceImportPage({
  lastImport,
  loading,
  onImport
}: {
  lastImport: Selection1ImportResponse | null;
  loading: boolean;
  onImport: (values: { source_sheet: string }) => Promise<void>;
}) {
  return (
    <Space orientation="vertical" size={16} className="full-width">
      <Card title="选品1 导入">
        <Form layout="inline" initialValues={{ source_sheet: "开发0623期" }} onFinish={onImport}>
          <Form.Item name="source_sheet" label="Sheet" rules={[{ required: true, message: "请输入 sheet 名" }]}>
            <Input placeholder="开发0623期" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<Upload size={16} />} loading={loading}>
              导入
            </Button>
          </Form.Item>
        </Form>
      </Card>
      {lastImport && (
        <Card title="导入结果">
          <Descriptions column={{ xs: 1, sm: 2, lg: 4 }} bordered size="small">
            <Descriptions.Item label="Sheet">{lastImport.source_sheet}</Descriptions.Item>
            <Descriptions.Item label="入池">{lastImport.imported_count}</Descriptions.Item>
            <Descriptions.Item label="新增">{lastImport.created_count}</Descriptions.Item>
            <Descriptions.Item label="更新">{lastImport.updated_count}</Descriptions.Item>
            <Descriptions.Item label="跳过">{lastImport.skipped_count}</Descriptions.Item>
            <Descriptions.Item label="竞品记录">{lastImport.market_research_count}</Descriptions.Item>
            <Descriptions.Item label="预填认领">{lastImport.prefill_claim_count}</Descriptions.Item>
            <Descriptions.Item label="任务">{lastImport.task_count}</Descriptions.Item>
          </Descriptions>
        </Card>
      )}
    </Space>
  );
}

function AssignmentPage({
  rows,
  columns,
  selectedKeys,
  onSelectedKeysChange,
  candidateNames,
  onCandidateNamesChange,
  assigneeName,
  onAssigneeNameChange,
  previewItems,
  onPreview,
  onConfirm
}: {
  rows: { main_sku: string; items: Opportunity[] }[];
  columns: ColumnsType<AssignmentRow>;
  selectedKeys: Key[];
  onSelectedKeysChange: (keys: Key[]) => void;
  candidateNames: string[];
  onCandidateNamesChange: (value: string[]) => void;
  assigneeName: string;
  onAssigneeNameChange: (value: string) => void;
  previewItems: AssignmentPreviewItem[];
  onPreview: () => void;
  onConfirm: () => void;
}) {
  const tableRows: AssignmentRow[] = rows.map((group) => ({
    main_sku: group.main_sku,
    site: group.items[0]?.site || group.items[0]?.country,
    sub_sku_count: group.items.length,
    status: summarizeStatus(group.items),
    opportunity_ids: group.items.map((item) => item.id)
  }));
  const previewColumns: ColumnsType<AssignmentPreviewItem> = [
    { title: "主 SKU", dataIndex: "main_sku" },
    { title: "子 SKU 数", dataIndex: "sub_sku_count", width: 120 },
    { title: "建议责任人", dataIndex: "suggested_assignee", width: 160 }
  ];

  return (
    <div className="two-column">
      <Card title="选择主 SKU 组">
        <Space orientation="vertical" size={12} className="full-width">
          <Space wrap>
            <Select
              mode="tags"
              value={candidateNames}
              onChange={onCandidateNamesChange}
              className="candidate-select"
              placeholder="候选销售"
            />
            <Select
              value={assigneeName}
              onChange={onAssigneeNameChange}
              options={candidateNames.map((name) => ({ label: name, value: name }))}
              className="assignee-select"
              placeholder="确认分配人"
            />
            <Button icon={<ListChecks size={16} />} onClick={onPreview}>
              预览
            </Button>
            <Button type="primary" icon={<UserPlus size={16} />} onClick={onConfirm}>
              确认分配
            </Button>
          </Space>
          <Table
            rowKey="main_sku"
            rowSelection={{
              selectedRowKeys: selectedKeys,
              onChange: onSelectedKeysChange
            }}
            columns={columns}
            dataSource={tableRows}
            pagination={{ pageSize: 8 }}
          />
        </Space>
      </Card>
      <Card title="分配预览">
        <Table rowKey="main_sku" columns={previewColumns} dataSource={previewItems} pagination={false} />
      </Card>
    </div>
  );
}

function AdminPage({
  roles,
  notifications,
  roleColumns,
  notificationColumns,
  onRoleSubmit
}: {
  roles: RoleMapping[];
  notifications: NotificationLog[];
  roleColumns: ColumnsType<RoleMapping>;
  notificationColumns: ColumnsType<NotificationLog>;
  onRoleSubmit: (values: { name: string; role: string; site?: string; group_name?: string }) => Promise<void>;
}) {
  const [roleForm] = Form.useForm<{ name: string; role: string; site?: string; group_name?: string }>();

  async function submitRole(values: { name: string; role: string; site?: string; group_name?: string }) {
    await onRoleSubmit(values);
    roleForm.resetFields();
  }

  return (
    <Tabs
      items={[
        {
          key: "roles",
          label: "人员映射",
          children: (
            <div className="two-column">
              <Card>
                <Form form={roleForm} layout="vertical" initialValues={{ role: "sales" }} onFinish={submitRole}>
                  <Form.Item name="name" label="姓名" rules={[{ required: true, message: "请输入姓名" }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="role" label="角色" rules={[{ required: true, message: "请选择角色" }]}>
                    <Select
                      options={[
                        { label: "销售/运营", value: "sales" },
                        { label: "主管/运营负责人", value: "manager" },
                        { label: "开发", value: "developer" },
                        { label: "管理员", value: "admin" }
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="site" label="站点">
                    <Input />
                  </Form.Item>
                  <Form.Item name="group_name" label="小组">
                    <Input />
                  </Form.Item>
                  <Button type="primary" htmlType="submit">
                    保存
                  </Button>
                </Form>
              </Card>
              <Card>
                <Table rowKey="id" columns={roleColumns} dataSource={roles} pagination={{ pageSize: 8 }} />
              </Card>
            </div>
          )
        },
        {
          key: "notifications",
          label: "通知日志",
          children: (
            <Card>
              <Table rowKey="id" columns={notificationColumns} dataSource={notifications} pagination={{ pageSize: 10 }} />
            </Card>
          )
        }
      ]}
    />
  );
}

function OpportunityDetailDrawer({ opportunity, onClose }: { opportunity: Opportunity | null; onClose: () => void }) {
  return (
    <Drawer title="机会详情" size="large" open={Boolean(opportunity)} onClose={onClose}>
      {opportunity && (
        <Space orientation="vertical" size={16} className="full-width">
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="站点">{opportunity.site || opportunity.country || "-"}</Descriptions.Item>
            <Descriptions.Item label="状态">{statusTag(opportunity.current_status)}</Descriptions.Item>
            <Descriptions.Item label="主 SKU">{opportunity.main_sku}</Descriptions.Item>
            <Descriptions.Item label="子 SKU">{opportunity.sub_sku}</Descriptions.Item>
            <Descriptions.Item label="主 SKU 名称">{opportunity.main_sku_name || "-"}</Descriptions.Item>
            <Descriptions.Item label="子 SKU 名称">{opportunity.sub_sku_name || "-"}</Descriptions.Item>
            <Descriptions.Item label="一级类目">{opportunity.category_level1 || "-"}</Descriptions.Item>
            <Descriptions.Item label="关键词">{opportunity.keyword || "-"}</Descriptions.Item>
            <Descriptions.Item label="开发员">{opportunity.developer_name || "-"}</Descriptions.Item>
            <Descriptions.Item label="来源 Sheet">{opportunity.source_sheet || "-"}</Descriptions.Item>
            <Descriptions.Item label="来源行号">{opportunity.source_row || "-"}</Descriptions.Item>
            <Descriptions.Item label="来源文件">{opportunity.source_file || "-"}</Descriptions.Item>
          </Descriptions>
          <Card size="small" title="开品理由">
            <Text>{opportunity.reason || "-"}</Text>
          </Card>
        </Space>
      )}
    </Drawer>
  );
}

function OpportunitySummary({ opportunity }: { opportunity: Opportunity }) {
  return (
    <Card size="small" className="drawer-summary">
      <Descriptions size="small" column={1}>
        <Descriptions.Item label="主 SKU">{opportunity.main_sku}</Descriptions.Item>
        <Descriptions.Item label="子 SKU">{opportunity.sub_sku}</Descriptions.Item>
        <Descriptions.Item label="站点">{opportunity.site || opportunity.country || "-"}</Descriptions.Item>
        <Descriptions.Item label="状态">{statusTag(opportunity.current_status)}</Descriptions.Item>
      </Descriptions>
    </Card>
  );
}

function buildOpportunityColumns(
  siteFilters: { text: string; value: string }[],
  statusFilters: { text: string; value: string }[],
  onDetail: (item: Opportunity) => void
): ColumnsType<OpportunityGroupRow> {
  return [
    {
      title: "主/子 SKU",
      dataIndex: "main_sku",
      width: 210,
      fixed: "left",
      render: (_, row) =>
        row.isGroup ? (
          <Space orientation="vertical" size={0}>
            <Space>
              <Text strong>{row.main_sku}</Text>
              <Tag>{row.sub_sku_count} 子 SKU</Tag>
            </Space>
            <Text type="secondary">{row.main_sku_name || "-"}</Text>
          </Space>
        ) : (
          <Space orientation="vertical" size={0}>
            <Text>{row.sub_sku}</Text>
            <Text type="secondary">{row.sub_sku_name || "-"}</Text>
          </Space>
        )
    },
    { title: "站点", dataIndex: "site", width: 100, filters: siteFilters, onFilter: (value, row) => row.site === value },
    { title: "类目", dataIndex: "category_level1", width: 130 },
    { title: "关键词", dataIndex: "keyword", width: 180 },
    { title: "开发员", dataIndex: "developer_name", width: 110 },
    {
      title: "状态",
      dataIndex: "current_status",
      width: 120,
      filters: statusFilters,
      onFilter: (value, row) => row.current_status === value,
      render: (value) => statusTag(value)
    },
    {
      title: "来源",
      width: 180,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text>{row.source_sheet || "-"}</Text>
          <Text type="secondary">{row.source_row ? `行 ${row.source_row}` : "-"}</Text>
        </Space>
      )
    },
    {
      title: "操作",
      width: 100,
      fixed: "right",
      render: (_, row) => {
        const item = row.record || row.children?.[0]?.record;
        return (
          <Button size="small" disabled={!item} onClick={() => item && onDetail(item)}>
            详情
          </Button>
        );
      }
    }
  ];
}

function buildAssignmentColumns(): ColumnsType<AssignmentRow> {
  return [
    { title: "主 SKU", dataIndex: "main_sku" },
    { title: "站点", dataIndex: "site", width: 100 },
    { title: "子 SKU 数", dataIndex: "sub_sku_count", width: 120 },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => statusTag(value) }
  ];
}

function buildActionOpportunityColumns(actionLabel: string, onAction: (item: Opportunity) => void): ColumnsType<Opportunity> {
  return [
    { title: "站点", dataIndex: "site", width: 90, render: (_, row) => row.site || row.country || "-" },
    {
      title: "主 SKU / 子 SKU",
      width: 220,
      render: (_, row) => (
        <Space orientation="vertical" size={0}>
          <Text strong>{row.main_sku}</Text>
          <Text type="secondary">{row.sub_sku}</Text>
        </Space>
      )
    },
    { title: "关键词", dataIndex: "keyword", width: 180 },
    { title: "开发员", dataIndex: "developer_name", width: 110 },
    { title: "状态", dataIndex: "current_status", width: 120, render: (value) => statusTag(value) },
    {
      title: "操作",
      width: 100,
      fixed: "right",
      render: (_, row) => (
        <Button type="primary" size="small" onClick={() => onAction(row)}>
          {actionLabel}
        </Button>
      )
    }
  ];
}

function buildTaskColumns(): ColumnsType<Task> {
  return [
    { title: "节点", dataIndex: "node_code", width: 140 },
    { title: "任务类型", dataIndex: "task_type", width: 160, render: (value) => taskTypeTag(value) },
    { title: "责任人", dataIndex: "assignee_name", width: 120, render: (value) => value || "-" },
    { title: "角色", dataIndex: "assignee_role", width: 120, render: (value) => value || "-" },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <Tag color={value === "pending" ? "gold" : "green"}>{value}</Tag> },
    { title: "截止时间", dataIndex: "deadline_at", render: (value) => value || "-" }
  ];
}

function buildStockingColumns(): ColumnsType<AvailableStockingItem> {
  return [
    { title: "销售员", dataIndex: "salesperson_name", width: 120, render: (value) => value || "-" },
    { title: "主 SKU", dataIndex: "main_sku", width: 140 },
    { title: "子 SKU", dataIndex: "sub_sku", width: 140 },
    { title: "站点", dataIndex: "site", width: 90, render: (value) => value || "-" },
    { title: "认领单销", dataIndex: "claim_daily_sales", width: 120 },
    { title: "备货量", dataIndex: "quantity", width: 120 },
    { title: "选品数据源", dataIndex: "selection_source", width: 220 },
    { title: "操作状态", dataIndex: "operation_status", width: 120, render: (value) => <Tag>{value}</Tag> },
    { title: "开品邮件", dataIndex: "launch_email_status", width: 120, render: (value) => value || "-" }
  ];
}

function buildNotificationColumns(): ColumnsType<NotificationLog> {
  return [
    { title: "接收人", dataIndex: "receiver_name", width: 120, render: (value) => value || "-" },
    { title: "渠道", dataIndex: "channel", width: 120 },
    { title: "标题", dataIndex: "message_title" },
    { title: "状态", dataIndex: "send_status", width: 120, render: (value) => <Tag>{value}</Tag> },
    { title: "去重键", dataIndex: "dedupe_key", width: 240 }
  ];
}

function buildRoleColumns(): ColumnsType<RoleMapping> {
  return [
    { title: "姓名", dataIndex: "name", width: 120 },
    { title: "角色", dataIndex: "role", width: 140, render: (value) => <Tag color="blue">{value}</Tag> },
    { title: "小组", dataIndex: "group_name", render: (value) => value || "-" },
    { title: "站点", dataIndex: "site", width: 100, render: (value) => value || "-" },
    { title: "状态", dataIndex: "enabled", width: 100, render: (value) => <Tag color={value ? "green" : "red"}>{value ? "启用" : "停用"}</Tag> }
  ];
}

function groupOpportunities(items: Opportunity[]) {
  const map = new Map<string, Opportunity[]>();
  for (const item of items) {
    if (!map.has(item.main_sku)) {
      map.set(item.main_sku, []);
    }
    map.get(item.main_sku)!.push(item);
  }
  return Array.from(map.entries()).map(([main_sku, groupItems]) => ({ main_sku, items: groupItems }));
}

function toGroupTableRow(group: { main_sku: string; items: Opportunity[] }): OpportunityGroupRow {
  const first = group.items[0];
  return {
    key: group.main_sku,
    isGroup: true,
    main_sku: group.main_sku,
    main_sku_name: first?.main_sku_name,
    site: first?.site || first?.country,
    category_level1: first?.category_level1,
    keyword: first?.keyword,
    developer_name: first?.developer_name,
    current_status: summarizeStatus(group.items),
    source_sheet: first?.source_sheet,
    source_file: first?.source_file,
    sub_sku_count: group.items.length,
    opportunity_ids: group.items.map((item) => item.id),
    children: group.items.map((item) => ({
      key: item.id,
      isGroup: false,
      main_sku: item.main_sku,
      main_sku_name: item.main_sku_name,
      sub_sku: item.sub_sku,
      sub_sku_name: item.sub_sku_name,
      site: item.site || item.country,
      category_level1: item.category_level1,
      keyword: item.keyword,
      developer_name: item.developer_name,
      current_status: item.current_status,
      source_sheet: item.source_sheet,
      source_file: item.source_file,
      source_row: item.source_row,
      sub_sku_count: 1,
      opportunity_ids: [item.id],
      record: item
    }))
  };
}

function summarizeStatus(items: Opportunity[]) {
  const statuses = new Set(items.map((item) => item.current_status));
  return statuses.size === 1 ? items[0].current_status : "mixed";
}

function statusTag(status: string) {
  const meta = statusMeta[status] || { label: status, color: "default" };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

function taskTypeTag(type: string) {
  const labelMap: Record<string, string> = {
    sales_claim: "销售认领",
    manager_review: "主管审核"
  };
  return <Tag color={type === "manager_review" ? "gold" : "blue"}>{labelMap[type] || type}</Tag>;
}

function uniqueFilters(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).map((value) => ({ text: value, value }));
}

function buildStats(opportunities: Opportunity[], tasks: Task[], availableStocking: AvailableStockingItem[]) {
  const byStatus = opportunities.reduce<Record<string, number>>((acc, item) => {
    acc[item.current_status] = (acc[item.current_status] || 0) + 1;
    return acc;
  }, {});
  const pendingFront = (byStatus.pending_assignment || 0) + (byStatus.open_claim_pool || 0) + (byStatus.assigned || 0);
  const claimSubmitted = byStatus.claim_submitted || 0;
  const readyStocking = availableStocking.length;
  const pendingReview = tasks.filter((task) => task.task_type === "manager_review").length || claimSubmitted;
  const assigned = byStatus.assigned || 0;
  const flowCurrent = readyStocking > 0 ? 4 : pendingReview > 0 ? 3 : claimSubmitted > 0 ? 2 : assigned > 0 ? 1 : 0;
  return {
    total: opportunities.length,
    pendingFront,
    assigned,
    claimSubmitted,
    pendingReview,
    readyStocking,
    flowCurrent
  };
}

export default App;
