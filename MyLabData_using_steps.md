### MyLabData管理数据

#### 1.前情提要

##### （1）管理与筛选

  MyLabData是一个基于Flask的网页应用，用于统一浏览、检索和比较湿实验（Wet）和干实验（Dry）的分子数据。

*注1：需要额外补充的地方为：*

*（1）"WetData"指的是在实验室中实际测量得到的光谱、稳定性、毒性等数据，按照分子和实验类型组织；*

*（2）"DryData"指的是通过计算或AI模型得到的分子性质和预测结果，按照批次（Batch）组织；*

*（3）启动后通过浏览器访问 **http://127.0.0.1:8501** 即可使用，不需要额外配置。*

##### （2）两部数据

1）Wet板块：用于管理和展示湿实验数据。包含查看（ViewMode）和比较（CompareMode）两个模式；

2）Dry板块：用于管理和展示干实验数据。包含查看（ViewMode）、搜索（SearchMode）、比较（CompareMode）三个模式

*注2：每个模式的具体功能会在后面的章节中逐一说明*

#### 2.安装与启动

##### （1）通过Github克隆

1）创建存放MyLabData的文件夹，在终端中运行下述命令克隆项目：

```bash
git clone https://github.com/Kirinwinn/MyLabData.git
```

2）进入项目文件夹，通过environment.yml创建conda环境：

```bash
cd MyLabData
conda env create -f environment.yml
```

*注3：环境名为"MyLabData"，Python版本为3.11，主要依赖包括Flask、pandas、RDKit、PyArrow等*

##### （2）启动平台

1）激活环境MyLabData：

```bash
conda activate MyLabData
```

2）运行launch.py启动网页服务器：

```bash
python MyLabData/launch.py
```

3）启动成功后，在浏览器中打开下述地址即可访问：

```
http://127.0.0.1:8501
```

*注4：如果端口8501被占用，程序会提示错误，需要先关掉占用端口的程序再重新启动*

#### 3.数据组织方式

##### （1）Dry数据结构

  Dry数据需要一个根目录（通过环境变量`DRY_DATA_ROOT`配置），根目录下包含以下子文件夹：

```text
{DRY_DATA_ROOT}/
├── Separate/                # SMILES列表，每个批次一个Parquet文件
│   └── {BatchCode}.parquet  #   必须包含SMILES列
├── Property/                # 分子性质，每个批次一个Parquet文件
│   └── {BatchCode}.parquet  #   包含44个性质列 + SMILES列
└── Prediction/              # AI预测数据
    └── {Model}/             #   每个模型一个文件夹（如Proby、Tox21）
        ├── {BatchCode}/     #     原始预测数据（xlsx或csv）
        └── {BatchCode}.parquet  # 标准化后的Parquet文件
```

*注5：需要额外补充的地方为：*

*（1）BatchCode的命名格式为 **Batch[来源][编号]**，例如"BatchE001"表示第001批外部数据，"BatchG004"表示第004批生成数据，其中E代表External（外部），G代表Generated（生成）*

*（2）原始预测结果需要放入`{Model}/{BatchCode}/`文件夹，然后运行`Supporting/Prediction_Normalize.ipynb`将其标准化为同级目录下的Parquet文件*

*（3）44个性质分为四大类：官能团类（Trait1-24，如羟基、硝基、氰基等）、基本性质类（Trait25-29，如分子量、LogP等）、空间性质类（Trait30-38，如TPSA、可旋转键数等）、电子性质类（Trait39-44，如氢键受体数、偶极矩等）*

##### （2）Wet数据结构

  Wet数据也需要一个根目录（通过环境变量`WET_DATA_ROOT`配置），根目录下按分子名→实验类型→批次的层级组织：

```text
{WET_DATA_ROOT}/
└── {Molecule}/
    └── {ExpType}/           # 实验类型文件夹
        └── {Batch}/
            ├── RData/       # 原始数据（CSV、XLSX、SPC等）
            ├── PData/       # 处理后的工作数据
            └── SData/       # 展示文件（Markdown、图片等）
```

*注6：需要额外补充的地方为：*

*（1）目前支持的实验类型有六种：**solventscom**（溶剂比较）、**fluostable**（荧光稳定性）、**uvstable**（紫外稳定性）、**mtt**（细胞毒性）、**e**（摩尔吸光系数）、**selectivei**（选择性干扰）*

*（2）Wet数据在首次启动时会自动扫描文件夹并建立索引数据库Wet.db，之后可以通过页面的Refresh按钮手动刷新*

*（3）文件夹和文件的详细命名规范请参考Supporting文件夹中的**MLD湿实验识别符.md***

#### 4.Wet板块功能

##### （1）ViewMode——浏览湿实验数据

  ViewMode用于逐级浏览湿实验数据，操作流程为：

1）在左侧边栏选择分子名称；

2）选择实验类型（solventscom、fluostable等）；

3）浏览该分子在所选实验类型下的所有批次，每个批次下可以预览RData、PData、SData中的文件。

*注7：支持在线预览的文件格式包括CSV、XLSX、Markdown、图片（PNG等）和SPC光谱文件*

*注8：每个批次会显示状态标签，包括Normal（正常）、UnDone（未完成）、UnValuable（不可用）、Test（测试）四种*

##### （2）CompareMode——多批次实验对比

  CompareMode用于在多个批次之间进行数据对比分析，目前支持六种实验类型的对比，分别是：

