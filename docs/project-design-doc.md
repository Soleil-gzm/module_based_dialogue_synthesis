# 项目设计文档 (Project Design Doc)

> 多轮对话生成系统 — 设计说明
> 最后更新：2026-08-06

---

## 1. 项目背景与目标

### 1.1 背景

在电话催收等垂直业务场景中，训练高质量的多轮对话模型需要大量结构化、多样化的对话数据。人工标注成本高、效率低，且难以覆盖业务话术中各种跳转路径与施压策略的组合。

本项目通过 **「Excel 话术模板 + 概率转移矩阵 + 继承树结构」** 的方式，自动生成大量符合业务规则的多轮对话 `JSON` 数据，可直接用于 `LLM` 指令微调或对话模型训练。

### 1.2 核心目标

| 目标 | 说明 |
|------|------|
| **配置驱动** | 所有业务参数通过 YAML 管理，切换业务线无需改代码 |
| **可复现性** | 统一随机服务 + 种子注入，生成结果可复现 |
| **模块化** | 路径生成、对话构建、条件解析等组件解耦，符合开闭原则 |
| **规模化** | 支持多进程并行、断点续传、流式写入，可生成数万条对话 |
| **可观测** | Trace 追踪 + 自动分析报告，便于调优与质量评估 |
| **可扩展** | 案例加载器、条件解析器、时间生成器、施压策略均通过工厂模式扩展 |

### 1.3 非目标（Non-Goals）

- 不负责训练模型本身，只产出训练数据。
- 不替代真实人机对话的随机性，生成严格受话术模板与概率矩阵约束。

---

## 2. 核心概念模型

### 2.1 模块（Module）

对话的基本组成单元，如「身份确认」「告知」「没钱」。每个模块对应 Excel 中的一个 sheet，包含多行话术（`human` 客户话术 / `assistant` 专员话术）。

### 2.2 路径（Path）

一条由模块名组成的有序序列，如 `["身份确认", "告知", "没钱", "承诺还款"]`，描述一次对话的模块流转顺序。路径由概率转移矩阵 + 跳转规则生成。

### 2.3 A 集 / B 集

| 集合 | 语义 | 路径规则 |
|------|------|----------|
| `a_set` | 问题原因类模块（失业、生病住院等） | 路径中**只能出现一个** A 集模块 |
| `b_set` | 态度回应类模块（没钱、承诺还款等） | 可在路径中**多次出现** |

### 2.4 继承链（Inheritance Chain）

通过 Excel 的 `parent(继承)` 列构建父子关系。子行可继承父行的话术属性（如 `flexible_stop`、`是否再见`），实现话术复用与条件约束传递。

### 2.5 施压话术（Pressure）

在特定模块（`insert_nodes`）位置插入的催收施压片段，由独立的「链接施压话术」sheet 管理。施压概率随对话位置**动态变化**（前低后高），符合真实催收流程。

### 2.6 再见（Goodbye）

对话终止机制。当模块命中 `是否再见=1` 时，按概率决定是否触发对话结束，支持动态再见概率曲线。

---

## 3. 数据流设计

```
Excel 话术模板 ─┐
                ├─→ load_sheets ─→ df_dict (每模块 DataFrame)
概率矩阵 ───────┘─→ load_prob_matrix ─→ prob_df

df_dict + prob_df + 跳转规则 ─→ PathGenerator ─→ all_paths (路径列表)

案例文件 ─→ CaseLoader ─→ (cases, prompts)

all_paths + cases + df_dict ─→ DialogueBuilder ─→ messages (对话列表)
                                  │
                                  ├─ PressureManager (施压片段注入)
                                  ├─ ConditionEvaluator (条件筛选)
                                  ├─ TimeGenerator (时间占位符)
                                  └─ TraceCollector (决策追踪)

messages ─→ JSON 输出文件
Trace    ─→ traces JSON ─→ Analyzer ─→ HTML/PNG 报告
```

---

