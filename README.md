# Hengzhe New Product Workflow

东南亚海外仓新品流程平台。前段已覆盖两张内部反馈表导入、主管分配、运营认领/不认领、主管复核、销售自选三分支、运营备货申请保存/提交和主管勾选导出；后段开发环境已覆盖到货后二次调研、刊登与 Item 独立周期观察。ERP 体积查询不可用时允许运营手填降级。

第一版仍不做在线表自动写回、采购/供应链待办或中央表匹配异常清单。集团八部 Hermes / FineBI 原始 `ItemID财务数据八部` 既可在发生财务行后提供滞后的 `主 SKU -> 店铺 + Item` 历史候选，也将作为周指标源；它没有子 SKU，不能替代实时刊登接口。平台尚未把周指标接到 `apply_week_metrics(...)`，不得改用会过滤低于 7 单 Item 的成品表。

主管复核支持按“运营认领 / 运营不认领”分组批量通过或退回补充。商品详情按源表表头识别价格字段，主管可在保留原始来源快照和审计记录的前提下修正当前商品业务参数与合法状态。

开发主线以 `lxc/integrated-workflow` 为基线；当前开发环境运行标记 `cced0b9-role-switch-hotfix-20260724_1538`，完整数据重置基线为 `cced0b9-later-uat-full-20260724_150554`，访问地址为 [http://139.224.2.166:18081](http://139.224.2.166:18081)，开发库为 `workflow_dev_20260715 / e1f2a3b4c678 (head)`。当前开发环境已包含第二轮紧凑 UI、刊登主 SKU / Item 新增入口、周期观察折叠状态与最近指标、二次调研主 SKU 模块详情、顶部同排筛选、“延长观察”文案，以及 `super_admin` 可切换主管 / 运营视角的角色热修。旧业务测试数据已清理，保留系统配置并按只读生产账号/角色/运营档案清单重建开发账号，密码统一为姓名拼音首字母加 `123456`，未复制生产密码哈希；生产只读核对为 `刘学城=super_admin`、`练玉君=manager`。当前 UAT 业务期为 `后半段UAT-20260724`，已准备二次调研、备货导出、刊登任务和周期观察覆盖数据。生产环境仍运行 `b373d65`，本次只读核对账号配置，未部署、重启或修改生产。

销售自选三分支、申请填写 / 自动保存 / 提交和主管勾选导出的写入式业务 UAT 已由用户确认无问题。2026-07-23 起，开发环境每天用 2,237 个历史 `国家 + 子 SKU` 关注键检查前一天 PLM 首次到货，命中时只向刘学城发送试运行卡片；除下载或复用 `/data/plm/plm-<date>.xlsx` 缓存外，它只写独立 JSON 幂等状态，不写业务表，三个全局自动化开关继续保持关闭。该试运行不替代现行正式 `waiting_arrival + ExportRow` 精确匹配 UAT，后者仍需下一笔真实正式导出验证。

已校验 2026-04-16 至 2026-07-22 共 14 个 FineBI 周期：2,237 个历史关注键中命中 566 个，形成 202 个唯一待确认候选、364 个多候选和 1,671 个未命中；任何候选均未自动写入业务库。

## Documentation

从 [docs/README.md](docs/README.md) 进入文档。业务规则、实现状态、推进、架构和部署分别只有一份权威文档；历史规格和源表证据冻结在 `docs/archive/2026-07-22/`，不参与日常维护。

## Local Test

```powershell
cd E:\Project\Hengzhe-New-Product-Workflow\backend
..\.venv\Scripts\python.exe -m pytest -q

cd E:\Project\Hengzhe-New-Product-Workflow\frontend
npm test
npm run build
```

测试使用 SQLite。生产环境必须使用 PostgreSQL `DATABASE_URL`。

## Local Dev

Backend:

```powershell
cd E:\Project\Hengzhe-New-Product-Workflow\backend
$env:APP_ENV='local'
$env:DATABASE_URL='sqlite:///./workflow_dev.db'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd E:\Project\Hengzhe-New-Product-Workflow\frontend
$env:VITE_API_BASE_URL='http://127.0.0.1:8000'
npm run dev
```

## Docker Compose

Create `.env` outside source control for real passwords and deployment-specific values, then run:

```powershell
docker compose -p hengzhe-new-product-dev --env-file .env config
docker compose -p hengzhe-new-product-dev --env-file .env up -d --build
```

Default services: PostgreSQL 16, Redis, FastAPI API, worker, scheduler, React frontend, and Caddy reverse proxy.
