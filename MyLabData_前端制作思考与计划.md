# MyLabData 前端制作思考与计划

> 文档状态：审核稿  
> 日期：2026-08-26  
> 当前范围：仅讨论 MyLabData 数据库应用前端，不开始编码

## 1. 背景与已经确定的方向

MyLabData 第一版后端已经完成，当前技术结构为：

```text
React + TypeScript
        ↓ HTTP / SSE
FastAPI API
        ↓
Service 业务层
        ↓
DuckDB 数据库
```

前端技术方向继续采用：

```text
React
TypeScript
Vite
React Router
TanStack Query
```

第一版仍按照以下运行边界设计：

1. 单用户本地运行。
2. FastAPI 默认只监听本机。
3. 第一版不制作登录、用户和角色权限系统。
4. 大文件不通过浏览器上传，而是由后端扫描 `Incoming`。
5. React 不接触 DuckDB，也不接收或提交任意绝对文件路径。
6. 所有业务操作必须经过版本化的 `/api/v1` 接口。
7. 数据库写操作由后端单写任务队列协调。

## 2. 当前前端的职责范围

MyLabData 前端是数据库管理、查询和人工确认界面，主要负责：

1. 查看服务和数据库状态。
2. 发现 `Incoming` 中的 Molecules 文件和 Annotation Package。
3. 查看数据包信息并启动导入预览。
4. 审核新增、已有和冲突的 Attribute 与 Entry。
5. 确认并启动数据导入。
6. 通过 SSE 或查询接口跟踪后台任务。
7. 查看 Imports 和 Jobs 历史。
8. 浏览 Molecules 及其全部 Annotation。
9. 浏览 Attribute 和 Entry Catalog。
10. 建立多个筛选条件并执行交叉查询。
11. 修改明确允许编辑的 Property。

## 3. 不属于当前前端的内容

`MLD_Processing_Module` 是独立项目，因此当前 MyLabData 前端不制作 Processing 页面，也不负责：

1. 上传和解释模型原始结果。
2. 配置或生成 Adapter。
3. 将原始模型字段映射成 Attribute 和 Entry。
4. 执行原始数据标准化、单位转换或分块处理。
5. 生成 Annotation Package。

两个项目之间只通过标准 Annotation Package 衔接：

```text
MLD_Processing_Module
        ↓
Annotation Package
        ↓
Incoming/Annotations
        ↓
MyLabData 前端预览与人工确认
        ↓
MyLabData 后端事务入库
```

## 4. 页面与导航规划

第一版建议设置六个主入口。

### 4.1 Dashboard

用于快速查看系统整体状态：

- FastAPI 和数据库健康状态。
- Molecule、Attribute、Entry、Annotation、Import 和 Job 数量。
- 最近的导入记录。
- 正在运行或等待确认的任务。
- 最近失败任务及错误摘要。

Dashboard 只展示摘要，不承担复杂操作。

### 4.2 Import

将 Incoming Packages、导入预览和导入历史组织在同一个业务区域中，可以使用页面内标签页区分：

```text
Import
├── Incoming
├── Preview / Confirmation
└── History
```

Incoming 页面展示：

- Package 名称。
- Package 类型：Molecules 或 Annotations。
- 文件大小。
- 修改时间。
- Package 内文件列表。
- 预览操作。

Annotation Preview 页面展示：

- 包名称和包哈希。
- Annotation 总行数。
- 已有、新增和冲突的 Attribute。
- 已有、新增和冲突的 Entry。
- 可关联与不可关联分子数量。
- 文件内部重复 Annotation。
- 数据库内已有 Annotation。
- 预计写入数量。
- warnings、errors 和 `can_import`。

只有满足以下条件时才允许用户确认导入：

```text
can_import = true
preview_token 存在
没有 Attribute/Entry 冲突
```

Molecules Preview 页面展示：

- 文件总行数。
- 合法分子数。
- 新分子数。
- 库内已有分子数。
- 文件内部重复数。
- 无效记录数。
- 预计写入数。

### 4.3 Molecules

Molecules 列表负责：

- 按 Lab ID 或 SMILES 查询。
- 分页显示分子。
- 显示 `molecule_id`、`lab_id`、canonical SMILES 和创建时间。
- 点击进入 Molecule Detail。

Molecule Detail 负责：

