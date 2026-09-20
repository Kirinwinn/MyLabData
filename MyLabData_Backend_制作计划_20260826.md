# MyLabData Backend 制作计划

**版本定位：** MyLabData v2 Backend 初步实施计划  
**整理日期：** 2026-08-26  
**当前状态：** 仅完成设计规划，尚未开始代码实现

---

## 1. 第一版目标

MyLabData v2 后端第一版需要完成以下六项核心能力：

1. 初始化和升级 DuckDB 数据库。
2. 扫描外部 `DryData/Incoming` 目录。
3. 验证 Molecules 文件和 Annotation Package。
4. 生成导入预览，并在用户确认后通过事务完成入库。
5. 支持分子浏览、Annotation 查询和多条件交叉筛选。
6. 支持可变 Property 的人工修改。

第一版暂不加入：

- WetData 重构；
- 用户登录和权限系统；
- 云服务器部署；
- Redis、Celery 等外部任务组件；
- 多进程并发写入；
- 复杂持久化查询缓存；
- MLD Processing Module 的 Adapter 实现。

---

## 2. 总体架构

```text
React + TypeScript
        ↓ HTTP / SSE
FastAPI API
        ↓
Service 业务层
        ↓
Repository / SQL 数据访问层
        ↓
mylabdata.duckdb
```

职责边界如下：

- React 只负责界面，不直接访问文件系统或 DuckDB。
- FastAPI API 层负责接收 HTTP 请求并调用 Service。
- Service 层负责扫描、验证、预览、导入、搜索等业务流程。
- 数据访问层负责 DuckDB 连接、事务和 SQL。
- DuckDB 是日常查询和管理的数据源。
- Parquet 是标准入库格式，不作为日常查询源。

---

## 3. 后端目录规划

```text
backend/
├── pyproject.toml
├── src/
│   └── mylabdata/
│       ├── __init__.py
│       ├── main.py
│       │
│       ├── core/
│       │   ├── config.py
│       │   ├── exceptions.py
│       │   └── logging.py
│       │
│       ├── db/
│       │   ├── connection.py
│       │   ├── migrate.py
│       │   ├── write_coordinator.py
│       │   ├── catalog.py
│       │   ├── molecules.py
│       │   ├── annotations.py
│       │   ├── imports.py
│       │   ├── search.py
│       │   └── migrations/
│       │       └── 001_initial.sql
│       │
│       ├── schemas/
│       │   ├── common.py
│       │   ├── manifest.py
│       │   ├── packages.py
│       │   ├── imports.py
│       │   ├── molecules.py
│       │   ├── catalog.py
│       │   ├── filters.py
│       │   └── properties.py
│       │
│       ├── services/
│       │   ├── package_scanner.py
│       │   ├── package_reader.py
│       │   ├── import_preview.py
│       │   ├── molecule_importer.py
│       │   ├── annotation_importer.py
│       │   ├── property_editor.py
│       │   ├── search_service.py
│       │   └── stats_service.py
│       │
│       ├── jobs/
│       │   ├── manager.py
│       │   ├── models.py
│       │   └── events.py
│       │
│       └── api/
│           ├── dependencies.py
│           └── v1/
│               ├── router.py
│               ├── health.py
│               ├── packages.py
│               ├── imports.py
│               ├── molecules.py
│               ├── catalog.py
│               ├── search.py
│               ├── properties.py
│               └── jobs.py
│
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── fixtures/
```

以上文件不必在项目开始时一次性全部创建，可以根据实施阶段逐步建立。

---

## 4. 实施阶段

### 4.1 项目基础骨架

建立最小可运行 Python package，包括：

- `pyproject.toml`；
- 配置读取；
- 日志初始化；
- 通用异常；
- FastAPI 最小入口；
- pytest 配置。

核心配置至少包括：

```text
MLD_DATA_ROOT
MLD_DATABASE_PATH
MLD_TEMP_DIRECTORY
MLD_MEMORY_LIMIT
MLD_THREADS
MLD_HOST
MLD_PORT
```

`MLD_DATABASE_PATH` 可以默认由 `MLD_DATA_ROOT` 推导：

```text
DryData/Registry/mylabdata.duckdb
```

验收标准：

