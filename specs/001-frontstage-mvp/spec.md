# Feature Specification: Frontstage New Product MVP

**Feature Branch**: `001-frontstage-mvp`

**Created**: 2026-07-02

**Status**: Draft

**Input**: User description: "第一版只围绕两张内部反馈表做导入、主管分配、运营认领/不认领、主管复核和导出；中间桥、在线表自动写回、匹配异常清单、采购/供应链待办都先不做。"

## Clarifications

### Session 2026-07-03

- Q: 商品看板是否属于第一版，且它和机会池是什么关系？ → A: 商品看板属于第一版；商品看板是全量商品状态总览，机会池只显示待处理新品机会；看板中的后段节点只是状态展示，不代表第一版实现后段任务。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import Feedback Tables (Priority: P1)

主管导入 `选品1：海外仓开发部门开发新品认领-反馈.xlsx` 或 `选品2：海外仓财根团队开发新品认领-反馈.xlsx` 后，系统生成可分配的新品机会，并保留来源文件、sheet、行号和原始字段快照。

**Why this priority**: 导入是整个第一版流程的入口，没有可追溯导入就无法分配、认领、复核或导出。

**Independent Test**: 可以用一份含 1 个主 SKU、多个子 SKU 的样例 Excel 导入，验证系统生成机会记录、来源追溯和字段默认值。

**Acceptance Scenarios**:

1. **Given** 一份字段完整的选品1反馈表，**When** 主管导入指定 sheet，**Then** 系统为每一条有效子 SKU 生成机会记录，并保留来源文件、sheet、行号和快照。
2. **Given** 一份财根反馈表且部分中央字段缺失，**When** 主管导入，**Then** 系统能映射已有字段，缺失且无法唯一补齐的目标字段留空，不阻塞导入。
3. **Given** 同一来源文件、sheet、行号重复导入，**When** 主管再次导入，**Then** 系统更新已有记录而不是重复创建记录。
4. **Given** 主管在源表导入页上传反馈表，**When** 主管拖拽文件到上传区或点击选择文件，**Then** 系统读取该 Excel 文件并导入，页面不要求用户填写服务器本地文件路径。

---

### User Story 2 - Supervisor Assignment (Priority: P1)

主管对导入后的主 SKU 组执行一键分配，系统按重点站点、重点品类1、重点品类2和当前负载给出建议，主管可确认后生成运营认领任务。

**Why this priority**: 分配决定每个主 SKU 组进入哪个运营处理，是后续认领和复核的前置动作。

**Independent Test**: 可以准备人员配置表和多个主 SKU 组，验证系统按主 SKU 组生成分配建议，并在确认后生成任务。

**Acceptance Scenarios**:

1. **Given** 多个子 SKU 属于同一主 SKU，**When** 主管一键分配，**Then** 该主 SKU 组作为整体分配，不拆分子 SKU 给不同运营。
2. **Given** 运营人员配置包含重点站点和重点品类，**When** 系统生成分配建议，**Then** 优先匹配重点站点，其次重点品类1，其次重点品类2，最后按当前未完成主 SKU 组负载均衡。
3. **Given** 主管调整系统建议，**When** 主管确认分配，**Then** 系统按主管确认结果创建运营认领任务。
4. **Given** 主管打开分配台，**When** 存在选品1导入的待分配主 SKU 组，**Then** 系统默认使用全部启用运营人员生成推荐，不要求主管手工填写候选人名单。
5. **Given** 选品1反馈表导入完成，**When** 主管尚未确认分配，**Then** 该来源的主 SKU 组只进入分配台，保持待分配状态，不自动生成运营认领任务，也不进入运营自领机会池。
6. **Given** 财根反馈表导入完成，**When** 主管尚未确认分配，**Then** 该来源的主 SKU 组既可在分配台参与一键分配，也可在运营机会池供销售员自认领。

---

### User Story 3 - Operator Claim Or Not Claim (Priority: P1)

