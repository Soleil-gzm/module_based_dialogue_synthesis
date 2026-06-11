# 多轮对话生成系统

基于规则和概率矩阵的对话数据集自动生成工具，专为电话催收场景设计。通过 Excel 话术模板 + 概率转移矩阵 + 继承树结构，自动生成大量多样化的多轮对话 `JSON` 数据，可直接用于 `LLM` 的指令微调或对话模型训练。

---

## 📋 目录

- [特性](#特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [数据准备](#数据准备)
- [运行生成](#运行生成)
- [测试](#测试)
- [输出结构](#输出结构)
- [扩展开发](#扩展开发)
- [常见问题](#常见问题)

---

## ✨ 特性

- **配置驱动**：所有业务参数（模块、转移概率、重复次数、施压策略等）均通过 `YAML` 配置文件管理，无需修改代码即可适配不同业务线。
- **可复现性**：统一随机服务 `RandomService` 支持固定种子，确保生成结果可复现。
- **模块化设计**：路径生成、对话构建、条件解析、施压话术、时间生成等核心组件高度解耦，符合开闭原则。
- **断点续传**：生成大规模对话时支持检查点机制，中断后可恢复。
- **智能施压策略**：动态概率模型使施压话术自然集中于对话中后段，符合真实催收流程。
- **可扩展条件解析**：抽象 `ConditionEvaluator`，当前支持关键词匹配，可轻松替换为复杂逻辑（如 `&`、`|` 运算符）。
- **灵活案例加载**：支持单一目录（原有行为）或双目录（替换数据 + 系统提示）模式，适配不同业务需求。
- **自然时间生成**：内置口语化时间生成器（如“今天下午3点”），可自定义或扩展。
- **详尽追踪**：可选 `TraceCollector` 记录每条对话的决策过程（施压位置、再见触发、停止原因等），便于分析与调优。
- **自动分析报告**：生成对话后自动调用分析模块，输出可视化图表（HTML/PNG）和统计报告。

---

## 🏗️ 系统架构

![[Pasted image 20260611171602.png]]

```
┌─────────────────────────────────────────────────────────────┐
│                        配置层 (YAML)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        数据加载层                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ load_sheets │  │load_prob    │  │ CaseLoader (抽象)   │ │
│  │  (Excel)    │  │  Matrix     │  │ ├ DefaultCaseLoader │ │
│  └─────────────┘  └─────────────┘  │ └ XiaoyingCaseLoader│ │
│                                     └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        业务逻辑层                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │PathGenerator │  │DialogueBuilder│ │PressureManager   │  │
│  │ (路径生成)   │  │ (对话构建)    │  │ (施压管理)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ConditionEval │  │TimeGenerator │  │RandomService     │  │
│  │ (条件解析)   │  │ (时间生成)   │  │ (随机服务)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        生成层 (main.py)                       │
│  └── 路径缓存 → 对话生成 → 断点续传 → 输出 JSON + Trace     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      分析层 (analyze_all.py)                 │
│  └── 施压位置、再见处理、停止原因、对话轮数分布等图表        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- 依赖包：`pandas`, `numpy`, `openpyxl`, `pyyaml`, `plotly`（可选，用于 HTML 图表）

### 安装

```bash
# 克隆项目
git clone <repository-url>
cd module_based_dialogue_synthesis

# 创建虚拟环境（推荐）
conda env create -f env/dialogue_builder.yml
conda activate dialogue_builder

# 或使用 pip
pip install pandas numpy openpyxl pyyaml plotly
```

### 准备数据

1. **Excel 话术模板**：包含所有模块 sheet 和“链接施压话术” sheet（列定义详见 [数据准备](#数据准备)）。
2. **概率矩阵**：Excel 文件，行列均为模块名，值为整数百分比。
3. **案例文件**：文本文件，格式为 `- 字段：值`（示例见 `datas/xiaoying/cases_replace/`）。

### 配置

复制 `configs/general_Template.yaml` 为 `configs/my_config.yaml`，按需修改。

### 运行

```bash
python scripts_general/main.py
```

---

## ⚙️ 配置说明

配置文件采用 YAML 格式，主要配置段如下：

```yaml
# 基础配置
task_name: "xiaoying"          # 任务名称，用于输出子目录
num_paths: 1000                # 生成对话数量
random_seed: 42                # 随机种子

# 数据路径
excel_path: "data/xiaoying/template.xlsx"
prob_path: "data/xiaoying/prob.xlsx"

# 案例加载器 (支持 default / xiaoying)
case_loader:
  type: "xiaoying"             # 双目录模式
  replace_dir: "datas/xiaoying/cases_replace"   # 占位数据
  system_dir: "datas/xiaoying/cases_system"     # 系统提示

# 模块定义
modules:
  - "身份确认"
  - "告知"
  - "没钱"
  # ... 完整列表

max_repeat:
  "身份确认": 1
  "没钱": 3
  # ... 每个模块的最大重复次数

a_set: ["没钱", "失业", "生病住院"]
b_set: ["承诺还款", "三方", "转告"]
terminal_modules: ["已还款"]

# 施压话术配置
insert_nodes: ["没钱", "失业", "生病住院"]
pressure_dynamic_enabled: true
pressure_start_prob: 0.02
pressure_end_prob: 0.6
pressure_curve_exponent: 2.5
pressure_max_total: 3
module_pressure_weights:
  "没钱": 1.2
  "失业": 1.0

# 再见逻辑
goodbye_termination_prob: 0.3
flexible_stop_prob: 0.3

# 时间生成器
time_generator:
  type: "simple_natural"       # 当前仅支持 simple_natural

# 条件解析器
condition_parser: "keyword"    # keyword / 未来可扩展

# 追踪与日志
trace_enabled: true
logging:
  level: "INFO"
  console: true
  log_dir: "logs"

# 自动分析
auto_analysis:
  enabled: true
  format: "html"               # html 或 png
```

---

## 📁 数据准备

### Excel 话术模板

**必须包含的列**：

| 列名 | 说明 |
|------|------|
| `uid` | 唯一标识 |
| `parent(继承)` | 父节点 uid，用于构建继承链 |
| `repeat(次数)` | 支持的重复次数，如 `1` 或 `1/2/3` |
| `conditions(条件)` | 条件表达式（当前支持关键词“逾期”） |
| `human(客户)` | 客户话术，多个选项用 `/` 分隔 |
| `assistant(专员)` | 专员话术，多个选项用 `/` 分隔 |
| `flexible_stop(可选不继承)` | 是否允许后代链提前终止（1/0） |
| `是否再见` | 是否可能触发对话终止（1/0） |

### 概率矩阵

Excel 文件，第一行和第一列为模块名，单元格值为 0~100 的整数（表示百分比）。例如：

|          | 身份确认 | 告知 | 没钱 |
|----------|---------|------|------|
| 身份确认 | 0       | 80   | 20   |
| 告知     | 0       | 0    | 100  |
| 没钱     | 0       | 0    | 60   | (剩余 40 跳转到 B 集)

### 案例文件

#### 单目录模式 (`default`)

每个 `.txt` 文件同时作为**占位数据**和**系统提示**，格式如下：

```
- 客服电话：952592
- 客户姓名：张三
- 逾期天数：30
- 逾期金额：5000元
...
```

#### 双目录模式 (`xiaoying`)

- **replace_dir**：存放占位数据文件（用于填充对话中的 `{变量}`），格式同上。
- **system_dir**：存放系统提示文本（直接作为 system 消息内容），可包含多行自由文本。

两个目录中的文件按文件名排序后一一对应，数量不等时循环复用。

---

## ▶️ 运行生成

### 基本运行

```bash
python scripts_general/main.py
```

### 命令行参数（仅针对分析脚本）

分析脚本 `analyze_all.py` 支持独立运行：

```bash
# 分析指定 trace 文件，自动生成时间戳子目录
python scripts_general/analyze_all.py --trace output/xiaoying_1000_42/intermediate/traces/traces_20260611_142040.json

# 指定输出目录和图表格式
python scripts_general/analyze_all.py --trace traces.json --output_dir my_analysis --format png
```

### 断点续传

- 检查点文件：`output/{task_dir}/checkpoint.json`
- 每生成 `checkpoint_interval` 条对话自动保存
- 再次运行 `main.py` 会自动恢复

---

## 🧪 测试

项目使用 `pytest` 进行单元测试，覆盖核心模块。

```bash
# 运行所有测试
pytest scripts_general/testing/ -v

# 运行特定测试文件
pytest scripts_general/testing/test_case_time.py -v
```

测试覆盖：

- 时间生成器格式验证
- 案例加载器（default / xiaoying）
- 条件解析器
- 数据加载与解析（含金额数值提取）
- 工厂模式创建对象

---

## 📂 输出结构

运行完成后，输出目录结构如下：

```
output/xiaoying_1000_42/                     # 任务目录
├── general_dialogues_20260611_142040.json   # 最终对话数据
├── checkpoint.json                          # 检查点（生成完成后自动删除）
├── intermediate/                            # 中间文件
│   ├── logs/                                # 运行日志
│   │   └── dialogue_builder_20260611_142040.log
│   ├── traces/                              # 追踪数据（trace_enabled=True）
│   │   └── traces_20260611_142040.json
│   └── analysis/                            # 自动分析报告
│       └── 20260611_142040/                 # 按时间戳分组
│           ├── pressure_position_histogram.html
│           ├── goodbye_position_histogram.html
│           ├── stop_reason_bar.html
│           ├── dialogue_length_histogram.html
│           ├── goodbye_handling_bar.html
│           └── analysis_report.txt
└── auto_analysis/                           # 若配置了 auto_analysis
    └── ... (同 analysis 结构)
```

此外，路径缓存独立存放于：

```
output/paths/all_paths_{num_paths}_{seed}.json
```

---

## 🔧 扩展开发

### 1. 添加新的条件解析器

1. 继承 `ConditionEvaluator`，实现 `evaluate` 方法。
2. 在 `factory.py` 的 `create_condition_evaluator` 中添加分支。
3. 配置文件中指定 `condition_parser: "my_parser"`。

### 2. 添加新的时间生成器

1. 继承 `TimeGenerator`，实现 `generate` 方法。
2. 在 `time_generator.py` 的 `create_time_generator` 中添加分支。
3. 配置 `time_generator.type: "my_generator"`。

### 3. 添加新的案例加载器

1. 继承 `CaseLoader`，实现 `load` 方法。
2. 在 `factory.py` 的 `create_case_loader` 中添加分支。
3. 配置 `case_loader.type: "my_loader"` 及相应参数。

### 4. 调整动态施压曲线

修改 `config` 中的 `pressure_start_prob`, `pressure_end_prob`, `pressure_curve_exponent` 等参数，可控制施压话术在对话中的分布。

---

## ❓ 常见问题

### Q: 生成对话数量少于预期？

- 检查 `num_paths` 是否超过可能的路径组合数（有限状态机限制）。
- 增大 `max_repeat` 或减少终止模块可增加多样性。

### Q: 施压话术集中在对话开头？

- 确认 `pressure_dynamic_enabled: true`
- 降低 `pressure_start_prob` (如 0.02)，增大 `pressure_curve_exponent` (如 2.5)
- 检查早期模块的 `module_pressure_weights` 是否设置过高。

### Q: 金额字段包含“元”导致转换错误？

已修复：`parse_case_info` 会自动提取数字部分，同时保留原始字符串。无需额外处理。

### Q: 如何禁用自动分析？

在配置文件中设置 `auto_analysis.enabled: false`。

### Q: 如何切换到单目录案例加载？

配置 `case_loader.type: "default"` 并指定 `cases_dir`。

---

## 📝 许可证

[待补充]

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。请确保新增代码包含单元测试，并遵循现有代码风格。

---

**最后更新**：2026-06-11
