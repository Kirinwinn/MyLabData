### My Lab Data湿实验识别符

##### 1.文件夹基本结构

##### （1）普适性：

所有类型的文件夹都遵循基本的文件夹结构；

##### （2）基本结构：

![](assets/MLD_Folder_Structure.png)

1）category为主文件夹，名字是实验类型；

2）MoleculeX为分子文件夹，每个分子只能有一个文件夹，文件夹名字就是分子的名字

3）XthTime是第X次测试的结构文件夹，名字示例为：

**Name_Category_Xth_Time_Year_MonthDay_Mark**

1)）例如5107_e_1st_Time_2025_1226_UnDone；

2)）其中Mark目前有三个，分别是UnDone，代表数据尚未收集完成；UnValuable，代表这次数据不会被使用；Test，代表数据属于测试参数所用数据;

3)）当Category是MTT时，Solvents自动转变为CellLine，细胞的名字

4）RData是原始文件文件夹，名字固定；

5）PData是工作文件文件夹，名字固定；

6）SData是展示文件文件夹，名字固定。

##### 2.e文件命名规则

![](assets/MLD_e_Files_Structure.png)

###### （1）spcFiles

是spc格式原始文件，名字格式为**Name_Solvent(System)_e_Concentration_MarkerX_BatchTestTime**

1)）例如5107_DMSO_e_10UM_2_3；

2)）其中BatchTestTime是一的话，则默认不写;

3)）MarkerX可以是自然数，也可以是Blank，如果是Blank，则代表是空白样品，

###### （2）xlsxFiles

是xlsx格式原始文件，名字格式为**Name_Solvent(System)_e_Origin**

1)）例如5107_DMSO_e_Origin

###### （3）xlsxFiles

是xlsx格式工作文件，名字格式为**Name_Solvent(System)_e_Working**

1)）例如5107_DMSO_e_Working

###### （4）SData

1)）prismFiles，pngFiles和mdFiles分别是prism，png和md展示文件；

2)）三个文件的名字一致，格式为**Name_Solvent(System)_e_Xth_Time_Year_MonthDay**；

3)）例如5107_DMSO_e_1st_Time_2025_1226

##### 3.FluoStable命名规则

![](assets/MLD_FluoStable_Files_Structure.png)



###### （1）tmcFiles 

是tmc格式原始文件，名字格式为**Name_Solvent(System)_FluoStable_Con_MarkerX_BatchTestTime**

1)）例如5107_DMSO_FluorescenceStability_10UM_2_3；

2)）其中BatchTestTime是一的话，则默认不写。

###### （2）xlsxFiles

是xlsx格式原始文件，名字格式为**Name_Solvent(System)_FluoStable_Origin**

1)）例如5107_DMSO_FluoStable_Origin

###### （3）xlsxFiles

是xlsx格式工作文件，名字格式为**Name_Solvent(System)_FluoStable_Working**

1)）例如5107_DMSO_FluoStable_Working

###### （4）SData

1)）prismFiles，pngFiles和mdFiles分别是prism，png和md展示文件；

2)）三个文件的名字一致，格式为**Name_Solvent(System)_FluoStable_Xth_Time_Year_MonthDay**；

3)）例如5107_10%DMSO_FluoStable_1st_Time_2025_1201，三个文件的名字都保持一致

##### 4.MTT命名规则

![](assets/MLD_MTT_Files_Structure.png)

###### （1）xlsxFiles

1）是xlsx格式原始文件，名字格式为**Name_CellLine_MTT_Origin**

2）例如5107_SY5Y_MTT_Origin；

###### （2）xlsxFiles

是xlsx格式工作文件，名字格式为**Name_CellLine_MTT_Working/Ref**

1)）例如5107_SY5Y_MTT_Working

2)）有两种形式的后缀，第一种后缀为Working，即为工作文件；第二种后缀为Ref，即为参考文件

###### （3）SData

1)）prismFiles，pngFiles和mdFiles分别是prism，png和md展示文件；

2)）三个文件的名字一致，格式为**Name_CellLine_MTT_Xth_Time_Year_MonthDay_Mark**

3)）例如5107_SY5Y_MTT_1st_Time_2025_1103，三个文件的名字都保持一致，Mark主要是“Ref”，作参考

##### 5.UVStable命名规则：

![](assets/MLD_UVStable_Files_Structure.png)

###### （1）spcFiles

