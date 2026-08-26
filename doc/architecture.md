# 架构文档 (Architecture)

> 多轮对话生成系统 — 分层架构与模块职责
> 最后更新：2026-08-06

---

## 1. 总体架构

系统采用 **分层 + 配置驱动 + 工厂模式** 架构，自上而下分为五层：

```
┌─────────────────────────────────────────────────────────────┐
│                        配置层 (YAML)                         │
│            config_templates/general_full_template.yaml       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        数据加载层                            │
│  data_loader.py      │ case_loader.py     │ config.py       │
│  ├ load_sheets       │ ├ DefaultCaseLoader│ ├ load_config   │
│  ├ load_prob_matrix  │ └ XiaoyingCaseLoader│ └ auto_sync   │
│  └ load_cases        │   (抽象+工厂)       │                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        业务逻辑层                            │
│  PathGenerator  │ DialogueBuilder │ PressureManager         │
│  condition.py   │ time_generator  │ probability.py          │
│  pressure_prob_strategy │ utterance │ random_service        │
│  (均通过 factory.py 工厂创建)                                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        生成层 (main.py)                      │
│  路径缓存 → 对话生成 → 断点续传/多进程 → 输出 JSON + Trace   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      分析层 (analyzer.py)                    │
│  trace.py → Analyzer → HTML/PNG 报告 + 统计文本              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 目录结构

```
module_based_dialogue_synthesis/
├── config_templates/
│   └── general_full_template.yaml     # 完整配置模板（含全部参数注释）
├── env/
│   └── dialogue_builder.yml           # conda 环境定义
├── scripts_general/
│   ├── main.py                        # 主入口：配置加载→生成→分析
│   ├── core/                          # 核心业务逻辑（见下文逐模块说明）
│   └── testing/                       # pytest 单元测试与调试脚本
├── tools/                             # 数据后处理工具（去重/筛选/统计）
├── docs/                              # 项目文档（本目录）
├── README.md                          # 快速上手
└── generate_structure_exclude_data.py # 项目结构生成脚本
```

---

## 3. 核心模块职责（scripts_general/core/）

### 3.1 config.py — 配置中心

- `load_config(path)`：加载 YAML，返回 `Config` 对象。
- `auto_sync_config_from_excel(config)`：从话术模板 Excel 自动提取 `modules` 与 `max_repeat`，覆盖配置值。
- `Config`：统一配置访问入口，`get(key, default)` 支持点号路径（如 `case_loader.type`）。

### 3.2 data_loader.py — 数据加载

- `load_sheets(excel_path, modules, keep_cols)`：读取每个模块 sheet 为 DataFrame，保留核心列（`uid`、`parent(继承)`、`repeat(次数)`、`conditions(条件)`、`human(客户)`、`assistant(专员)`、`flexible_stop(可选不继承)`、`是否再见`）。
- `load_prob_matrix(prob_path, modules)`：读取概率转移矩阵。
- `parse_case_info(text)`：解析案例文件，自动提取金额数字部分，同时保留原始字符串。

### 3.3 case_loader.py — 案例加载器（抽象 + 工厂）

| 类 | 模式 | 行为 |
|----|------|------|
| `CaseLoader` (ABC) | — | 定义 `load() → (cases, prompts)` 接口 |
| `DefaultCaseLoader` | 单目录 | 每个 `.txt` 同时作为占位数据与 system prompt |
| `XiaoyingCaseLoader` | 双目录 | `replace_dir` 存占位数据，`system_dir` 存系统提示，按文件名排序一一对应，数量不等时循环复用 |

### 3.4 condition.py — 条件解析器（抽象 + 工厂）

- `ConditionEvaluator` (ABC)：`evaluate()` 与 `evaluate_with_metadata()` 双接口。
- `KeywordConditionEvaluator`：旧格式，检查是否包含「逾期」关键词。
- `OverdueConditionEvaluator`：新格式，支持 `未逾期`、`未逾期&{逾期天数}小于0`、`未逾期&{逾期天数}等于0` 等表达式，从 case 解析逾期天数数值判断。

### 3.5 path_generator.py — 路径生成

依据概率矩阵 + 跳转规则生成模块路径序列。

**跳转规则优先级**：
1. 若当前模块在 `transition_rules` 中有配置 → 按白名单/黑名单筛选候选。
2. 若当前模块在 `a_set` → 候选为 `[current] + b_set`（A 集规则：路径中只能有一个 A 集模块）。
3. 若当前模块在 `b_set` → 候选为 `b_set + [selected_a]`。
4. 默认候选为所有模块。

**自动规则**：A 集模块不能跳转到其他 A 集模块；达到 `max_repeat` 的模块被 ban；终止模块遇非零概率加入候选；`self_loop_modules` 按占比独立循环。

支持路径缓存复用（`all_paths_{num_paths}_{seed}.json`）与强制不重复生成。

### 3.6 dialogue_builder.py — 对话构建（核心）

`DialogueBuilder.build(path, case, prompt)`：
1. 遍历路径中每个模块。
2. 由 `ConditionEvaluator` 筛选符合条件的行。
3. 沿继承链（`parent(继承)`）确定可用话术。
4. 由 `sample_utterance` 随机抽取 `human`/`assistant` 话术（`/` 分隔多选项）。
5. 由 `should_stop_by_flexible` 判断 `flexible_stop` 提前终止。
6. 由 `PressureManager` 在 `insert_nodes` 位置动态插入施压片段。
7. 由再见逻辑（固定/动态概率）决定对话终止。
8. 由 `TimeGenerator` 替换时间占位符。
9. 由 `TraceCollector` 记录决策过程。

### 3.7 pressure_manager.py — 施压管理

- 依据 `repeat(次数)` 从施压话术表抽取片段（可含多轮）。
- 支持 repeat、继承、条件、随机后代链。
- `flexible_stop_prob` 控制后代链提前终止。

### 3.8 probability.py 与 pressure_prob_strategy.py — 动态概率

**双层解耦设计**：

```
PressureStrategy.get_normalized_position(idx, total) → t
        │
        ▼
