# MyLabData Backend

这是 MyLabData 当前 FastAPI 后端。它直接读取和修改现有的第三版
`DryData.duckdb`，所有业务操作统一通过持久化 Job 执行。

## 源码分层

```text
src/
├── api/        # FastAPI 路由、HTTP 请求与响应适配
├── jobs/       # 工作订单、状态机、持久化队列及处理器
├── services/   # Query 与 Command 业务流程
├── access/     # DuckDB、文件、目录、哈希和缓存的唯一访问边界
├── contracts/  # Annotation Package 输入契约
├── schemas/    # API 与业务数据模型
├── core/       # 配置、日志、版本和通用异常
└── main.py     # FastAPI 应用入口及 worker 生命周期
```

读取流程和修改流程分别是：

```text
API → Query Job   → services/queries.py  → access → DryData
API → Command Job → services/commands.py → access → DryData
```

Service 不直接使用真实文件路径；扫描、读取、哈希与归档均由 `access` 完成。
API 只接受后端扫描得到的不透明 `package_id`，不会接收客户端文件系统路径。

## 数据库与目录

`MLD_DATA_ROOT` 是唯一核心数据路径配置。后端从它固定推导：

- `DryData.duckdb`：第三版业务数据库；
- `Jobs.duckdb`：Job 工作订单与状态；
- `Incoming/Molecules`、`Incoming/Annotations`：待处理输入；
- `Processed/Molecules`、`Processed/Annotations`：成功归档；
- `Failed/Molecules`、`Failed/Annotations`：预留失败归档目录；
- `Cache` 与 `Temp`：缓存和 DuckDB 临时空间；
- `New`：上传的源数据文件（供 Import 页的建包流程使用）。

缺失的运行目录可以建立，但数据库文件不会因此被自动创建。业务数据库必须
已经存在并包含第三版六张表：`Molecules`、`Attributes`、`Entries`、
`Annotations`、`Sources`、`Imports`。当前版本没有 migration，也不兼容旧表
结构。

Molecules 输入是含 `canonical_smiles` 列的 Parquet 文件。Annotation Package
由 `annotation_manifest.json`、`annotations.parquet`、
`processing_report.json` 和可选的 `rejected.parquet` 组成。预览令牌绑定包名与
内容哈希，因此确认前内容变化会被拒绝。数据库写入成功后才归档到
`Processed`；失败时保留在 `Incoming`，不会自动移到 `Failed`。

## Job 模型

Query 与 Command 都是 Job，并记录在 `Jobs.duckdb`。默认启动两个 Query
worker 处理读取和一个 Command worker 串行处理修改。前端提交后立即得到
`job_id`，可通过 `/api/v1/jobs/{job_id}` 查询，也可通过
`/api/v1/jobs/{job_id}/events` 接收 SSE 进度。

Job 状态包括排队、校验、运行、等待确认、导入、归档、归档待处理、完成、
失败与取消。后端重启时，遗留的未结束 Job 会被标记为失败，避免把中断任务
误报为完成。

## 配置与启动

可从项目根目录的 `.env.example` 复制配置。最小启动方式是在本目录运行：

```powershell
$env:MLD_DATA_ROOT = "C:\path\to\DryData"
python -m uvicorn main:app --app-dir src --host 127.0.0.1 --port 8000
```

可选设置包括 `MLD_HOST`、`MLD_PORT`、`MLD_LOG_LEVEL`、
`MLD_MEMORY_LIMIT`、`MLD_THREADS`、`MLD_QUERY_WORKERS`、
`MLD_PRESERVE_INSERTION_ORDER` 和 `MLD_FRONTEND_DIST_DIRECTORY`。

## 验证与辅助命令

```powershell
# 普通测试
python -m pytest

# 明确启用大规模性能测试
python -m pytest tests/performance --run-performance -s

# 独立运行 v3 Job 性能测试并输出 JSON
python benchmarks/jobs_v3.py --rows 1000000 --query-repetitions 7 --output jobs-v3-benchmark.json

# 导出 OpenAPI 并刷新前端类型
python scripts/export_openapi.py ../frontend/src/api/generated/openapi.json
npm --prefix ../frontend run openapi:types

# 构建 Python wheel（不下载依赖）
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir dist
```

测试范围和性能参数详见 `tests/README.md`。