- 显示分子基本信息。
- 显示全部 Annotation。
- 按 Attribute 分组 Annotation。
- 展示 Entry、方法、版本、条件、值和更新时间。
- 仅对 `annotation_kind=property` 且 `is_mutable=true` 的 Entry显示编辑入口。
- prediction 和 calculation 始终只读。

第一版可以先显示和复制 SMILES，同时预留独立的二维结构组件。结构渲染方案应与普通页面组件隔离，方便以后替换实现。

### 4.4 Search

搜索条件采用统一的四段结构：

```text
Attribute
    ↓
Entry
    ↓
Operator
    ↓
Value
```

前端应根据 Attribute 的 `value_type` 只显示合法操作符：

| 类型 | 合法操作符 |
| --- | --- |
| number | `eq`、`ne`、`lt`、`lte`、`gt`、`gte`、`between` |
| text | `eq`、`ne`、`contains`、`starts_with`、`ends_with` |
| boolean | `eq`、`ne` |

多个条件默认使用 AND，同时提供 OR 选择。前端只发送结构化 JSON，不拼接 SQL。

搜索页面应支持：

- 新增和删除条件。
- 更改条件顺序。
- 清空全部条件。
- 在 URL 中保存已提交的条件、分页和逻辑模式。
- 展示查询耗时。
- 分页展示结果。
- 点击进入 Molecule Detail。

第一版暂不制作复杂查询缓存和结果导出，等后端提供相应能力后再增加。

### 4.5 Catalog

Catalog 页面按照 Attribute 展开 Entry：

```text
Attribute
├── 名称
├── value_type
├── unit
├── description
└── Entries
    ├── annotation_kind
    ├── method_name
    ├── method_version
    ├── conditions
    ├── source
    └── is_mutable
```

对于 number 类型 Attribute，可进一步展示已有统计信息，例如 count、min、max、mean、median 和标准差；boolean 类型展示 true/false 数量。

Catalog 第一版只读，不在界面中直接创建或修改 Attribute/Entry。新定义仍通过 Annotation Package 预览和确认产生。

### 4.6 Activity

Activity 页面统一展示后台任务和导入审计：

- Jobs：queued、validating、waiting_confirmation、importing、completed、failed、cancelled。
- Imports：总行数、合法行数、新增、已有、重复、写入、失败和错误信息。
- 对 queued 或运行中的任务提供取消操作。
- 对失败任务完整保留错误信息。

页面刷新后从后端重新读取任务状态，不依赖浏览器内存保存任务是否完成。

## 5. 建议路由

```text
/
/imports
/imports/:importId
/molecules
/molecules/:moleculeId
/search
/catalog
/activity
```

后台 Job 通常通过全局任务面板或 Activity 页面查看，不必为每个 Job 强制设置独立主页面；如果后续需要直接分享 Job 链接，可以再增加 `/jobs/:jobId`。

Property 编辑属于 Molecule Detail，不单独设置 `/properties` 页面。

## 6. 前端目录建议

```text
frontend/
├── package.json
├── tsconfig.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── app/
    │   ├── App.tsx
    │   ├── router.tsx
    │   ├── providers.tsx
    │   └── queryClient.ts
    ├── api/
    │   ├── generated/
    │   ├── client.ts
    │   ├── errors.ts
    │   └── jobResults.ts
    ├── layouts/
    │   └── AppLayout.tsx
    ├── features/
    │   ├── dashboard/
    │   ├── imports/
    │   ├── jobs/
    │   ├── molecules/
    │   ├── catalog/
    │   ├── search/
    │   └── properties/
    ├── components/
    ├── hooks/
    ├── lib/
    ├── styles/
    ├── types/
    └── tests/
```

各目录职责为：

| 目录 | 作用 |
| --- | --- |
| `app` | 应用入口、路由和全局 Provider |
| `api` | HTTP Client、OpenAPI 生成类型、错误转换和 Job 结果解析 |
| `layouts` | 导航、内容区、页头和全局任务区域 |
| `features` | 按 MyLabData 业务功能组织的页面、组件和 hooks |
| `components` | 跨 feature 复用的基础组件 |
| `hooks` | 多个 feature 共用的 React hooks |
| `lib` | 格式化、单位、日期、下载等无界面工具 |
| `styles` | 颜色、间距、字体和全局样式 |
| `types` | OpenAPI 无法表达的前端局部类型 |
| `tests` | 前端测试辅助代码和 Mock |