运营打开自己的认领任务，对每个子 SKU 选择认领或不认领。认领时填写认领单销，不认领时填写不认领理由，并可填写反馈总结和备注。

**Why this priority**: 认领结果和认领单销直接决定是否进入备货导出，以及备货数量。

**Independent Test**: 可以对一个已分配任务分别提交认领和不认领，验证必填校验、时间记录和状态流转。

**Acceptance Scenarios**:

1. **Given** 运营选择认领，**When** 未填写认领单销提交，**Then** 系统拒绝提交并提示认领单销必填。
2. **Given** 运营选择不认领，**When** 未填写不认领理由提交，**Then** 系统拒绝提交并提示不认领理由必填。
3. **Given** 运营提交前仍在草稿或待提交状态，**When** 运营修改是否认领、认领单销、不认领理由、反馈总结或备注，**Then** 系统记录这些字段的首次创建时间和最后更新时间。
4. **Given** 财根反馈表中的同一 SKU 可被多人自领，**When** 多个运营分别认领同一子 SKU，**Then** 系统分别保留每个运营的认领记录，不限制人数。
5. **Given** 运营在认领卡片上选择认领，**When** 运营填写认领单销并提交，**Then** 系统只提交认领单销，不同时提交不认领原因。
6. **Given** 运营在认领卡片上选择不认领，**When** 运营填写不认领原因并粘贴、拖拽或选择调研图片，**Then** 系统提交不认领原因，并保留图片证据占位信息。
7. **Given** 一个主 SKU 下有多个子 SKU，**When** 运营打开认领页，**Then** 系统按主 SKU 分组展示这些子 SKU，运营可以逐个填写。
8. **Given** 运营已在多个子 SKU 卡片上填完整认领单销或不认领原因，**When** 点击一键提交已填写，**Then** 系统只提交填写完整的子 SKU，未填完整的子 SKU 保持草稿状态。
9. **Given** 主管退回补充，**When** 运营重新打开认领页，**Then** 系统在对应子 SKU 上展示主管退回原因。

---

### User Story 4 - Supervisor Review (Priority: P1)

主管复核运营提交的认领或不认领结果。主管不能代改运营提交内容，只能通过、确认不认领或退回补充。

**Why this priority**: 复核是进入导出前的质量控制点，也决定不认领终态。

**Independent Test**: 可以提交一条认领记录和一条不认领记录，分别验证通过、确认不认领和退回补充。

**Acceptance Scenarios**:

1. **Given** 运营提交认领，**When** 主管复核通过，**Then** 子 SKU 进入可备货导出范围。
2. **Given** 运营提交不认领并填写理由，**When** 主管确认，**Then** 子 SKU 进入 `已确认不认领` 终态，且不进入备货导出范围。
3. **Given** 主管认为认领单销或不认领理由不完整，**When** 主管退回补充，**Then** 任务回到运营补充状态，主管不能直接修改运营字段。
4. **Given** 主管查看复核列表，**When** 任务来自运营认领提交或不认领提交，**Then** 系统分别显示 `待复核-认领` 和 `待复核-不认领`，并在卡片上标明 `运营已认领` 或 `运营不认领`。
5. **Given** 复核对象是运营认领提交，**When** 主管提交复核，**Then** 复核表单只提供通过认领，不要求填写复核意见。
6. **Given** 复核对象是运营不认领提交，**When** 主管选择退回补充，**Then** 必须填写退回原因，状态显示为 `已驳回-待运营补充`，并回到运营补充入口。

---

### User Story 5 - Export Approved Stocking Rows (Priority: P1)

主管或数据人员点击导出，系统生成本批可备货子 SKU 明细。导出只包含子 SKU 明细，不生成主 SKU 汇总；同一子 SKU 被多个运营认领通过时按运营分别导出多行。

**Why this priority**: 第一版的正式闭环是导出，不做在线表自动写回。

