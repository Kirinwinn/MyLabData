# 后端测试与性能测试指南

测试只使用临时目录和临时 DuckDB，不访问正式 `DryData`。

## 测试层次

- `unit/`：配置、路径契约、输入契约和 Job 状态转换等纯逻辑。
- `integration/`：第三版 access、Service、Job、API、SSE 与前端托管的组合行为。
- `performance/`：通过真实 v3 access 和 Job 队列导入生成的大型 Parquet；默认跳过。

## 主要覆盖

| 范围 | 主要文件 |
| --- | --- |
| 单一数据根目录、目录边界与建立 | `unit/test_config.py`、`unit/test_access_paths.py` |
| Job 状态与 Query/Command worker | `unit/test_job_state.py`、`integration/test_job_manager.py` |
| API 路由、OpenAPI 与无路径请求 | `integration/test_api_contract.py`、`integration/test_jobs_api.py` |
| v3 表结构、回滚、重复、冲突与预览令牌 | `integration/test_v3_access_regressions.py` |
| v3 Command、Property 修改和 Package 预览 | `integration/test_v3_command_access.py` |
| Molecules/Annotation 完整 Job 生命周期与归档 | `integration/test_v3_runtime_flow.py` |
| Catalog、Search、Package 与 Job API | `integration/test_catalog_api.py`、`integration/test_jobs_api.py` |
| React 构建产物的同源托管 | `integration/test_frontend_hosting.py` |
| 大规模 v3 Job 导入和并行 Query | `performance/test_jobs_v3_benchmark.py` |

## 命令

在 `backend` 目录运行普通测试：

```powershell
python -m pytest
```

性能测试默认生成 100 万 Molecules、200 万 Annotations，以 512 MB DuckDB
内存、一个 DuckDB 线程、两个 Query worker 和一个 Command worker 运行，并
重复七次 Query。它必须显式启用：

```powershell
python -m pytest tests/performance --run-performance -s
```

可以通过环境变量调整规模：

```powershell
$env:MLD_BENCH_MOLECULE_ROWS = "2000000"
$env:MLD_BENCH_QUERY_REPETITIONS = "10"
python -m pytest tests/performance --run-performance -s
```

独立性能脚本会输出可复用的 JSON 报告；未指定工作目录时，临时数据在结束后
自动清除：

```powershell
python benchmarks/jobs_v3.py --rows 1000000 --query-repetitions 7 --output jobs-v3-benchmark.json
```