不建议在项目初期建立过多抽象层。只有真正被多个 feature 使用的内容才放入共享目录。

## 7. API Client 与类型管理

FastAPI 已经生成 OpenAPI 文档，因此前端主要 API 类型应由 OpenAPI 自动生成：

```text
Pydantic Schema
        ↓
FastAPI OpenAPI
        ↓
TypeScript API Types
```

这样可以避免 Python 和 TypeScript 各维护一套字段定义。

建议将 API 层分为三部分：

1. `generated`：自动生成，不手工编辑。
2. `client`：统一 base URL、JSON 解析、错误处理和取消请求。
3. feature hooks：把具体 endpoint 包装成 TanStack Query query/mutation。

所有错误统一转换为适合界面显示的形式：

```text
HTTP status
detail
字段验证错误
网络错误
未知错误
```

当前 `JobRecord.result` 在 OpenAPI 中是通用字典，前端需要根据 `job_type` 进行安全解析，例如区分：

- Molecules Preview。
- Annotation Preview。
- Molecules Import Result。
- Annotation Import Result。
- Property Update Result。

这层解析应集中放在 `api/jobResults.ts`，不能散落在页面组件中。

## 8. 状态管理

第一版不需要 Redux。

### 8.1 服务端状态

TanStack Query 管理：

- Packages。
- Imports。
- Jobs。
- Molecules。
- Attributes 和 Entries。
- Search Result。
- Stats。

它负责加载、错误、缓存、失效和重新获取。

### 8.2 页面局部状态

React 组件状态或局部 reducer 管理：

- 尚未提交的搜索条件。
- Preview 确认对话框。
- 展开或折叠状态。
- 当前选择的表格行。
- 表单输入。

### 8.3 URL 状态

以下内容适合放入 URL：

- Molecules 查询词。
- 当前页和每页数量。
- Search 已提交条件。
- AND/OR 模式。
- Catalog 当前展开的 Attribute。

这样刷新页面或复制链接后可以恢复视图。

## 9. 后台任务与 SSE

前端需要一个统一的 Job 监听层，而不是由每个页面自行实现 EventSource。

建议流程：

```text
POST 创建任务
    ↓
保存 job_id
    ↓
连接 GET /jobs/{job_id}/events
    ↓
接收 JobRecord 快照
    ↓
更新全局任务提示和对应页面
    ↓
终态后关闭 SSE
    ↓
刷新受影响的 TanStack Query 缓存
```

终态包括：

```text
waiting_confirmation
completed
failed
cancelled
```

如果 SSE 连接失败，前端应退回定时查询 `GET /jobs/{job_id}`。浏览器刷新后，通过 `GET /jobs` 找回未完成任务并恢复监听。

不同终态对应行为：

| 状态 | 前端行为 |
| --- | --- |
| `waiting_confirmation` | 打开或提示用户进入 Preview 确认 |
| `completed` | 显示成功、刷新数据库数据 |
| `failed` | 显示完整错误并保留重试入口 |
| `cancelled` | 显示取消结果，不误报成功 |

## 10. Annotation 导入交互

当前后端的 Preview 是异步任务，完整流程为：

```text
用户选择 Annotation Package
        ↓
POST /packages/{id}/preview
        ↓
返回 job_id
        ↓
SSE 等待 waiting_confirmation
        ↓
从 job.result 解析 AnnotationPackagePreview
        ↓
展示 Attribute、Entry、计数、warning 和 error
        ↓
用户确认
        ↓
POST /packages/{id}/imports + preview_token
        ↓
返回新的 job_id
        ↓
SSE 跟踪 importing
        ↓
completed / failed / cancelled
```

Preview 页面需要明显区分：

- 绿色：existing。
- 蓝色：new。
- 红色：conflict。
- 黄色：warning。

冲突不能用普通警告样式弱化，也不能允许用户忽略后继续导入。

如果 Package 在预览后改变，后端会拒绝旧 token。前端收到这一错误时，应提示“数据包已经变化，请重新预览”，而不是简单显示未知失败。

## 11. Property 修改交互

Property 修改也是后台任务：