是spc原始格式文件，名字格式为**Name_Solvent(System)_UVStable_Conc_Xth_Time_Loop_Xtimes_Xmin_Year_MonthDay**

例如OTA61_DMSO_UVStability_10UM_1st_Time_Loop_16times_5min_2025_1121；

###### （2）xlsxFiles

xlsx格式原始文件，名字格式为**Name_Solvent(System)_UVStable_Conc_Xth_Time_Loop_Xtimes_Xmin_Year_MonthDay_Origin**

1）例如OTA61_DMSO_UVStability_10UM_1st_Time_Loop_16times_5min_2025_1121_Origin

###### （3）mdFiles

是md格式原始文件，说明此实验的各项参数，例如浓度，测试时间，温度以及湿度等

###### （4）xlsxFiles

xlsx格式工作文件，格式为**Name_Solvent(System)_UVStable_Conc_Xth_Time_Loop_Xtimes_Xmin_Year_MonthDay_Working**

1）例如OTA61_DMSO_UVStability_10UM_1st_Time_Loop_16times_5min_2025_1121_Working

###### （5）SData：

1)）prismFiles、opjuFiles、pngFiles和mdFiles分别是prism、opju、png和md展示文件；

2)）四个文件的名字一致，格式为**Name_Solvent(System)_UVStable_Conc_Xth_Time_Year_MonthDay**

3)）例如OTA61_DMSO_UVStable_10UM_1st_Time_20251121

##### 6.SelectiveI命名规则：

![](assets/MLD_SelectiveI_Files_Structure.png)

###### （1）spcFiles

是spc原始文件，格式为**Name_Solvent/System_SelectiveI_Conc_X(Probe)/X(Protein)__Disrupt_MakerX_BatchTestTime**

1)）例如STL36_10%DMSO_SelectiveI_4UM_1_FeCl2_1；

2)）如果BatchTestTime是1的话，则默认不写。

###### （2）xlsxFiles

是xlsx原始文件，格式为**Name_Solvent/System_SelectiveI_Conc_X(Probe)/X(Protein)_Origin**

###### （3）mdFiles

是md格式原始文件，说明此实验的各项参数，例如探针与蛋白质（干扰物质）比例，浓度，测试时间，自己对于实验结果的评价以及调整策略等

###### （4）xlsxFiles

是xlsx工作文件，名字格式为**Name_Solvent/System_SelectiveI_Conc_X(Probe)/X(Protein)_Working**

###### （5）SData：

1)）prismFiles、opjuFiles、pngFiles和mdFiles分别是prism、opju、png和md展示文件；

2)）四个文件的名字一致，格式为**Name_Solvent/System_SelectiveI_Conc_X(Probe)/X(Protein)_Xth_Time_Year_MonthDay**

##### 7.SolventsCom命名规则

![](assets/MLD_SolventCom_Files_Structure.png)

*注1：其中需要解释的地方为：*

*（1）Fluo，UV以及Pics的文件夹名字不固定，名字格式为分子名字+Fluo/Pics/UV，例如A11_Fluo；*

*（2）Solvent包括七种溶剂，名字分别是EtOH、MeOH、PBS、EA、MeCN、DMSO和DCM*

###### （1）Fluo_spcFiles

是spc原始文件，名字格式为**SolventCode ExSlit EmSlit MarkerX EM/EX**，例如DCBB1EM.spc

1）SolventCode为溶剂的代号，七种溶剂对应的代号分别是：

| Solvent | EtOH | MeOH | PBS  |  EA  | MeCN | DMSO | DCM  |
| :-----: | :--: | :--: | :--: | :--: | :--: | :--: | ---- |
|  Code   |  ET  |  MO  |  PB  |  EA  |  MC  |  DM  | DC   |

2）ExSlit和EmSlit为狭缝代号，狭缝宽度对应的代号分别是：

| SlitWidth | 1.5  | 3    | 5    | 10   | 15   | 20   |
| --------- | ---- | ---- | ---- | ---- | ---- | ---- |
| Code      | A    | B    | C    | D    | E    | F    |

3）MarkerX为测试样品编号，分别为1、2以及3等依次往下的整数以及字母T

1)）当编号为T时，代表此数据是测试数据，不是正式数据；

2)）当编号为整数时，代表此数据是正式数据

4）EM/EX标明数据是测的发射光谱还是激发光谱，EM对应发射光谱，EX对应激发光谱

###### （2）Fluo_xlsxFiles

是xlsx原始文件，名字格式为**Molecule‘s Name_SolventsCom_Fluo_Origin**