## 4. 关键设计决策

### 4.1 配置与代码分离

所有硬编码常量（模块列表、最大重复次数、A/B 集、终止模块、施压概率等）提取到 YAML。切换公司/业务线只需换配置文件。

同时 `auto_sync_config_from_excel()` 自动从话术模板提取 `modules` 与 `max_repeat`，避免切换模板时忘记同步。

### 4.2 依赖注入与可复现性

`RandomService` 封装 `random` + `numpy` 随机源，通过构造函数注入到所有需要随机的组件，避免全局污染。`Logger` 同样采用依赖注入。

### 4.3 动态概率模型

施压与再见概率均采用 **「归一化位置 t + 曲线函数」** 双层设计：

```
概率 = start_prob + (end_prob - start_prob) * t^exponent
```

- **位置策略**（`PressureStrategy`）：决定 `t` 的计算方式（归一化/绝对索引/Sigmoid/线性衰减）。
- **曲线计算器**（`ProbabilityCalculator`）：决定概率随 `t` 的变化曲线（指数/Sigmoid/线性）。

二者解耦，可独立配置组合。

### 4.4 抽象与工厂模式

所有可扩展组件均通过抽象基类 + 工厂方法实现：

| 组件 | 抽象基类 | 工厂方法 |
|------|----------|----------|
| 条件解析器 | `ConditionEvaluator` | `create_condition_evaluator` |
| 案例加载器 | `CaseLoader` | `create_case_loader` |
| 时间生成器 | `TimeGenerator` | `create_time_generator` |
| 施压策略 | `PressureStrategy` | `create_pressure_strategy` |
| 概率计算器 | `ProbabilityCalculator` | `create_probability_calculator` |
| 分析器 | `Analyzer` | `create_analyzer` |

### 4.5 断点续传与多进程

- **单进程**：检查点（`checkpoint.json`）记录 `next_index`，中断后自动恢复，临时文件用 JSON Lines 流式写入，最后合并为标准 JSON 数组。
- **多进程**：按 chunk 切分任务，各进程独立种子（`seed + process_id`），分片文件并行写入后合并。

---

## 5. 输入输出规范

### 5.1 输入

| 输入 | 格式 | 说明 |
|------|------|------|
| 话术模板 | `.xlsx` | 每模块一个 sheet + 「链接施压话术」sheet |
| 概率矩阵 | `.xlsx` | 行列均为模块名，值为整数百分比 |
| 案例文件 | `.txt` | `- 字段：值` 格式，用于占位填充 |
| 配置文件 | `.yaml` | 全部参数（见 `config_templates/general_full_template.yaml`） |

### 5.2 输出

```
output/{task_name}_{num_dialogues}_{seed}/
├── {task_name}_generate_{num_dialogues}_{seed}_{timestamp}.json  # 对话数据
└── intermediate/
    ├── logs/      # 运行日志
    ├── traces/    # 追踪数据（trace_enabled=True）
    └── analysis/  # 自动分析报告
```

对话 JSON 结构（OpenAI messages 格式）：

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

---

## 6. 适用场景与边界

### 6.1 适用

- 催收、客服等**有明确话术模板与流转规则**的多轮对话数据合成。
- 需要可控多样性（概率矩阵 + 模块组合）的指令微调数据生产。
- 需要可复现、可追溯、可分析的批量数据生成。

### 6.2 边界

- 生成质量上限取决于话术模板的完备性与概率矩阵的合理性。
- 不包含真实语义理解，条件解析当前仅支持关键词/逾期天数匹配，复杂逻辑需扩展 `ConditionEvaluator`。

---

## 7. 相关文档

- [架构文档](architecture.md) — 分层架构与模块职责详解
- [进度文档](progress.md) — 版本里程碑与功能完成度
- [开发日志](WORKLOG.md) — 开发过程中的思考与关键决策
- [更新日志](CHANGELOG.md) — 面向用户的版本变更记录
- [README](../README.md) — 快速上手指南
