import assert from "node:assert/strict";
import test from "node:test";

import { applyBoardReassignment, boardGroupSummary, canReassignBoardRow } from "../src/assignmentBoard.ts";

const groups = [
  {
    batch: "0714期",
    rows: [
      { task_id: "t1", task_status: "pending", assignee_name: "运营A" },
      { task_id: "t2", task_status: "completed", assignee_name: "运营B" }
    ]
  },
  {
    batch: "0707期",
    rows: [{ task_id: "t3", task_status: "pending", assignee_name: "运营B" }]
  }
];

test("只有已有受派人的待认领任务允许改派", () => {
  assert.equal(canReassignBoardRow({ task_status: "pending", assignee_name: "运营A" }), true);
  assert.equal(canReassignBoardRow({ task_status: "completed", assignee_name: "运营A" }), false);
  assert.equal(canReassignBoardRow({ task_status: "pending", assignee_name: null }), false);
});

test("改派成功后就地更新对应行的受派运营", () => {
  const next = applyBoardReassignment(groups, "t1", "运营C");
  assert.equal(next[0].rows[0].assignee_name, "运营C");
  assert.equal(next[0].rows[1].assignee_name, "运营B");
  assert.equal(next[1].rows[0].assignee_name, "运营B");
  assert.equal(groups[0].rows[0].assignee_name, "运营A");
});

test("汇总统计当前列表的总数、待认领数和人数", () => {
  assert.deepEqual(boardGroupSummary(groups), { total: 3, pending: 2, assignees: 2 });
});