**Independent Test**: 可以准备多个通过复核的认领记录，验证导出文件结构、行数和备货数量。

**Acceptance Scenarios**:

1. **Given** 认领单销为 1.5，**When** 导出备货申请表，**Then** 备货数量为 45。
2. **Given** 同一子 SKU 有 3 个运营认领通过，**When** 导出备货申请表，**Then** 导出 3 行，不合并为 1 行。
3. **Given** 子 SKU 已确认不认领，**When** 导出备货申请表，**Then** 该子 SKU 不出现在导出文件中。
4. **Given** 主管点击导出，**When** 导出完成，**Then** 系统记录导出人、导出时间、导出文件名和导出范围。

---

### User Story 6 - Product Dashboard Status Overview (Priority: P1)

主管和运营打开 `商品看板`，按主 SKU 分组查看所有已进入平台的商品当前状态，并可展开查看子 SKU 状态。`商品看板` 是全量状态总览，不等同于只展示待处理新品的 `机会池`。

**Why this priority**: 商品看板是用户判断“每个商品走到哪一步”的固定入口；如果缺失，主管和运营只能在单个流程页里找数据，容易误判任务是否已分配、已认领、待复核、可导出或已终止。

**Independent Test**: 可以准备同一批导入商品的不同状态记录，验证商品看板展示全量主 SKU 组、展开子 SKU、搜索筛选和状态展示。

**Acceptance Scenarios**:

1. **Given** 平台内存在待分配、待认领、待复核、已确认不认领和可导出的商品，**When** 用户打开商品看板，**Then** 系统按主 SKU 分组展示全部商品，而不是只展示机会池中的待处理新品。
2. **Given** 一个主 SKU 组包含多个子 SKU，**When** 用户展开该主 SKU 组，**Then** 系统展示每个子 SKU 的认领结果、复核结果和是否可导出。
3. **Given** 用户按站点、运营、状态、健康标签、一级类目 / 二级类目、来源批次筛选，或按主 SKU、子 SKU、商品名、关键词搜索，**When** 条件生效，**Then** 商品看板只缩小展示范围，不改变商品状态。
4. **Given** 商品看板中展示到货、二次调研、定价、刊登、每周监控或四周总结等后段节点，**When** 第一版运行，**Then** 这些节点只作为状态标签或占位展示，不创建第一版外的到货、调研、刊登、监控或总结待办。
5. **Given** 同一主 SKU 下有多个子 SKU，**When** 商品看板或认领页展示商品信息，**Then** 开品理由按主 SKU 组显示一次，子 SKU 明细不重复展示开品理由。
6. **Given** 商品看板没有独立详情页，**When** 用户查看主 SKU 组，**Then** 页面只保留展开 / 收起子 SKU 操作，不提供与展开重复的查看详情按钮。

### Edge Cases

