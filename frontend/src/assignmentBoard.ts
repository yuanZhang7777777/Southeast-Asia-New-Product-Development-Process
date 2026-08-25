export type AssignmentBoardRowLike = {
  task_id: string;
  task_status: string;
  assignee_name?: string | null;
};

export type AssignmentBoardGroupLike<T extends AssignmentBoardRowLike> = {
  batch: string;
  rows: T[];
};

export function canReassignBoardRow(row: Pick<AssignmentBoardRowLike, "task_status" | "assignee_name">) {
  return row.task_status === "pending" && !!row.assignee_name;
}

export function applyBoardReassignment<T extends AssignmentBoardRowLike, G extends AssignmentBoardGroupLike<T>>(
  groups: readonly G[],
  taskId: string,
  assigneeName: string
): G[] {
  return groups.map((group) => ({
    ...group,
    rows: group.rows.map((row) => (row.task_id === taskId ? { ...row, assignee_name: assigneeName } : row))
  }));
}

export function boardGroupSummary<T extends AssignmentBoardRowLike>(groups: readonly AssignmentBoardGroupLike<T>[]) {
  const rows = groups.flatMap((group) => group.rows);
  return {
    total: rows.length,
    pending: rows.filter(canReassignBoardRow).length,
    assignees: new Set(rows.map((row) => row.assignee_name).filter(Boolean)).size
  };
}


export function filterBoardOptionCandidates(options: readonly string[], query: string) {
  const needle = query.trim().toLowerCase();
  if (!needle) return [...options];
  return options.filter((option) => option.toLowerCase().includes(needle));
}