```text
打开编辑框
    ↓
根据 value_type 显示正确输入控件
    ↓
填写修改来源 source
    ↓
PUT property endpoint
    ↓
返回 job_id
    ↓
监听任务
    ↓
成功后刷新 Molecule Detail
```

输入控件应按照类型变化：

| value_type | 控件 |
| --- | --- |
| number | 数值输入框 |
| text | 单行或多行文本框 |
| boolean | 明确的 True/False 选择 |

前端可以提前阻止明显错误，但后端仍是最终权限和类型边界。

## 12. 视觉与交互方向

MyLabData 是实验室内部的数据密集型工具，建议采用：

- 桌面端优先的响应式布局。
- 左侧主导航和顶部状态区域。
- 明亮、克制的科学工具风格。
- 表格与详情面板作为主要信息载体。
- 状态颜色保持全项目一致。
- SMILES、Lab ID、entry_key 等标识支持一键复制。
- 数值始终显示单位。
- conditions JSON 转换成易读标签，不直接展示未格式化 JSON。
- loading、empty、error、stale 和 retry 状态都必须有明确界面。

第一版不应为了视觉效果引入复杂动画，也不应过早建立大型自定义 Design System。可以先定义少量颜色、间距、圆角和字体 token，再按实际页面需要扩展。

界面语言需要在正式实现前确认。一个自然方案是：

- 导航、按钮和错误说明使用中文。
- Attribute、Entry、方法名称和科学单位保留数据库中的英文原名。
- 时间、数字和布尔值由统一格式化函数处理。

## 13. 开发与生产运行方式

### 13.1 开发环境

Vite 开发服务器运行 React，并将 `/api` 请求代理到 FastAPI：

```text
Browser → Vite :5173
              ├── React assets
              └── /api → FastAPI :8000
```

前端始终使用相对路径 `/api/v1`，避免在组件中写死主机和端口，也不需要给 FastAPI 增加宽泛的 CORS 配置。

### 13.2 生产环境

Vite 构建生成静态文件后，建议通过 FastAPI 或同一个本地反向代理提供：

```text
http://127.0.0.1:8000/         React
http://127.0.0.1:8000/api/v1   FastAPI
```

这样符合第一版单用户本地运行的定位，并减少启动和跨域配置复杂度。

## 14. 当前 API 与前端需求之间的适配点

后端业务核心已经完成，但页面实施后可能需要少量展示型接口增强。

### 14.1 分页总数

当前 Molecules 和 Imports 列表没有返回总数量。第一版可以根据“返回数量是否小于 limit”判断下一页，但无法显示准确总页数。

后续可以统一改为：

```json
{
  "items": [],
  "total": 1000000,
  "limit": 100,
  "offset": 0
}
```

### 14.2 Search Result 内容

当前 Search Result 主要返回 Molecule Summary，没有同时返回命中条件对应的 Annotation 值。因此第一版可以展示匹配分子并进入详情，但复杂结果表和结果导出需要后端增强。

### 14.3 Molecule Detail 元数据

当前 Annotation 结果中的字段较精简。为了直接显示单位、Attribute 名称、类型、方法和可变性，前端可能需要额外读取 Catalog 并进行关联。

如果实际实现发现请求和拼接过于复杂，可以让 Molecule Detail 返回更完整的展示字段。

### 14.4 Job Result 类型

`JobRecord.result` 是通用字典。前端可以集中解析，但从长期维护角度，后端可考虑返回带 `job_type` 判别字段的联合结果。

### 14.5 导出与分布

当前没有搜索结果导出接口，也没有完整分布图数据接口。这两项不应由前端自行拼接大量数据，建议留待后端对应阶段完成。

以上属于前端友好型接口增强，不表示当前后端核心未完成。

## 15. 前端测试规划

前端测试分成三层：

### 15.1 纯逻辑测试

- 根据 value_type 选择合法操作符。
- Search 条件序列化和 URL 恢复。
- Job result 类型解析。
- 数值、单位、日期和条件格式化。

### 15.2 组件与交互测试

- 加载、空数据、错误和重试状态。
- Annotation Preview 冲突展示。
- Import 确认按钮启用规则。
- Property 类型控件和提交规则。
- SSE 状态变化后的页面更新。

### 15.3 端到端测试

- 打开 Dashboard 并读取数据库摘要。
- 扫描 Package、预览和确认导入。
- 任务失败时展示后端错误。
- 多条件 Search 返回正确分子。
- 修改 mutable Property 并刷新详情。
- prediction/calculation 没有编辑入口。