1）例如A11_SolventsCom_Fluo_Origin

###### （3）UV_spcFiles

是spc原始文件，名字格式为**Molecule‘s Name_Solvent_Conc_MarkerX_TestTime**

1）例如A11_DMSO_10UM_1_2；

2）MaekerX可以是自然数或者Blank：当它是自然数时，表示测试样品的编号；当它是Blank时，表示空白样品

###### （4）UV_xlsxFiles

是xlsx原始文件，名字格式为**Molecule‘s Name_SolventsCom_UV_Origin**

1）例如A11_SolventsCom_UV_Origin

###### （5）mdFiles

是md格式原始文件，名字格式为**Molecule’s Name_SolventsCom**，说明此实验的各项参数，例如探针的浓度，测试时间，λmax，Em以及Ex等

###### （6）xlsxes

1）xlsx1是xlsx格式工作文件，名字格式为**Name_SolventsCom_Fluo_Working**

例如A11_SolventCom_Fluo_Working

2）xlsx2是xlsx格式工作文件，名字格式为**Name_SolventsCom_UV_Working**

例如A11_SolventCom_UV_Working

3）xlsx3是xlsx格式工作文件，名字格式为**Name_SolventsCom_Fin**

例如A11_SolventCom_Fin

###### （8）SData

1）prismFiles、opjuFiles、pngFiles均是展示文件，mdFiles是补充说明文件，名字格式为**Molecule‘s Name_SolventsCom_Fin/Fluo/UV**；

2）opjuFiles记录的是各个溶剂的Em，λmax，Ex以及Em和Ex，波谱图；

3）md为解释说明的文件

##### 8.Confoal1mage命名规则

![](assets/MLD_Confocal1mage.png)

###### （1）lifFiles

是共聚焦实验的原始结果，格式为**Molecule's Name_Confal1mage_Xth_Time_Origin**

例如STL36_Confal1mage_3rd_Time_Origin

###### （2）mdFiles

是共聚焦实验的解释文档，格式为**Molecule‘s Name_Confal1mage_Xth_Time**

例如STL36_Confal1mage_3rd_Time

###### （3）lifFiles

是共聚焦实验的处理文件，格式为**Molecule's Name_Confal1mage_Xth_Time_Working**

例如STL36_Confal1mage_3rd_Time_Working

###### （4）SData

是共聚焦实验的展示结果，格式为**CellLine_Function_PositionX_Dye's Name**

*注2：值得注意的地方是：*

*（1）Function不是特定名称，只是一个占位符，故不需要进行检查，只是有一个位置占住即可；*

*（2）Dye's Name也是占位符，但是数量不限，内容无需检查，例如BV2_Mito_Position1_**Nuclear_Mito**中的Nuclear和Mito*

##### 9.IF-P命名规则

![](assets/MLD_IF-P_Files_Structure.png)

###### （1）Folder

1）此数据是从其他人手中接收，故无特殊命名要求，只是需要在原名字后加“_Origin”后缀即可

2）此处的一个源文件不是指具体的一个格式的文件，例如一个tmc格式文件，而是指一个文件夹；

###### （2）mdFiles

记录实验的相关参数，命名格式为**Molecule' Name_IF-P_Xth_Time**

例如STL36_IF-P_2nd_Time

###### （3）kfbfFiles

1）后缀改为“_Working”；

2）单指一个kfbf格式文件；

###### （4）SData

展示文件，命名格式为**Purpose_Target_PositionX_Dye's Name**

1）相似地，Dye's Name的数量不限，内容无需检查，例如Coposition_TDP43_Position1_Probe_SecondAntibody中Probe以及SecondAntibody都是Dye's Name































可能会出现的几种情况：

（1）管理我们自己的湿实验数据：

文件结构：

1）湿实验数据，实体数据是按照实验种类进行储存的；

2）分子目录数据，虚体数据是按照分子进行归类；

实现功能：



4）检查分子的湿实验数据是否符合命名规范

（2）管理我们自己的干实验数据：

文件结构：

1）干实验数据，结构如下：

1)）数据集原始数据，跟格式没有关系；

2)）预测数据，大文件夹是按照预测的参数命名，例如PLQY，合成难度等等，但是里面的子文件夹是按照数据集进行分类的；

3)）非预测数据，例如对它的结构进行分析这种，它与预测数据的区别在于是否是原始数据中已知的；

4)）分子目录数据，虚体数据也是按照分子进行分类的；

