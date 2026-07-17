# PLM 全量下载与后半段端到端验收 Implementation Plan

> 执行结果（2026-07-17）：已完成。真实文件解析 2,263 条业务记录、22 个销售员分组；同文件重跑幂等；受控 Item 已完成二次调研、刊登、第 1-5 周和第四周总结。22 张到货测试卡和 2 张淘汰汇总测试卡均只发刘学城，常驻自动开关保持关闭。后续架构已收口为 `caigen-arrival-notifier` 唯一发送到货卡，新品流程平台只保留淘汰汇总提醒。客户端截图已确认当前共享模板没有按钮组件；发送与去重验收完成，入口按钮验收未完成，待复制开发模板并在钉钉卡片设计器中新增、绑定后复测。

> **执行要求：** 按 `superpowers:executing-plans` 逐项执行；代码行为变更先写失败测试，完成前使用 `superpowers:verification-before-completion` 核验。

**Goal:** 在独立开发环境真实下载并处理完整 PLM 数据，把所有到货测试卡和淘汰款汇总卡只发送给刘学城，并用一条受控真实新品记录完成二次调研、刊登、第 1–4 周、四周总结和第 5 周闭环。

**Architecture:** 复用现有 PLM 下载、工作流处理、刊登观察和钉钉发送能力。仅补齐现有测试接收人设置对到货卡和主管汇总卡的覆盖；一次性验收脚本放在开发服务器运行目录，不进入业务运行时。开发常驻自动发送与 PLM 调度继续关闭，生产只读取得必要钉钉配置和刘学城身份映射。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy、pytest、openpyxl、Docker Compose、PostgreSQL、DingTalk API。

## Global Constraints

- [ ] 生产 `101.132.26.138:8080` 不部署、不重启、不写数据库或 `.env`；只允许读取必要的钉钉应用配置和刘学城身份映射。
- [ ] 所有 PLM、业务和通知测试数据只写开发库 `workflow_dev_20260715`。
- [ ] 所有真实钉钉发送只能到刘学城；测试接收人缺失或不唯一时必须失败停止，禁止回退到原销售员或主管。
- [ ] 开发与生产常驻配置保持 `PLM_SYNC_ENABLED=false`；开发保持 `DINGTALK_CARD_AUTOSEND_ENABLED=false`，真实发送只在一次性测试进程中显式开启。
- [ ] 不把账号、密码、Token、钉钉 userId、临时下载 URL 或 `.env` 提交到 Git、文档、输出和工作日志。
- [ ] 不伪造尚不存在的周复盘钉钉卡；本轮只验证现有 `work_notice/pending` 记录。

## Task 1: 用失败测试锁定测试接收人安全边界

**Files:**

- Modify: `backend/tests/test_notification_jobs.py`

- [ ] 新增到货卡测试：两个原销售员分组仍生成两张不同业务卡，但两张卡的实际接收人均为刘学城。
- [ ] 新增失败保护测试：配置了测试接收人但其映射缺失或无钉钉 ID 时抛错，不向原销售员发送。
- [ ] 新增淘汰款汇总测试：存在多个主管时，测试模式只生成并发送一张给刘学城。
- [ ] 运行窄测试，确认新增断言因当前实现未覆盖测试接收人而失败。

## Task 2: 最小实现统一测试接收人覆盖

**Files:**

- Modify: `backend/app/notification_jobs.py`

- [ ] 增加一个私有解析函数，按现有角色范围查找 `DINGTALK_CARD_TEST_RECEIVER_NAME`；配置非空但不可用时抛出明确错误。
- [ ] 到货卡仍按原销售员分组、保留原去重键和卡片内容，只替换实际 receiver userId。
- [ ] 主管到货 / 待办 / 淘汰汇总在测试模式使用唯一测试接收人；设置为空时保持现有生产行为。
- [ ] 运行 Task 1 窄测试和全部通知测试。
- [ ] 检查差异不包含秘密或无关重构并提交代码。

## Task 3: 本地全量回归

**Files:** none

- [ ] 运行 `python -m pytest backend/tests -q`。
- [ ] 运行前端 `npm test` 与 `npm run build`。
- [ ] 核验 Alembic 单一 head，并运行 `git diff --check`。
- [ ] 任何失败先按系统化调试查根因，禁止带失败部署。

## Task 4: 安全准备开发环境

**Targets:**

- Read only: production `.env` and production Liu mapping
- Write: development `.env` and development Liu mapping

