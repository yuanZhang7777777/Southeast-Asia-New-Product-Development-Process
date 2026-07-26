import { Download, RefreshCw, ShieldCheck, Users, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  AdminPasswordReset,
  AdminUser,
  api,
  FeatureSwitch,
  FineBIPullResult,
  ImportBatchPage,
  ImportBatchSummary,
  RoleMapping
} from "./api";
import { defaultFineBIWeekLabel, validateFineBIWeekLabel } from "./finebiPull";
import {
  ADMIN_SECTIONS,
  AdminSectionKey,
  adminBatchPageCount,
  BATCH_SOURCE_TYPE_OPTIONS,
  BATCH_STATUS_OPTIONS,
  batchSourceTypeLabel,
  batchStatusMeta,
  featureSwitchMeta,
  mappingsForUser,
  roleLabel,
  roleOptions,
  validateResetPasswordInput
} from "./adminConsole";

const EMPTY_BATCH_PAGE: ImportBatchPage = { total: 0, page: 1, page_size: 20, items: [] };

type BatchQuery = { page: number; page_size: number; source_type: string; status: string };

function readableError(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

function formatBatchTime(value?: string | null) {
  return value ? value.replace("T", " ").slice(0, 16) : "-";
}

export function AdminConsoleView(props: { onStatus: (message: string) => void }) {
  const { onStatus } = props;
  const [section, setSection] = useState<AdminSectionKey>("users");
  const [loading, setLoading] = useState(false);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [roleMappings, setRoleMappings] = useState<RoleMapping[]>([]);
  const [switches, setSwitches] = useState<FeatureSwitch[]>([]);
  const [batchPage, setBatchPage] = useState<ImportBatchPage>(EMPTY_BATCH_PAGE);
  const [batchQuery, setBatchQuery] = useState<BatchQuery>({ page: 1, page_size: 20, source_type: "", status: "" });
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetInput, setResetInput] = useState("");
  const [resetError, setResetError] = useState("");
  const [resetResult, setResetResult] = useState<{ userName: string; result: AdminPasswordReset } | null>(null);
  const [batchToggleTarget, setBatchToggleTarget] = useState<{ batch: ImportBatchSummary; disabled: boolean } | null>(null);
  const [batchToggleReason, setBatchToggleReason] = useState("");
  const [finebiWeekLabel, setFinebiWeekLabel] = useState(() => defaultFineBIWeekLabel());
  const [finebiRunning, setFinebiRunning] = useState(false);
  const [finebiResult, setFinebiResult] = useState<FineBIPullResult | null>(null);
  const [finebiError, setFinebiError] = useState("");

  const loadBase = useCallback(async () => {
    setLoading(true);
    try {
      const [userList, mappingList, switchList] = await Promise.all([
        api.adminUsers(),
        api.roleMappings(),
        api.adminFeatureSwitches()
      ]);
      setUsers(userList);
      setRoleMappings(mappingList);
      setSwitches(switchList);
    } catch (error) {
      onStatus(readableError(error, "超管后台数据加载失败"));
    } finally {
      setLoading(false);
    }
  }, [onStatus]);

  const loadBatches = useCallback(async () => {
    setLoading(true);
    try {
      setBatchPage(await api.adminImportBatches(batchQuery));
    } catch (error) {
      onStatus(readableError(error, "导入批次加载失败"));
    } finally {
      setLoading(false);
    }
  }, [batchQuery, onStatus]);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  useEffect(() => {
    void loadBatches();
  }, [loadBatches]);

  async function toggleUser(user: AdminUser) {
    const enabled = !user.enabled;
    if (!enabled && !window.confirm(`确认停用用户「${user.name}」？停用后该账号无法登录，历史数据保留。`)) return;
    try {
      await api.adminSetUserEnabled(user.id, enabled);
      setUsers(await api.adminUsers());
      onStatus(enabled ? `已启用用户 ${user.name}` : `已停用用户 ${user.name}`);
    } catch (error) {
      onStatus(readableError(error, "用户状态更新失败"));
    }
  }

  async function changeMappingRole(mapping: RoleMapping, role: string) {
    try {
      const updated = await api.updateRoleMapping(mapping.id, { role });
      setRoleMappings((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      onStatus(`已将 ${mapping.name} 的角色调整为${roleLabel(role)}`);
    } catch (error) {
      onStatus(readableError(error, "角色调整失败"));
    }
  }

  function openReset(user: AdminUser) {
    setResetTarget(user);
    setResetInput("");
    setResetError("");
  }

  async function submitReset() {
    if (!resetTarget) return;
    const validation = validateResetPasswordInput(resetInput);
    if (validation) {
      setResetError(validation);
      return;
    }
    const targetName = resetTarget.name;
    try {
      const password = resetInput.trim();
      const result = await api.adminResetUserPassword(resetTarget.id, password || undefined);
      setResetTarget(null);
      setResetResult({ userName: targetName, result });
      setUsers(await api.adminUsers());
      onStatus(`已重置 ${targetName} 的登录密码`);
    } catch (error) {
      setResetError(readableError(error, "重置密码失败"));
    }
  }

  function openBatchToggle(batch: ImportBatchSummary, disabled: boolean) {
    setBatchToggleTarget({ batch, disabled });
    setBatchToggleReason("");
  }

  async function submitBatchToggle() {
    if (!batchToggleTarget) return;
    const { batch, disabled } = batchToggleTarget;
    try {
      await api.adminDisableImportBatch(batch.id, { disabled, reason: batchToggleReason.trim() || null });
      setBatchToggleTarget(null);
      await loadBatches();
      onStatus(disabled ? "已停用导入批次" : "已恢复导入批次");
    } catch (error) {
      onStatus(readableError(error, disabled ? "停用导入批次失败" : "恢复导入批次失败"));
    }
  }

  async function submitFineBIPull() {
    const label = finebiWeekLabel.trim();
    const validation = validateFineBIWeekLabel(label);
    if (validation) {
      setFinebiError(validation);
      return;
    }
    setFinebiRunning(true);
    setFinebiError("");
    setFinebiResult(null);
    try {
      const result = await api.adminFineBIPull(label);
      setFinebiResult(result);
      onStatus(`FineBI ${result.week_label} 拉取并入库完成`);
    } catch (error) {
      setFinebiError(readableError(error, "FineBI 拉取失败"));
    } finally {
      setFinebiRunning(false);
    }
  }

  const batchPages = adminBatchPageCount(batchPage.total, batchQuery.page_size);

  return (
    <div className="admin-console">
      <div className="admin-section-tabs">
        {ADMIN_SECTIONS.map((item) => (
          <button
            className={`btn small ${section === item.key ? "primary" : ""}`}
            key={item.key}
            type="button"
            onClick={() => setSection(item.key)}
          >
            {item.label}
          </button>
        ))}
        <button
          className="btn small"
          type="button"
          disabled={loading}
          onClick={() => {
            void loadBase();
            void loadBatches();
          }}
        >
          <RefreshCw size={14} />
          刷新
        </button>
      </div>

      {section === "users" && (
        <section className="info">
          <h3>
            <Users size={16} />
            用户管理
          </h3>
          <p className="muted">不提供删除用户：请用停用代替，停用后账号立即无法登录，历史数据全部保留。</p>
          {!users.length ? (
            <p className="muted">暂无用户。</p>
          ) : (
            <div className="admin-table">
              <div className="admin-user-row head">
                <span>姓名</span>
                <span>钉钉绑定</span>
                <span>登录密码</span>
                <span>角色</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {users.map((user) => {
                const mappings = mappingsForUser(user.name, roleMappings);
                return (
                  <div className="admin-user-row" key={user.id}>
                    <span>{user.name}</span>
                    <span>{user.dingtalk_user_id ? "已绑定" : "未绑定"}</span>
                    <span>{user.has_password ? "已设置" : "未设置"}</span>
                    <span className="admin-role-cell">
                      {mappings.length ? (
                        mappings.map((mapping) => (
                          <select
                            aria-label={`${user.name} 的角色`}
                            key={mapping.id}
                            value={mapping.role}
                            onChange={(event) => void changeMappingRole(mapping, event.target.value)}
                          >
                            {roleOptions(mapping.role).map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        ))
                      ) : (
                        <span className="muted">未配置角色</span>
                      )}
                    </span>
                    <span>{user.enabled ? <span className="pill green">启用中</span> : <span className="pill gray">已停用</span>}</span>
                    <span className="action-row compact-actions">
                      <button className="btn" type="button" onClick={() => void toggleUser(user)}>
                        {user.enabled ? "停用" : "启用"}
                      </button>
                      <button className="btn" type="button" onClick={() => openReset(user)}>
                        重置密码
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {section === "batches" && (
        <section className="info">
          <h3>
            <ShieldCheck size={16} />
            导入批次
          </h3>
          <p className="muted">停用批次后，该批次导入的商品机会将从流程中隐藏；恢复批次即恢复展示。</p>
          <div className="admin-filters">
            <label>
              来源
              <select
                value={batchQuery.source_type}
                onChange={(event) => setBatchQuery({ ...batchQuery, source_type: event.target.value, page: 1 })}
              >
                <option value="">全部来源</option>
                {BATCH_SOURCE_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              状态
              <select
                value={batchQuery.status}
                onChange={(event) => setBatchQuery({ ...batchQuery, status: event.target.value, page: 1 })}
              >
                <option value="">全部状态</option>
                {BATCH_STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <span className="tag">共 {batchPage.total} 个批次</span>
          </div>
          {!batchPage.items.length ? (
            <p className="muted">当前筛选条件下没有导入批次。</p>
          ) : (
            <div className="admin-table">
              <div className="admin-batch-row head">
                <span>时间</span>
                <span>来源</span>
                <span>文件 / Sheet</span>
                <span>期数</span>
                <span>新增/更新/跳过</span>
                <span>导入人</span>
                <span>状态</span>
                <span>操作</span>
              </div>
              {batchPage.items.map((batch) => {
                const disabled = batch.status === "disabled";
                const statusMeta = batchStatusMeta(batch.status);
                return (
                  <div className="admin-batch-row" key={batch.id}>
                    <span>{formatBatchTime(batch.imported_at)}</span>
                    <span>{batchSourceTypeLabel(batch.source_type)}</span>
                    <span>{batch.source_file || "-"}{batch.source_sheet ? ` / ${batch.source_sheet}` : ""}</span>
                    <span>{batch.business_period || "-"}</span>
                    <span>{batch.created_count} / {batch.updated_count} / {batch.skipped_count}</span>
                    <span>{batch.imported_by || "-"}</span>
                    <span>
                      <span className={`pill ${statusMeta.klass}`}>{statusMeta.label}</span>
                    </span>
                    <span className="action-row compact-actions">
                      <button className="btn" type="button" onClick={() => openBatchToggle(batch, !disabled)}>
                        {disabled ? "恢复" : "停用"}
                      </button>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
          <div className="action-row admin-pager">
            <select
              aria-label="每页批次数"
              value={batchQuery.page_size}
              onChange={(event) => setBatchQuery({ ...batchQuery, page_size: Number(event.target.value), page: 1 })}
            >
              {[20, 50, 100].map((size) => (
                <option key={size} value={size}>
                  {size} 条/页
                </option>
              ))}
            </select>
            <button
              className="btn"
              type="button"
              disabled={batchQuery.page <= 1 || loading}
              onClick={() => setBatchQuery({ ...batchQuery, page: batchQuery.page - 1 })}
            >
              上一页
            </button>
            <span className="tag">第 {batchPage.page} / {batchPages} 页</span>
            <button
              className="btn"
              type="button"
              disabled={batchQuery.page >= batchPages || loading}
              onClick={() => setBatchQuery({ ...batchQuery, page: batchQuery.page + 1 })}
            >
              下一页
            </button>
          </div>
        </section>
      )}

      {section === "finebi" && (
        <section className="info">
          <h3>
            <Download size={16} />
            FineBI 周数据拉取
          </h3>
          <p className="muted">
            一键完成 FineBI 登录、导出、下载并入库到刊登观察，替代人工每周下载；周标签默认取上一个周四至周三区间。
            需后端开启 FINEBI_AUTO_PULL_ENABLED，仅超级管理员可操作。
          </p>
          <div className="admin-filters">
            <label>
              周标签
              <input
                value={finebiWeekLabel}
                onChange={(event) => {
                  setFinebiWeekLabel(event.target.value);
                  setFinebiError("");
                }}
                placeholder="MMDD-MMDD，如 0723-0729"
              />
            </label>
            <button className="btn primary" type="button" disabled={finebiRunning} onClick={() => void submitFineBIPull()}>
              {finebiRunning ? "拉取中…" : "拉取并入库"}
            </button>
          </div>
          {finebiError && <p className="admin-dialog-error">{finebiError}</p>}
          {finebiResult && (
            <p className="muted">
              已入库 {finebiResult.week_label}：文件 {finebiResult.file}；新增刊登 {finebiResult.apply_counts.listings_created ?? 0}，
              复用刊登 {finebiResult.apply_counts.listings_reused ?? 0}，新增绑定 {finebiResult.apply_counts.bindings_created ?? 0}，
              新增周 {finebiResult.apply_counts.weeks_created ?? 0}，更新周 {finebiResult.apply_counts.weeks_updated ?? 0}。
            </p>
          )}
        </section>
      )}

      {section === "switches" && (
        <section className="info">
          <h3>
            <ShieldCheck size={16} />
            系统开关
          </h3>
          <p className="muted">只读展示后端环境配置的功能开关，修改需调整部署环境变量后重启服务。</p>
          {!switches.length ? (
            <p className="muted">暂无系统开关。</p>
          ) : (
            <div className="admin-table">
              {switches.map((item) => {
                const meta = featureSwitchMeta(item.enabled);
                return (
                  <div className="admin-switch-row" key={item.name}>
                    <span>{item.name}</span>
                    <span className={`pill ${meta.klass}`}>{meta.label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {resetTarget && (
        <div className="listing-overlay">
          <div className="listing-dialog small-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-reset-title">
            <button aria-label="关闭重置密码" className="listing-dialog-close" type="button" onClick={() => setResetTarget(null)}>
              <X size={18} />
            </button>
            <h2 id="admin-reset-title">重置 {resetTarget.name} 的密码</h2>
            <p>可输入自定义新密码（至少 6 位）；留空则按“姓名拼音首字母 + 123456”自动生成。</p>
            <label>
              新密码
              <input
                autoFocus
                value={resetInput}
                onChange={(event) => {
                  setResetInput(event.target.value);
                  setResetError("");
                }}
                placeholder="留空自动生成"
              />
            </label>
            {resetError && <span className="admin-dialog-error">{resetError}</span>}
            <div className="listing-dialog-actions">
              <button className="btn" type="button" onClick={() => setResetTarget(null)}>
                取消
              </button>
              <button className="btn primary" type="button" onClick={() => void submitReset()}>
                确认重置
              </button>
            </div>
          </div>
        </div>
      )}

      {resetResult && (
        <div className="listing-overlay">
          <div className="listing-dialog small-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-reset-result-title">
            <button aria-label="关闭新密码提示" className="listing-dialog-close" type="button" onClick={() => setResetResult(null)}>
              <X size={18} />
            </button>
            <h2 id="admin-reset-result-title">{resetResult.userName} 的新密码</h2>
            <p>{resetResult.result.generated ? "已自动生成初始密码：" : "已设置为自定义密码："}</p>
            <div className="admin-password-display">{resetResult.result.password}</div>
            <p className="admin-password-warning">请转告用户，此密码不会再次显示。</p>
            <div className="listing-dialog-actions">
              <button className="btn primary" type="button" onClick={() => setResetResult(null)}>
                我已记录
              </button>
            </div>
          </div>
        </div>
      )}

      {batchToggleTarget && (
        <div className="listing-overlay">
          <div className="listing-dialog small-dialog" role="dialog" aria-modal="true" aria-labelledby="admin-batch-toggle-title">
            <button aria-label="关闭批次操作确认" className="listing-dialog-close" type="button" onClick={() => setBatchToggleTarget(null)}>
              <X size={18} />
            </button>
            <h2 id="admin-batch-toggle-title">{batchToggleTarget.disabled ? "停用导入批次" : "恢复导入批次"}</h2>
            <p>
              {batchSourceTypeLabel(batchToggleTarget.batch.source_type)} · {batchToggleTarget.batch.source_file || "-"} ·
              期数 {batchToggleTarget.batch.business_period || "-"}
            </p>
            <label>
              {batchToggleTarget.disabled ? "停用原因" : "恢复原因"}
              <textarea
                value={batchToggleReason}
                onChange={(event) => setBatchToggleReason(event.target.value)}
                placeholder="选填，记录到审计日志"
              />
            </label>
            <div className="listing-dialog-actions">
              <button className="btn" type="button" onClick={() => setBatchToggleTarget(null)}>
                取消
              </button>
              <button className="btn primary" type="button" disabled={loading} onClick={() => void submitBatchToggle()}>
                {batchToggleTarget.disabled ? "确认停用" : "确认恢复"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
