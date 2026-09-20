# MyLabData

MyLabData 是一个以分子为中心的数据管理项目，由 React/TypeScript 前端、
FastAPI 后端和现有第三版 DuckDB 数据库组成。

## 当前架构

```text
前端
  ↓ HTTPS / JSON / SSE
api（HTTP 接口）
  ↓
jobs（所有 Query 与 Command 的工作订单、队列和状态）
  ↓
services（业务流程）
  ↓
access（数据库及文件系统访问）
  ↓
DryData（数据本体）
```

后端源码直接位于 `backend/src`：

```text
src/
├── access/
├── api/
├── contracts/
├── core/
├── jobs/
├── schemas/
├── services/
└── main.py
```

所有业务操作都创建 Job。Query Job 表示读取，默认由两个读取
worker 并行处理；Command Job 表示修改，由一个写入 worker 串行处理，避免
多个写操作同时争用 DuckDB。Job 记录存放在独立的 `Jobs.duckdb` 中。

## DryData 目录契约

只需配置 `MLD_DATA_ROOT`，其余数据路径均由后端推导：

```text
DryData/
├── DryData.duckdb
├── Jobs.duckdb
├── Incoming/
│   ├── Molecules/
│   └── Annotations/
├── Processed/
│   ├── Molecules/
│   └── Annotations/
├── Failed/
│   ├── Molecules/
│   └── Annotations/
├── Cache/
├── Temp/
└── New/
```

`New/` 存放通过 Import 页上传的源数据文件（CSV），供“人工定义 Attribute/Entry
并生成 Annotation Package”的建包流程使用；包生成后写入 `Incoming/Annotations`，
仍需预览确认才会导入。

当前代码直接适配已有的第三版 `DryData.duckdb` 六张表：`Molecules`、
`Attributes`、`Entries`、`Annotations`、`Sources` 和 `Imports`；不会创建或
迁移业务数据库。导入成功后包会移至 `Processed`。导入或预览失败时包仍留在
`Incoming`，目前不会自动移至 `Failed`。

## 启动后端

在 `backend` 目录运行：

```powershell
$env:MLD_DATA_ROOT = "C:\path\to\DryData"
python -m uvicorn main:app --app-dir src --host 127.0.0.1 --port 8000
```

开发前端时，在 `frontend` 目录运行 `npm run dev`；Vite 会把 `/api` 请求代理
到 `127.0.0.1:8000`。生产式本地运行可先构建前端，再设置
`MLD_FRONTEND_DIST_DIRECTORY` 让 FastAPI 同源提供静态页面。

后端的完整说明与验证命令见 `backend/README.md` 和
`backend/tests/README.md`。
