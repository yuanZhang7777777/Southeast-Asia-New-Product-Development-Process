# Hengzhe New Product Workflow

东南亚海外仓新品流程平台。前段已覆盖两张内部反馈表导入、主管分配、运营认领/不认领、主管复核、销售自选三分支、运营备货申请保存/提交和主管勾选导出；后段开发环境已覆盖到货后二次调研、刊登与 Item 独立周期观察。ERP 体积查询不可用时允许运营手填降级。

第一版仍不做在线表自动写回、采购/供应链待办或中央表匹配异常清单。周 Item 指标目前只有稳定的内部落库边界，真实公司接口和凭据尚未接入。

主管复核支持按“运营认领 / 运营不认领”分组批量通过或退回补充。商品详情按源表表头识别价格字段，主管可在保留原始来源快照和审计记录的前提下修正当前商品业务参数与合法状态。

统一开发分支为 `lxc/integrated-workflow`；开发环境当前部署 `b0f27fde5109`，访问地址为 [http://139.224.2.166:18081](http://139.224.2.166:18081)。开发库保持 `e1f2a3b4c678 (head)`；该版本在既有备货申请、长 / 宽 / 高自动体积、自动保存和稳定复核布局上，进一步压紧“主 SKU → Item → 周记录”观察工作台并修复复选框、单结果拉伸和平板断行。生产环境仍运行 `b373d65`，本次未连接或变更生产，不得把开发部署视为生产发布。

销售自选三分支、申请填写 / 自动保存 / 提交和主管勾选导出的写入式业务 UAT 已由用户确认无问题。2026-07-22 开发环境只读实测 PLM 可下载并识别真实新到货；当前开发库没有与样例新到货对应的正式导出 `waiting_arrival` 记录，因此现行精确匹配推进仍需用下一笔真实正式导出做一次受控 UAT。三个自动化开关继续保持关闭。

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