ProbabilityCalculator.calculate(t) → 概率值
```

| 策略（位置 t） | 公式 |
|----------------|------|
| `NormalizedPressureStrategy` | `t = idx / (total-1)` |
| `AbsolutePressureStrategy` | `t = min(1.0, idx / max_expected_modules)` |
| `SigmoidPressureStrategy` | `t = 1/(1+exp(-slope*(x-0.5)))` |
| `LinearDecayPressureStrategy` | `t = 1 - idx/(total-1)` |

| 计算器（概率曲线） | 公式 |
|--------------------|------|
| `ExponentialProbabilityCalculator` | `prob = start + (end-start)*t^exponent` |
| `SigmoidProbabilityCalculator` | `prob = 1/(1+exp(-slope*(t-0.5)))` |
| `LinearProbabilityCalculator` | `prob = start + (end-start)*t` |

### 3.9 time_generator.py — 时间生成器

`SimpleNaturalTimeGenerator`：随机生成口语化时间（「今天下午3点」「昨天晚上8点30分」）。可扩展 `RelativeTimeGenerator` 等基于查账时间的生成器。

### 3.10 random_service.py — 随机服务

封装 `random.Random`（独立实例，避免全局污染）+ `numpy` 随机种子同步。提供 `random/choice/choices/randint/uniform/sample` 等方法，通过构造函数注入，保证可复现性。

### 3.11 trace.py — 追踪收集器

`TraceCollector` 记录单条对话的决策点：路径、施压位置、再见触发、停止原因、模块轮次等。`trace_enabled` 开关控制。`_convert_to_native` 递归转换 numpy 类型，确保 JSON 可序列化。

### 3.12 analyzer.py — 分析器（抽象 + 工厂）

`DefaultAnalyzer`：对 trace 文件生成可视化报告：
- 施压位置直方图、再见位置直方图
- 停止原因条形图、对话长度分布直方图
- 再见处理统计、施压覆盖率饼图
- 输出 HTML（plotly）或 PNG（matplotlib）

### 3.13 factory.py — 工厂集合

集中所有 `create_*` 工厂方法，根据配置 type 分支创建对应实例，实现配置驱动的组件切换。

### 3.14 logger.py — 日志（单例）

模块级单例 `_logger_instance`，`init_logger` 根据配置初始化（级别、文件前缀、是否控制台、格式、日期格式），支持文件 + 控制台双输出。

---

## 4. 生成层流程（main.py）

```
1. 加载配置 (load_config + auto_sync_config_from_excel)
2. 读取基本参数 (task_name / num_dialogues / seed / 多进程配置)
3. 创建任务目录结构 (logs / traces / analysis)
4. 初始化日志
5. 创建 RandomService(seed)
6. 加载数据 (load_sheets / load_prob_matrix / CaseLoader / 施压话术表)
7. 创建条件解析器与时间生成器
8. 路径生成 (PathGenerator, 支持缓存复用)
9. 对话生成
   ├─ 单进程: generate_single_process (断点续传 + 进度条 + trace 收集)
   └─ 多进程: worker_generate 分片并行 → merge_shards_to_json 合并
