import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ADMIN_SECTIONS,
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
} from "../src/adminConsole.ts";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const adminViewSource = readFileSync(new URL("../src/AdminConsoleView.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");

const mapping = (id: string, name: string, role: string) => ({
  id,
  name,
  role,
  enabled: true
});

test("三个分区固定为用户管理、导入批次、系统开关", () => {
  assert.deepEqual(
    ADMIN_SECTIONS.map((item) => [item.key, item.label]),
    [
      ["users", "用户管理"],
      ["batches", "导入批次"],
      ["switches", "系统开关"]
    ]
  );
});

test("角色标签覆盖已知角色，未知角色原样展示并保留为下拉选项", () => {
  assert.equal(roleLabel("operator"), "运营");
  assert.equal(roleLabel("manager"), "主管");
  assert.equal(roleLabel("super_admin"), "超级管理员");
  assert.equal(roleLabel("sales"), "销售");
  assert.equal(roleLabel("custom_role"), "custom_role");
  const options = roleOptions("custom_role");
  assert.deepEqual(
    options.map((option) => option.value),
    ["operator", "sales", "manager", "super_admin", "custom_role"]
  );
  assert.deepEqual(
    roleOptions("manager").map((option) => option.value),
    ["operator", "sales", "manager", "super_admin"]
  );
});

test("按姓名精确匹配角色映射，空白姓名不匹配", () => {
  const mappings = [mapping("1", "张三", "operator"), mapping("2", "张三", "manager"), mapping("3", "张三丰", "operator")];
  assert.deepEqual(
    mappingsForUser("张三", mappings).map((item) => item.id),
    ["1", "2"]
  );
  assert.deepEqual(
    mappingsForUser(" 张三 ", mappings).map((item) => item.id),
    ["1", "2"]
  );
  assert.deepEqual(mappingsForUser("", mappings), []);
  assert.deepEqual(mappingsForUser("李四", mappings), []);
});

test("重置密码输入：留空自动生成通过，非空至少 6 位", () => {
  assert.equal(validateResetPasswordInput(""), "");
  assert.equal(validateResetPasswordInput("   "), "");
  assert.equal(validateResetPasswordInput("abc123"), "");
  assert.notEqual(validateResetPasswordInput("abc12"), "");
  assert.notEqual(validateResetPasswordInput("  ab1  "), "");
});

test("系统开关：开=绿 关=灰", () => {
  assert.deepEqual(featureSwitchMeta(true), { label: "开", klass: "green" });
  assert.deepEqual(featureSwitchMeta(false), { label: "关", klass: "gray" });
});

test("批次来源与状态的筛选选项和标签", () => {
  assert.deepEqual(
    BATCH_SOURCE_TYPE_OPTIONS.map((option) => option.value),
    [
      "selection1_developer_claim_feedback",
      "selection2_caigen_claim_feedback",
      "historical_market_monitor_archive",
      "history_finebi"
    ]
  );
  assert.equal(batchSourceTypeLabel("selection1_developer_claim_feedback"), "选品1 开发反馈表");
  assert.equal(batchSourceTypeLabel("unknown_source"), "unknown_source");
  assert.equal(batchSourceTypeLabel(null), "-");
  assert.deepEqual(
    BATCH_STATUS_OPTIONS.map((option) => option.value),
    ["running", "completed", "disabled"]
  );
  assert.deepEqual(batchStatusMeta("completed"), { label: "已完成", klass: "green" });
  assert.deepEqual(batchStatusMeta("running"), { label: "进行中", klass: "blue" });
  assert.deepEqual(batchStatusMeta("disabled"), { label: "已停用", klass: "gray" });
  assert.deepEqual(batchStatusMeta("weird"), { label: "weird", klass: "gray" });
});

test("批次分页页数向上取整且至少 1 页", () => {
  assert.equal(adminBatchPageCount(0, 20), 1);
  assert.equal(adminBatchPageCount(20, 20), 1);
  assert.equal(adminBatchPageCount(21, 20), 2);
  assert.equal(adminBatchPageCount(5, 0), 5);
});

test("超管后台入口仅 super_admin 可见且渲染受 isSuperAdmin 双重保护", () => {
  assert.match(appSource, /\{isSuperAdmin && \(\s*<button className=\{activeView === "admin" \? "flow-step active" : "flow-step"\} onClick=\{\(\) => setActiveView\("admin"\)\}>\s*<ShieldCheck size=\{16\} \/>\s*超管后台/);
  assert.match(appSource, /\{activeView === "admin" && isSuperAdmin && <AdminConsoleView onStatus=\{setStatusMessage\} \/>\}/);
  assert.match(appSource, /admin: \{ title: "超管后台"/);
});

test("重置密码结果弹窗回显新密码并提示不会再次显示", () => {
  assert.match(adminViewSource, /admin-password-display/);
  assert.match(adminViewSource, /请转告用户，此密码不会再次显示。/);
  assert.match(adminViewSource, /留空自动生成/);
});

test("用户管理无删除按钮，用停用替代", () => {
  assert.doesNotMatch(adminViewSource, /<button[^>]*>[^<]*删除/);
  assert.doesNotMatch(adminViewSource, /method: "DELETE"|adminDeleteUser/);
  assert.match(adminViewSource, /不提供删除用户：请用停用代替/);
  assert.match(adminViewSource, /\{user\.enabled \? "停用" : "启用"\}/);
});

test("批次停用/恢复带原因输入与二次确认按钮", () => {
  assert.match(adminViewSource, /\{batchToggleTarget\.disabled \? "停用原因" : "恢复原因"\}/);
  assert.match(adminViewSource, /\{batchToggleTarget\.disabled \? "确认停用" : "确认恢复"\}/);
  assert.match(adminViewSource, /openBatchToggle\(batch, !disabled\)/);
});

test("api 追加超管端点且重置密码留空发送 null 自动生成", () => {
  assert.match(apiSource, /adminUsers: \(\) => request<AdminUser\[\]>\("\/admin\/users"\)/);
  assert.match(apiSource, /new_password: newPassword \|\| null/);
  assert.match(apiSource, /`\/admin\/users\/\$\{id\}\/reset-password`/);
  assert.match(apiSource, /`\/admin\/import-batches\$\{query\(filter\)\}`/);
  assert.match(apiSource, /`\/admin\/import-batches\/\$\{id\}\/disable`/);
  assert.match(apiSource, /adminFeatureSwitches: \(\) => request<FeatureSwitch\[\]>\("\/admin\/feature-switches"\)/);
  assert.match(apiSource, /updateRoleMapping: \(id: string, payload: \{ role\?: string; enabled\?: boolean \}\)/);
});
