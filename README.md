# Hengzhe New Product Workflow

东南亚海外仓新品流程平台。前段已覆盖两张内部反馈表导入、主管分配、运营认领/不认领、主管复核、备货申请表和中央字段追溯表导出；后段开发环境已覆盖到货后二次调研、刊登与 Item 独立周期观察。

第一版仍不做在线表自动写回、采购/供应链待办或中央表匹配异常清单。周 Item 指标目前只有稳定的内部落库边界，真实公司接口和凭据尚未接入。

主管复核支持按“运营认领 / 运营不认领”分组批量通过或退回补充。商品详情按源表表头识别价格字段，主管可在保留原始来源快照和审计记录的前提下修正当前商品业务参数与合法状态。

当前统一开发基线为 `lxc/integrated-workflow@1aae41e`，已部署到开发环境 [http://139.224.2.166:18081](http://139.224.2.166:18081)。生产环境仍运行 `b373d65`，不得把开发部署视为生产发布。

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
docker compose config
docker compose up -d --build
```

Default services: PostgreSQL 16, Redis, FastAPI API, worker, scheduler, React frontend, and Caddy reverse proxy.