10. 自动分析 (若启用且 trace 存在 → DefaultAnalyzer)
```

**输出格式**：临时 JSON Lines 流式写入 → 合并为标准 JSON 数组，兼容 orjson 加速。

---

## 5. 工具层（tools/）

| 工具 | 作用 |
|------|------|
| `deduplicate_assistant.py` | 相邻 assistant 去重，按相似度阈值保留首次出现，支持统计 |
| `find_adjacent_assistant_duplicates.py` | 检测相邻 assistant 重复并导出命中对话 |
| `filter_zero_overdue.py` | 筛选 `逾期天数=0` 案例文件到新目录 |
| `name_length_distribution.py` | 姓名长度分布统计 |

---

## 6. 设计原则

1. **单一职责**：每个核心类只负责一个领域（路径/对话/施压/条件/时间）。
2. **依赖倒置**：高层（DialogueBuilder）依赖抽象（ConditionEvaluator/CaseLoader），非具体实现。
3. **开闭原则**：新增行为通过继承 + 工厂分支扩展，不修改既有代码。
4. **DRY**：施压话术构建、话术抽取等公共逻辑抽取为私有方法/工具函数。
5. **可复现**：随机源统一注入，杜绝全局随机。
6. **配置即文档**：YAML 配置项按功能分组并附详细注释。

---

## 7. 扩展指南

### 新增条件解析器
1. 继承 `ConditionEvaluator`，实现 `evaluate` / `evaluate_with_metadata`。
2. 在 `factory.py` 的 `create_condition_evaluator` 添加分支。
3. 配置 `condition_parser: "my_parser"`。

### 新增案例加载器
1. 继承 `CaseLoader`，实现 `load`。
2. 在 `factory.py` 的 `create_case_loader` 添加分支。
3. 配置 `case_loader.type` 及对应参数。

### 新增时间生成器
1. 继承 `TimeGenerator`，实现 `generate`。
2. 在 `time_generator.py` 的 `create_time_generator` 添加分支。
3. 配置 `time_generator.type`。

### 新增施压策略/概率曲线
1. 继承 `PressureStrategy` / `ProbabilityCalculator`。
2. 在 `factory.py` 对应工厂方法添加分支。
3. 配置 `pressure_strategy.type` / `pressure_calc_type`。

---

## 8. 相关文档

- [项目设计文档](project-design-doc.md)
- [进度文档](progress.md)
- [开发日志](WORKLOG.md)
- [更新日志](CHANGELOG.md)
