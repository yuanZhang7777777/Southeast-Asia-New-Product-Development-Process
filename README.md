# Hengzhe New Product Workflow

东南亚海外仓新品前段流程平台。第一版范围固定为：两张内部反馈表导入、主管分配、运营认领/不认领、主管复核、导出备货申请表和中央字段追溯表。

第一版不做在线表自动写回、不做采购/供应链待办、不做中央表匹配异常清单。

## Local Test

```powershell
cd E:\Project\Hengzhe-New-Product-Workflow\backend
..\.venv\Scripts\python.exe -m pytest -q

cd E:\Project\Hengzhe-New-Product-Workflow\frontend
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