- 来源表字段能匹配的写入目标字段；来源表没有且无法唯一补齐的目标字段留空，不写 `0`。
- 财根反馈表缺少站点字段时，可通过主 SKU / 子 SKU 回查中央新品表辅助补齐；匹配不到或匹配多行不阻塞导入、认领、复核和导出。
- 运营忽略财根机会池中的自领机会时，不生成不认领任务。
- 主管查看新品机会池时不能直接认领或替运营提交认领；主管只能查看、分配或复核。
- 已提交给主管复核后，运营不能自行撤回；只能由主管退回补充。
- 商品看板不能因为商品已经离开机会池、进入复核、可导出、已导出或已确认不认领而隐藏该商品；它必须保留全量状态视图。
- 第一版不做在线表自动写回入口，不生成中央表匹配异常清单，不生成采购或供应链待办。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST import only the two in-scope internal feedback workbooks for the first version: development department feedback and Caigen team feedback.
- **FR-002**: System MUST retain source traceability for every imported row, including source file, sheet, row number, import batch, and original snapshot.
- **FR-003**: System MUST align imported fields to the `东南亚海外仓新品表-PH/TH/VN` field dictionary by header name or documented semantic mapping, not fixed column position.
- **FR-004**: System MUST leave unmatched target fields empty when they cannot be mapped or uniquely backfilled.
- **FR-005**: System MUST treat main SKU group as the supervisor assignment unit and child SKU as the export/detail unit.
- **FR-006**: System MUST generate one-click assignment suggestions using priority order: key site, key category 1, key category 2, current main-SKU-group load.
- **FR-007**: System MUST allow the supervisor to adjust assignment suggestions before creating operator claim tasks.
- **FR-008**: System MUST require claim daily sales when an operator chooses to claim.
- **FR-009**: System MUST require a not-claim reason when an operator chooses not to claim.
- **FR-010**: System MUST keep first-created and last-updated timestamps for operator-submitted claim/not-claim fields, including not-claim reason.
- **FR-011**: System MUST allow unlimited approved claim records for the same child SKU in the Caigen opportunity pool.
- **FR-012**: System MUST prevent supervisors from editing operator-submitted claim daily sales or not-claim reason during review.
- **FR-013**: System MUST allow supervisors to approve claimed submissions, confirm not-claim submissions, or return submissions for supplement.
- **FR-014**: System MUST mark supervisor-confirmed not-claim records as `已确认不认领`.
- **FR-015**: System MUST export only child SKU detail rows that have approved claim submissions.
- **FR-016**: System MUST calculate stocking quantity as `认领单销 × 30`.
- **FR-017**: System MUST export `备货申请表` using the 16-column structure of `海外仓备货申请表.xlsx`.
- **FR-018**: System MUST keep `补货原因` empty in the first-version stocking export.
- **FR-019**: System MUST generate a full-field traceability export for the same approved child SKU rows, using central-table fields before `开发是否接受核价结果` plus internal claim/review/export fields.
- **FR-020**: System MUST record export batch metadata: exporter, export time, export file name, and export scope.
- **FR-021**: System MUST provide a dedicated `商品看板` that shows all platform product records grouped by main SKU, with expandable child SKU rows and current workflow status.
- **FR-022**: System MUST keep `商品看板` separate from `机会池`: `商品看板` shows all product statuses, while `机会池` shows only pending or claimable new-product opportunities.
- **FR-023**: System MUST support product-dashboard search and filters for main SKU, child SKU, product name, keyword, site, operator, status, health label, level-1 / level-2 category, and source batch.
- **FR-024**: System MUST treat later-stage labels shown on the product dashboard as read-only status indicators in the first version unless a later feature explicitly implements those workflows.
- **FR-025**: System MUST NOT expose online-table automatic writeback, central-table exception-list handling, procurement todos, or supply-chain todos in the first version.
- **FR-026**: System MUST import feedback workbooks from browser file upload by drag-and-drop or file picker; the UI MUST NOT ask users to type server-local file paths.
- **FR-027**: System MUST prevent supervisors from claiming opportunities from the opportunity pool; claim submissions must be tied to an operator identity.
- **FR-028**: System MUST maintain a supervisor-editable operator assignment configuration with only these first-version fields: operator name, key site, key category 1, key category 2.
- **FR-029**: System MUST generate one-click assignment previews using all enabled operator assignment profiles by default, without requiring a manually typed candidate list.
- **FR-030**: System MUST render operator claim/not-claim inputs inline on the product card and make claim daily sales and not-claim reason mutually exclusive by action.
- **FR-031**: System MUST provide a not-claim evidence area that accepts pasted, dragged, or selected research images; first version may store this evidence in the claim note payload until dedicated file storage is implemented.
- **FR-032**: System MUST provide local-only demo data generation that covers the major statuses needed for UI testing: pending assignment, assigned, pending supervisor review, returned for supplement, confirmed not-claim, ready for export, and mixed status.
- **FR-033**: System MUST route selection1 developer feedback imports into supervisor assignment only until the supervisor confirms assignment; selection1 import MUST NOT auto-create operator claim tasks from source-table salesperson columns.
- **FR-034**: System MUST route selection2 Caigen feedback imports into both supervisor assignment and operator self-claim opportunity pool, because Caigen opportunities may be claimed by multiple operators.
- **FR-035**: System MUST group operator claim cards by main SKU and keep child SKU rows visible together.
- **FR-036**: System MUST allow operators to submit all complete child-SKU drafts in one action while leaving incomplete drafts unsubmitted.
- **FR-037**: System MUST distinguish supervisor-review statuses for claimed vs not-claimed submissions in UI labels and review cards.
- **FR-038**: System MUST require a supervisor return reason only when returning a not-claim submission for supplement, and MUST expose that reason to the operator on the returned child SKU.
- **FR-039**: System MUST display `开品理由` once at main-SKU-group level when child SKUs share the same main SKU.
- **FR-040**: System MUST avoid duplicate dashboard actions; if no richer detail view exists, product dashboard cards MUST use only expand/collapse for child SKU details.

