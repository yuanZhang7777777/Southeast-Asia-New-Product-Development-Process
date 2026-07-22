# Hengzhe New Product Workflow

东南亚海外仓新品流程平台。前段已覆盖两张内部反馈表导入、主管分配、运营认领/不认领、主管复核、销售自选三分支、运营备货申请保存/提交和主管勾选导出；后段开发环境已覆盖到货后二次调研、刊登与 Item 独立周期观察。ERP 体积查询不可用时允许运营手填降级。

第一版仍不做在线表自动写回、采购/供应链待办或中央表匹配异常清单。周 Item 指标目前只有稳定的内部落库边界，真实公司接口和凭据尚未接入。

主管复核支持按“运营认领 / 运营不认领”分组批量通过或退回补充。商品详情按源表表头识别价格字段，主管可在保留原始来源快照和审计记录的前提下修正当前商品业务参数与合法状态。

统一开发分支为 `lxc/integrated-workflow`；开发环境当前部署 `ac8a5359e350`，访问地址为 [http://139.224.2.166:18081](http://139.224.2.166:18081)。开发库已迁移到 `e1f2a3b4c678 (head)`；该版本提供备货申请/导出工作台、长 / 宽 / 高（cm）自动计算单个体积、离开申请编辑区自动保存、固定主 / 子 SKU 排序、稳定的主管复核布局，以及可折叠的“主 SKU → Item → 周记录”观察工作台。生产环境仍运行 `b373d65`，本次未连接或变更生产，不得把开发部署视为生产发布。

销售自选与新版备货申请已完成技术部署和管理员/运营只读页面验收；主管复核先按“销售员 + 子 SKU”生成草稿，运营填写并提交后才进入主管可勾选导出范围，真实导出后才进入 `waiting_arrival` 并允许 PLM 按导出快照国家精确关联。三分支、填写、提交和导出的写入式业务 UAT 仍待刘学城在开发环境完成。

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