端到端测试应使用临时 DuckDB，不接触正式 DryData。

## 16. 推荐实施阶段

### 阶段 1：前端骨架

- 创建 Vite + React + TypeScript 项目。
- 建立目录、Router、QueryClient 和基础布局。
- 配置 `/api` 开发代理。
- 建立 lint、format、typecheck 和 test 命令。

### 阶段 2：API 基础设施

- 从 OpenAPI 生成 TypeScript 类型。
- 建立统一 API Client。
- 建立错误转换。
- 建立 Query Key 规则。

### 阶段 3：只读基础页面

- Dashboard。
- Catalog。
- Molecules 列表。
- Molecule Detail。
- Activity 的只读列表。

### 阶段 4：Search

- 动态条件构建器。
- 类型对应操作符。
- AND/OR。
- URL 状态和分页。
- 结果列表。

### 阶段 5：Jobs 与 SSE

- 创建统一 Job 状态模型。
- SSE hook。
- 断线轮询回退。
- 全局任务提示。
- 任务恢复和取消。

### 阶段 6：Import 工作流

- Incoming Packages。
- Molecules Preview。
- Annotation Preview。
- Attribute/Entry 差异展示。
- 确认导入。
- 完成、失败和 token 失效处理。

### 阶段 7：Property 修改

- 类型化输入控件。
- source 输入。
- Job 跟踪。
- 成功后缓存失效和详情刷新。

### 阶段 8：测试、可访问性和生产构建

- 补齐单元、组件和端到端测试。
- 键盘操作、焦点和表格可访问性检查。
- loading、empty、error 和 retry 状态检查。
- Vite production build。
- FastAPI 静态资源托管或同源反向代理。
- 编写本地启动说明。

## 17. 第一版验收标准

第一版前端至少满足：

1. 可以查看后端健康状态和数据库摘要。
2. 可以查看 Incoming Packages，且不会提交绝对文件路径。
3. 可以异步启动 Preview 并正确解析 `job.result`。
4. Annotation 冲突、警告和错误不会被静默忽略。
5. 可以使用 `preview_token` 确认导入。
6. 可以通过 SSE 查看任务状态，断开后任务仍继续。
7. 刷新页面后可以恢复未完成任务。
8. 可以查看 Imports 和失败错误。
9. 可以按 Lab ID 或 SMILES 查找 Molecule。
10. 可以查看 Molecule 的 Annotation。
11. 可以按多个 Entry 条件执行 AND/OR 搜索。
12. 不同 value_type 只显示合法操作符和输入控件。
13. 只能编辑 mutable property。
14. prediction 和 calculation 没有编辑入口。
15. 页面具备明确的 loading、empty、error 和 retry 状态。
16. TypeScript、lint、测试和 production build 全部通过。

## 18. 正式实施前建议确认的问题

前端开始编码前，建议确认以下产品层选择：

1. 界面主要使用中文还是英文。
2. 第一版是否必须显示分子二维结构。
3. 是否需要暗色模式。
4. 是否接受第一版列表没有准确总页数。
5. Search Result 第一版只显示 Molecule Summary 是否足够。
6. 是否将 Jobs 和 Imports 合并在 Activity 页面。
7. 正式运行时是否由 FastAPI 同时托管 React 静态文件。

这些选择不会改变核心架构，但会影响页面组件、后端展示型接口以及第一版工作量。

## 19. 总结

MyLabData 前端的核心不是制作大量独立页面，而是建立三个稳定交互体系：

```text
Catalog 驱动的 Molecule/Search 展示
Package Preview 驱动的人工确认导入
Job/SSE 驱动的长任务状态管理
```

建议保持 React 前端薄而明确：数据库规则、文件安全、值类型校验和写入权限仍由 FastAPI 后端负责；React 负责组织信息、引导确认、展示状态并提供可靠的操作体验。

## 20. 参考资料

- React TypeScript：https://react.dev/learn/typescript
- Vite Backend Integration：https://vite.dev/guide/backend-integration
- Vite Development Proxy：https://vite.dev/config/server-options.html#server-proxy
- React Router：https://reactrouter.com/start/declarative/installation
- TanStack Query：https://tanstack.com/query/latest/docs/framework/react/overview
