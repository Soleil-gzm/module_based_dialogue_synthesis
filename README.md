# 🧩一、项目背景

基于规则和概率矩阵的对话数据集自动生成工具，专为电话催收场景设计。通过 Excel 话术模板 + 概率转移矩阵 + 继承树结构，自动生成大量多样化的多轮对话 JSON 数据，可直接用于 LLM 的指令微调或对话模型训练。

# 🧩二、功能特性

- **配置驱动**：所有业务参数（模块列表、转移规则、重复次数限制等）通过 YAML 配置文件管理，无需修改代码即可适配不同话术模板或业务逻辑。

- **模块化设计**：路径生成、对话构建、条件解析、随机服务等职责分离，便于扩展和维护。

- **继承树模拟**：每个模块内部通过 `uid` / `parent` 构建话术树，支持祖先链（完整上下文）和随机后代链（模拟分支），使对话更真实。

- **施压话术独立模块**：施压话术自身具备 repeat、继承、条件解析能力，可根据主模块出现次数动态附加，并支持合并或独立轮次。

- **断点续传 & 路径缓存**：对话生成定期保存检查点，意外中断后可恢复；路径生成结果按 `num_paths` 和 `seed` 缓存，避免重复计算。

- **可复现随机**：统一 `RandomService` 管理随机种子，确保结果可重复。

- **详细追踪**（可选）：记录每条对话的模块处理状态、跳过原因、停止原因、继承链长度、施压话术细节等，便于调试和分析。

# 🧩三、项目代码说明

## trace 标签说明

| trace 标签                | 说明                            |
| ----------------------- | ----------------------------- |
| module                  |                               |
| repeat                  |                               |
| status                  |                               |
| turn_count              |                               |
| ancestor_count          |                               |
| descendant_count        |                               |
| stop_reason             |                               |
| error                   |                               |
| selected_uid            |                               |
| pressure_applied        |                               |
| pressure_segment_length |                               |
| pressure_merge_last     | 是否将该片段的第一个助理话术合并到了上一条已有的助理消息中 |

## 配置文件说明

配置文件 `configs/general.yaml` 包含所有业务参数，主要字段如下：

| 字段                         | 类型    | 说明                                                                                           |
| -------------------------- | ----- | -------------------------------------------------------------------------------------------- |
| `modules`                  | list  | 模块名称列表，必须与 Excel 中 sheet 名称一致                                                                |
|                            |       |                                                                                              |
| `start_module`             | str   | 路径起始模块，默认为 `modules` 第一个                                                                     |
| `max_repeat`               | dict  | 每个模块在路径中最多出现的次数                                                                              |
| `terminal_modules`         | list  | 终止模块（如 `["承诺还款", "已还款"]`）                                                                    |
| `a_set` / `b_set`          | list  | A 集（自循环模块）和 B 集（循环模块）                                                                        |
| `insert_nodes`             | list  | 需要附加施压话术的模块                                                                                  |
| `pressure_prob`            | float | 施压话术触发概率（0~1）                                                                                |
| `goodbye_termination_prob` | float | 遇到“是否再见=1”时终止对话的概率                                                                           |
| `paths_cache`              | str   | 路径缓存模板，需包含 `{num_paths}` 和 `{seed}` 占位符，如 `"intermediate/all_paths_{num_paths}_{seed}.json"` |
| `trace_enabled`            | bool  | 是否启用详细追踪（记录每条对话的决策过程）                                                                        |
| `trace_output_dir`         | str   | 追踪数据输出目录，如 `"traces"`                                                                        |
| `logging`                  | dict  | 日志配置（级别、目录、格式等）                                                                              |
完整示例参见仓库中的 `configs/general.yaml`。

# 🧩四、安装与依赖

## 环境要求

- Python 3.9+

- 建议使用虚拟环境（conda 或 venv）

## 安装依赖

`重建环境：`
`conda env create -f path/to/dialogue_builder.yml`
`指定新环境名：`
`conda env create -n 新环境名 -f path/to/dialogue_builder.yml`

# 📄问题待解决

1. trace 记录里面的merge_last报错
2. 文件时间戳一致性
3.