- [ ] 记录生产 API / scheduler 容器 ID、启动时间和 RestartCount，作为未触碰基线。
- [ ] 备份开发 `.env` 与开发数据库。
- [ ] 通过权限 `600` 的临时文件把生产必要钉钉键安全复制到开发，不回显值。
- [ ] 把生产刘学城钉钉身份安全写入开发已有 `super_admin` 映射，不输出 userId。
- [ ] 设置开发 `DINGTALK_CARD_TEST_RECEIVER_NAME=刘学城`，保持两个常驻自动开关关闭。
- [ ] 仅验证“键存在 / 值非空 / 映射唯一”，删除临时敏感文件。

## Task 5: 只部署开发环境

**Target:** `139.224.2.166:/opt/hengzhe-new-product-dev/app`

- [ ] 打包已验证提交，上传开发机并保留当前 `1aae41e` 回滚包。
- [ ] 只重建受代码影响的开发服务；不重建 PostgreSQL / Redis，不执行任何生产部署命令。
- [ ] 验证 `http://139.224.2.166:18081/api/health`、容器状态和日志。

## Task 6: 真实下载并完整处理 PLM

**Targets:** development PLM cache and database

- [ ] 使用现有 `download_plm_export(...)` 下载北京时间前一天 `2026-07-16` 的真实完整文件。
- [ ] 用 openpyxl 校验工作簿，记录文件大小、行数、字段数和 SHA-256；不记录 URL 或鉴权信息。
- [ ] 从预览中选择一条字段完整的新品首次到货记录，创建带唯一 E2E 标记、与其子 SKU / 国家 / 销售员精确匹配的已复核平台认领测试记录。
- [ ] 开启本次进程的 workflow automation，处理完整工作簿并回读批次、行数、匹配和二次调研任务。
- [ ] 对同一文件重复处理，断言 `duplicate` 且无重复 PLM 行、到货记录或二次调研任务。

## Task 7: 把全量到货卡只发送给刘学城

**Targets:** DingTalk Liu account and development notification logs

- [ ] 发送前统计有效原销售员分组数和预计卡片数，确认测试接收人唯一可用；不输出钉钉 ID。
- [ ] 一次性进程显式启用卡片发送，发送所有原销售员分组卡；卡片业务姓名不改，实际接收人全部为刘学城。
- [ ] 回读发送状态和去重键；若存在失败则停止后续真实消息发送并保留日志，不盲目重试。
- [ ] 同日期重跑，确认已成功卡片不重复实际发送。

## Task 8: 完成受控后半段闭环

**Targets:** one marked development business record

- [ ] 提交二次调研必填字段，产品定位为 `稳定款`，进入待刊登。
- [ ] 手工字段创建唯一测试店铺、唯一 Item、必填刊登策略和当前业务周期的刊登记录。
- [ ] 第 1–4 周各抓取一次模拟指标并提交定位 / 优化操作：`利润款 → 淘汰款 → 稳定款 → 引流款`；第 4 周同时提交四周总结。
- [ ] 断言第 2 周淘汰后第 3、4 周继续录入，淘汰转换事件只生成一次。
- [ ] 发送主管淘汰款汇总，实际只发送一张给刘学城；重跑不重复。
- [ ] 新增并完成第 5 周 `稳定款`，验证首轮结束后可继续新增周期。
- [ ] 回读工作台和商品详情 API，确认同页可见第 1–5 周历史；核验周复盘仅生成内部 pending 通知。

## Task 9: 验收、文档与交接

**Files:**

- Modify: `docs/02-功能实现状态.md`
- Modify: `docs/06-部署与运维.md`
- Modify: `docs/20-项目推进总控.md`
- Modify: `AGENT_HANDOFF.md`
- Append: `C:/Users/86173/.codex/work-logs/2026-W29.md`

- [ ] 回读所有实际已发送通知，确认测试接收人全部为刘学城且无其他收件人；文档不记录 userId。
- [ ] 再次核对生产 API / scheduler 容器 ID、启动时间和 RestartCount 与基线一致。
- [ ] 运行最终后端、前端、构建、健康检查和 `git diff --check`。
- [ ] 使用 `neat-freak` 对照代码与实测结果同步状态、部署、总控和交接文档；保留“周复盘真实钉钉发送”和“真实周 Item 接口”未完成状态。
- [ ] 追加 Asia/Shanghai 工作日志，记录代码、部署、PLM 流程、消息数量、验证与备份，不含秘密。
- [ ] 审查提交范围并推送 `lxc/integrated-workflow`；不混入其他会话尚未完成的工作树文件。