### Key Entities *(include if feature involves data)*

- **Source Import Batch**: A single import operation with source workbook, sheet, import time, operator, and summary counts.
- **Source Row Snapshot**: Immutable trace of a source row, including source file, sheet, row number, and captured fields.
- **New Product Opportunity**: Imported child SKU opportunity aligned to the central field dictionary and grouped by main SKU.
- **Main SKU Group**: Assignment unit containing one or more child SKU opportunities.
- **Operator Claim Record**: A submitted claim or not-claim decision for one operator and one child SKU.
- **Supervisor Review Record**: Supervisor decision on an operator submission.
- **Export Batch**: One export action containing metadata and generated child SKU rows.
- **Export Row**: One approved claim row in the exported stocking detail.
- **Product Dashboard View**: A read view that groups all platform product records by main SKU, expands to child SKU rows, and shows current status, owner, source batch, and health label.
- **Opportunity Pool View**: A narrower action view that lists only pending or claimable new-product opportunities.
- **Operator Assignment Profile**: Supervisor-maintained configuration for one operator, containing operator name, key site, key category 1, key category 2, and enabled flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A supervisor can import a valid feedback workbook and see generated opportunities within 5 minutes for a typical weekly batch.
- **SC-002**: For every imported opportunity, a reviewer can trace back to source file, sheet, and row without opening the original chat history.
- **SC-003**: At least 95% of valid source rows in the two in-scope feedback workbooks are imported without manual correction when headers match documented mappings.
- **SC-004**: A supervisor can generate assignment suggestions and create operator tasks for a weekly batch in under 10 minutes.
- **SC-005**: Operators cannot submit claim records missing required claim daily sales or not-claim reason.
- **SC-006**: Approved claim rows export with stocking quantity equal to claim daily sales multiplied by 30 in 100% of tested cases.
- **SC-007**: Confirmed not-claim rows never appear in the stocking export.
- **SC-008**: The exported stocking workbook can be opened in Excel and contains the same 16 business columns as the existing `海外仓备货申请表.xlsx` template.
- **SC-009**: A supervisor or operator can locate an imported main SKU or child SKU and identify its current status from the dedicated `商品看板` in under 1 minute during a smoke test.

## Assumptions

- First-version users are internal Group 8 operators and the fixed supervisor `练玉君`.
- DingTalk is an entry and notification channel only in the first version; submitted data is stored in the platform database.
- The first version is export-only and does not automatically write back to DingTalk online sheets.
- PostgreSQL is the intended production database; lightweight local databases may be used only for development and automated tests.
- Existing Excel source files remain business inputs, but platform state is authoritative for assignment, claim, review, and export status after import.
- `商品看板` is part of the first-version UI as the all-product status overview; market monitoring, PLM arrival tracking, listing, and four-week summaries remain later-stage capabilities and are not implemented as first-version workflows.
