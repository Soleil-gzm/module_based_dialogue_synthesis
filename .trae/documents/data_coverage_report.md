# 数据检测报告（Coverage Check）实现计划

## Context（为什么做这件事）

目前 `scripts_general/core/analysis/analyze_module_diversity.py` 只能分析**单个模块**内"条件 × UID"的多样性分布，无法回答两个更宏观的问题：

1. Excel 话术模板定义了哪些模块，trace 数据里**实际用到**了哪些、哪些**完全没用**？
2. 每个模块在 Excel 里一共定义了多少个**不同条件**，trace 里命中了哪些、哪些**没被命中**？

用户每次拿到新业务数据（新 Excel/新 trace）后，需要一个快速对照报告，判断"当前代码和配置能否匹配这批新数据"。本计划新增一个独立的 coverage 检测工具，输出纯 TXT 报告，并可选择性集成进 main.py 自动分析流程。

## 设计要点

### 1. 模块全集来源（关键）

* **优先用 prob 表**：`load_prob_matrix(prob_path)` 提取 modules（权威来源，与 `load_sheets` 校验逻辑一致）。

* **prob 表缺失时**从 Excel sheet 名推断，减去 `known_extra = {"链接施压话术","链接话术","逻辑"}`（见 [data\_loader.py:44](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/data/data_loader.py#L44)）。

* **不能用 trace 当全集**：会漏掉"应该有但完全没跑"的模块，那正是要检测的异常。

### 2. 条件归一化（两端必须一致）

生成端 [dialogue\_builder.py:184](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/generation/dialogue_builder.py#L184) 直接写原始 `conditions(条件)` 值；[analyze\_module\_diversity.py:69](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/analysis/analyze_module_diversity.py#L69) 把空串和 `"无条件"` 都归一为 `"无条件(空)"`。

新工具对 **Excel 端和 trace 端都应用同一个** **`normalize_condition(s)`**：

* `None`/`NaN`/空串/`"无条件"` → `"无条件(空)"`

* 其余 → `str(s).strip()`

* 只做 strip，不做更激进的标准化（与生成端保持一致，避免假阳性）

### 3. 不直接复用 load\_sheets

`load_sheets`（[data\_loader.py:40-42](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/data/data_loader.py#L40)）在 Excel 缺模块时会 raise。coverage 场景下"Excel 缺模块"恰是要检测的异常，不该中断。新写 `_load_module_sheets(excel_path, modules)`：逐 sheet `pd.read_excel(engine="calamine")`，缺失模块记入 `missing_excel_modules`，继续处理其余模块。

### 4. "使用"的定义

* **模块使用了**：trace 中该模块至少有一条 `status=="processed"` 且 `selected_uid` 非空。

* **条件使用了**：该模块被 processed 的记录中，归一化后的 `condition_text` 至少出现一次。

## 实现步骤

### 步骤 1：新建分析文件

创建 [scripts\_general/core/analysis/analyze\_coverage.py](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/analysis/analyze_coverage.py)

函数结构：

```python
def normalize_condition(s) -> str: ...           # 两端共用归一化

def _load_module_sheets(excel_path, modules) -> tuple[dict, list[str]]:
    """返回 (sheet_df_dict, missing_modules)。逐 sheet 读，缺失不抛错。"""

def _collect_excel_conditions(df) -> dict:
    """{normalized_cond: [uid, ...]}，从 conditions(条件)+uid 列。uid 列缺失时退化为只统计条件集合。"""

def _collect_trace_usage(traces) -> dict:
    """{module_name: {normalized_cond: used_count}}，仅 processed 且 selected_uid 非空计入。"""

def analyze_coverage(trace_path, excel_path, prob_path=None, output_dir=None) -> str:
    """主函数，返回生成的 txt 路径。
    - modules 全集：prob_path 优先；否则 Excel sheets - known_extra。
    - 检测 trace_only_modules（trace 有但 modules 全集无的模块）。
    - 输出到 output_dir（默认 trace 同级的 analysis 目录），文件名 coverage_report_{timestamp}.txt。
    """

def main():  # argparse 入口
```

CLI 用法：

```
python analyze_coverage.py <trace.json> --excel <excel_path> [--prob <prob_path>]
```

独立脚本不依赖 config，prob 可选；输出目录默认 `Path(trace).parent.parent / "analysis"`（与 [analyze\_module\_diversity.py:182](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/core/analysis/analyze_module_diversity.py#L182) 一致）。

### 步骤 2：报告 TXT 结构

```
========================================================================
数据检测报告 (Coverage Check)
========================================================================
生成时间: 2026-09-24 15:30:00
Excel:   /.../话术模板.xlsx
Trace:   /.../traces_xxx.json  (N 条对话)
模块全集来源: prob表 / Excel推断  (共 12 个模块)

【一、模块使用总览】 Excel定义 12 | 使用 10 | 未使用 2
------------------------------------------------------------------------
  [✓] 身份确认   Excel条件=4  trace命中=4  覆盖率 100%
  [✗] 查账       Excel条件=5  trace命中=0  覆盖率   0%   ⚠ 完全未使用
  ...
------------------------------------------------------------------------
未使用模块 (2): 查账、信息问题

【二、每模块条件覆盖详情】
------------------------------------------------------------------------
[身份确认] Excel条件=4  trace命中=4  未使用=0
  ✓ 逾期&未逾期    trace出现 1520 次  Excel对应uid=[5,6]
  ✓ 无条件(空)     trace出现  880 次  Excel对应uid=[1,2,3,4]
  ✗ 已还款         Excel定义但trace未出现  Excel对应uid=[7]   ⚠
------------------------------------------------------------------------
[查账] Excel条件=5  trace命中=0  未使用=5
  ✗ 所有条件均未使用（模块整体未进入路径）

【三、异常检测】
------------------------------------------------------------------------
trace有但Excel/prob无的模块 (0 个): -
trace有但Excel无的条件 (0 个): -
Excel缺失模块sheet (0 个): -
prob表缺失: 否
========================================================================
判定: 2 个模块未使用、0 个条件异常 → 建议检查配置/路径生成
========================================================================
```

### 步骤 3：集成到 main.py 自动分析

在 [main.py:255](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/scripts_general/main.py#L255)（diversity 分析之后、`except` 之前）插入：

```python
# 数据检测报告
if config.get("analysis.coverage_enabled", False):
    from core.analysis.analyze_coverage import analyze_coverage
    cov_report = analyze_coverage(
        trace_path=trace_file,
        excel_path=excel_path,
        prob_path=prob_path,
        output_dir=analysis_output,
    )
    logger.info(f"数据检测报告已生成: {cov_report}")
```

* 开关默认 `False`，不破坏现有行为；复用已加载的 `excel_path`/`prob_path`。

* 包在现有 try/except 内，失败只 log 不阻断。

* 配置项文档加在 [general\_full\_template.yaml](file:///home/GUO_Zimeng/coding/projects/module_based_dialogue_synthesis/config_templates/general_full_template.yaml) 的 `analysis` 段下：`coverage_enabled: false`。

## 边界情况处理

* trace 为空 → 所有模块标 `✗ 完全未使用`，不崩。

* Excel sheet 缺失 → 记入 `missing_excel_modules`，该模块条件行写 `Excel sheet 缺失，无法统计`。

* trace 出现 Excel 没有的模块名 → 记入 `trace_only_modules`（说明 trace 与当前 Excel 版本不匹配）。

* 同一条件对应多个 uid → 报告列出全部 uid，帮助定位。

* selected\_uid 为 null → 防御性跳过。

## 验证方式

1. 用 `datas/逾期-0920/` 下的 Excel + 任一历史 trace（若无则先跑一次生成）运行独立脚本，确认报告生成且结构正确。
2. 故意构造异常：删一个 sheet / 改一个条件字符串，确认报告的【三、异常检测】能检出。
3. main.py 集成：在配置里设 `analysis.coverage_enabled: true` 跑一次生成，确认 `analysis_output` 下出现 `coverage_report_*.txt`。
4. 核对未使用条件/模块的判定与 trace 原始数据一致（抽查几个模块的 condition\_text）。