- Python package 可以正常导入；
- 配置能够解析外部 DryData 路径；
- 缺少必需目录时给出明确错误；
- 最小 FastAPI 应用可以启动。

### 4.2 DuckDB 连接和 Migration

建立数据库基础设施：

- 显式创建和关闭 DuckDB Connection；
- 配置线程数、内存限制和临时目录；
- 建立 `_schema_migrations`；
- 按顺序执行 SQL migration；
- migration 重复执行时不重复建表；
- 数据库升级失败时能够回滚。

连接原则：

```text
一个 FastAPI 进程
多个短生命周期读连接
一个串行写协调器
每个任务拥有自己的 Connection
Connection 不跨线程共享
```

验收标准：

- 可以在空目录中创建数据库；
- 第二次启动不会重复执行 migration；
- migration 失败不留下半完成结构；
- 可以查询当前 schema 版本。

### 4.3 初始数据库模型

第一份 migration 创建八张业务表：

```text
Molecules
Attributes
Entries
Annotations
Sources
Imports
AttributeDistributions
AttributeStats
```

同时创建必要的 Sequence 和约束。

关键规则：

- `molecule_id` 全局唯一；
- canonical SMILES 唯一；
- `entry_id` 全局连续编号，不按 Attribute 重新编号；
- 一个 Entry 必须属于一个 Attribute；
- Annotation 通过 `molecule_id + entry_id` 建立关联；
- 一条 Annotation 只能有一个 `value_*` 非空；
- prediction 和 calculation 默认不可修改；
- 只有 `is_mutable=true` 的 property 可以人工修改。

大型 `Annotations` 表是否立即设置物理复合唯一约束和全部外键，需要通过性能测试决定；逻辑重复检查仍然必须实现。

验收标准：

- 八张表可以从空库创建；
- 能插入一个完整的 Molecule—Attribute—Entry—Annotation 示例；
- 非法值类型、重复 canonical SMILES 和错误关联会被拒绝。

### 4.4 Molecules 导入

先独立完成分子入库：

```text
扫描 Molecules 文件
    ↓
检查文件格式和必需列
    ↓
计算文件哈希
    ↓
生成预览
    ↓
集合式去重
    ↓
事务导入
    ↓
记录 Imports
```

预览和结果应区分：

- 文件总行数；
- 合法分子数；
- 新分子数；
- 库内已有分子数；
- 文件内部重复数；
- 无效记录数；
- 最终写入数。

不在 Python 中逐行写入，而是通过临时表和 `INSERT ... SELECT` 批量完成。

验收标准：

- 同一 canonical SMILES 不会生成两个分子；
- 同一文件重复导入不会重复写入；
- 失败时数据库整体回滚；
- Imports 中保留导入结果和文件哈希。

### 4.5 Annotation Package 契约与预览

实现对以下数据包的读取：

```text
annotation_manifest.json
annotations.parquet
processing_report.json
rejected.parquet
```

其中 `rejected.parquet` 可选，`annotations.parquet` 后续可以支持分片。

验证分为三个层次：

1. 数据包结构是否合法；
2. Manifest 内容是否合法；
3. Parquet 的列、类型和 Manifest 是否一致。

导入预览至少返回：

```text
包名称
包哈希
Annotation 总行数
已有/新增/冲突 Attribute
已有/新增/冲突 Entry
可关联/不可关联分子
文件内重复 Annotation
库内已有 Annotation
预计写入数量
警告和错误
```

预览应产生 `preview_token`。真正导入前重新检查包哈希，防止预览后文件被替换。

验收标准：

- 不修改数据库即可完成完整预览；
- 新 Attribute 和 Entry 会明确展示；
- 冲突不会被静默接受；
- 文件发生变化后，旧预览无法继续用于导入。

### 4.6 Annotation 事务入库

单次导入事务应包含：

```text
BEGIN
  创建或确认 Source
  创建新增 Attribute
  创建新增 Entry
  建立临时 Annotation 表
  关联 Molecules 和 Entries
  写入 Annotations
  写入 Imports
COMMIT
```

任何一步失败都执行 `ROLLBACK`。

事务提交成功后，才将数据包移入 `Processed`。失败情况需要区分：

- 数据包本身无效：进入 `Failed`；
- 数据库或系统临时故障：保留在 `Incoming`，允许重试。

验收标准：