| 实验类型 | 对比内容 |
| :------: | :------: |
| solventscom | 不同溶剂中的荧光和紫外光谱比较 |
| fluostable | 荧光稳定性趋势分析 |
| uvstable | 紫外稳定性趋势分析 |
| mtt | 细胞毒性结果对比 |
| e | 摩尔吸光系数测定数据对比 |
| selectivei | 选择性干扰实验结果对比 |

*注9：对比结果通过ECharts交互式图表展示，支持缩放和悬停查看数值*

#### 5.Dry板块功能

##### （1）ViewMode——浏览分子性质分布

  ViewMode用于查看某个批次中所有分子的44项性质分布，操作流程为：

1）选择一个批次（如BatchE001）；

2）页面会显示该批次44项分子性质的分布直方图；

3）点击直方图中的某个区间，可以浏览落在该区间内的具体分子。

*注10：44项性质的分布直方图会根据性质类型自动选择合适的展示方式：整数型性质（如官能团计数）显示为离散柱状图，连续型性质（如分子量、LogP）显示为连续直方图*

##### （2）SearchMode——条件筛选分子

  SearchMode用于按条件从多个批次中筛选分子，操作流程为：

1）选择一个或多个批次作为筛选范围；

2）设定性质筛选条件（如分子量在200-500之间、LogP大于2等）；

3）查看符合条件的分子的性质分布；

4）将筛选结果下载为ZIP压缩包。

*注11：筛选条件支持范围设定，可以同时设置多个性质的条件进行组合筛选*

##### （3）CompareMode——单分子全景查询

  CompareMode用于查询单个分子的完整信息，操作流程为：

1）通过LabID或SMILES搜索目标分子；

2）页面会展示该分子的完整档案，包括44项分子性质数值以及所有可用模型的AI预测结果；

3）可以下载该分子的数据包，包含CSV数据文件、2D结构SVG图片和3D结构SDF文件。

*注12：搜索优先级为LabID精确匹配 → SMILES精确匹配。2D结构图由RDKit实时生成并缓存在Supporting/structures/文件夹中*

##### （4）Prediction——AI预测结果浏览

  Prediction模式用于浏览AI模型预测结果的分布，操作流程为：

1）选择预测模型（目前支持Proby和Tox21）；

2）如果模型结果按溶剂区分（如Proby），还需要选择溶剂；

3）页面会展示预测结果各项参数的分布直方图。

*注13：需要额外补充的地方为：*

*（1）Proby模型预测10项光学参数：abs（吸收波长）、emi（发射波长）、plqy（量子产率）、e（摩尔吸光系数）、log10e、lifetime（寿命）、abs fwhm和emi fwhm（两种单位）*

*（2）Tox21模型预测12项毒理学终点：NR-AR、NR-AR-LBD、NR-AhR、NR-Aromatase、NR-ER、NR-ER-LBD、NR-PPAR-gamma、SR-ARE、SR-ATAD5、SR-HSE、SR-MMP、SR-p53*

*（3）原始预测数据需要先通过`Supporting/Prediction_Normalize.ipynb`标准化后才能在此模式中浏览*

#### 6.项目结构

```
MyLabData/
├── App/
│   ├── app.py              # 路由与后端主逻辑
│   ├── templates/          # 网页模板（base.html, index.html）
│   └── static/             # 静态资源
├── Database/
│   ├── Wet/                # Wet数据管道（扫描建库）
│   ├── Dry/                # Dry数据管道（性质计算建库）
│   └── Tools/              # 辅助工具（预测数据标准化等）
├── Search/
│   ├── Wet_ViewMode.py     # Wet浏览模式后端
│   ├── Wet_CompareMode.py  # Wet对比模式后端
│   ├── Dry_ViewMode.py     # Dry浏览模式后端
│   ├── Dry_CompareMode.py  # Dry查询模式后端
│   ├── Dry_SearchMode.py   # Dry筛选模式后端
│   └── Dry_Prediction.py   # Dry预测模式后端
├── Supporting/
│   ├── structures/         # 缓存的2D结构SVG图片
│   ├── specs/              # 命名规范文档
│   ├── Prediction_Normalize.ipynb  # 预测数据标准化notebook
│   └── Solvent.md          # 溶剂SMILES与缩写对照表
├── environment.yml         # conda环境配置文件
└── launch.py               # 启动脚本
```

#### 7.注意之处

##### （1）数据根目录需正确配置

  Dry数据和Wet数据各有一个根目录，需要通过环境变量`DRY_DATA_ROOT`和`WET_DATA_ROOT`配置到正确的路径，否则平台无法读取数据。

##### （2）预测数据需先标准化

  原始的AI预测结果（如Proby输出的xlsx文件）不能直接被MyLabData读取，需要先运行`Supporting/Prediction_Normalize.ipynb`将其转换为标准化的Parquet格式。

##### （3）Wet数据的文件命名需符合规范

  MyLabData通过解析文件名来识别分子名、实验类型、溶剂、批次等信息，所以Wet数据的文件和文件夹命名必须严格遵守命名规范，详见`Supporting/MLD湿实验识别符.md`。

##### （4）端口冲突处理

  如果启动时提示端口8501已被占用，需要先关掉占用端口的程序。可以通过环境变量`APP_PORT`修改端口号。

##### （5）RDKit相关功能

  2D结构图生成和3D结构文件导出依赖RDKit库。如果RDKit未正确安装，这些功能会自动禁用，但不影响平台其他功能的使用。