- 一个包可以包含多个 Attribute 和 Entry；
- 导入过程不会产生部分成功状态；
- 重复导入具有明确的幂等行为；
- 百万级数据通过集合式 SQL 导入；
- 导入结果与预览数量一致。

### 4.7 Catalog、查询和 Property 修改

先实现不依赖 HTTP 的 Service：

- 查看 Attribute 列表；
- 查看某个 Attribute 的 Entries；
- 查看单个分子的全部 Annotation；
- 按 Lab ID 或 SMILES 查找分子；
- 多条件交叉筛选；
- 更新可变 Property；
- 获取数据库摘要和属性统计。

搜索条件采用统一形式：

```text
Attribute
Entry
Operator
Value
```

例如：

```text
EmissionWavelength
Proby + DMSO
between
500, 600
```

多个条件默认使用 AND 交集，同时为 OR 表达方式预留空间。第一版不急于制作复杂查询缓存，应先测量真实数据上的 DuckDB 查询时间。

验收标准：

- 多个 Entry 条件能够正确求交集；
- 数值、文本和布尔类型分别使用合法操作符；
- 不允许修改 prediction 或 calculation；
- 可变 property 修改保留时间和来源记录。

### 4.8 后台任务与写入协调

导入操作不阻塞普通 HTTP 请求：

```text
API 创建任务
    ↓
返回 job_id
    ↓
进入单写任务队列
    ↓
后台执行验证或导入
    ↓
通过查询接口或 SSE 报告进度
```

任务状态：

```text
queued
validating
waiting_confirmation
importing
completed
failed
cancelled
```

第一版采用进程内队列和单后台写线程，不引入 Redis 或 Celery。

验收标准：

- 同一时间只有一个数据库写任务；
- 普通查询仍能执行；
- 前端断开不会终止导入；
- 失败任务保留错误信息；
- 应用重启后不会把未完成任务误报为成功。

### 4.9 FastAPI 接口

数据库和 Service 稳定后，再增加 HTTP 层：

```text
GET  /api/v1/health
GET  /api/v1/packages
GET  /api/v1/packages/{id}
POST /api/v1/packages/{id}/preview
POST /api/v1/packages/{id}/imports

GET  /api/v1/imports
GET  /api/v1/imports/{id}

GET  /api/v1/jobs/{id}
GET  /api/v1/jobs/{id}/events

GET  /api/v1/molecules
GET  /api/v1/molecules/{id}

GET  /api/v1/attributes
GET  /api/v1/attributes/{id}/entries

POST /api/v1/search
PUT  /api/v1/molecules/{id}/properties/{entry_id}

GET  /api/v1/stats
```

API 层只负责：

- 解析请求；
- 边界检查；
- 调用 Service；
- 转换异常和状态码；
- 序列化响应。

前端不能提交任意绝对文件路径，只能使用后端扫描后生成的 Package ID。

### 4.10 测试和性能基准

测试分为：

- 单元测试：Manifest、筛选条件和状态转换等纯逻辑；
- 集成测试：临时 DuckDB、migration、导入、回滚和查询；
- 性能基准：真实规模下的导入、交叉查询、数据库体积和内存占用。

必须覆盖：

- 重复分子导入；
- 重复包导入；
- Attribute/Entry 冲突；
- Annotation 值类型错误；
- 缺失分子；
- 事务中途失败；
- 文件哈希改变；
- Property 非法修改；
- 多条件查询正确性；
- 低内存条件下的大文件导入。

---

## 5. 推荐开发顺序

第一轮先完成一个垂直闭环：

```text
配置
→ DuckDB migration
→ Molecules 导入
→ 单个 Annotation Package 预览
→ 事务导入
→ 两条件交叉查询
→ 集成测试
```

这个闭环通过后，再扩展：

```text
完整 API
→ 后台任务
→ SSE
→ 统计
→ 前端
```

这样可以尽早验证：

1. 数据模型是否合理；
2. DuckDB 导入和查询性能是否满足要求；
3. Annotation Package 是否能够统一不同处理结果。

后端第一里程碑不应只是“FastAPI 页面可以打开”，而应是：

> 在没有前端的情况下，能够从一个真实 Molecules 文件和一个真实 Annotation Package 创建数据库、完成事务导入，并执行多条件查询。

