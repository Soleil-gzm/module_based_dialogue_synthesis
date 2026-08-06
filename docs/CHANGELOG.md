# Changelog

本项目所有重要变更均记录在此文件中。

本文件基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范编写，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。
日期采用 ISO 8601 格式（YYYY-MM-DD）。

> 说明：本文件由开发团队基于 Git 提交记录（`feat` / `fix` / `perf` 类型）聚合生成。
> 仓库当前未使用 Git Tag，版本号按开发里程碑划分，便于用户查阅。

---

## [0.8.0] - 2026-08-06

### Added
- 新增 `tools/deduplicate_assistant.py` 相邻 assistant 去重工具，支持按相似度阈值删除相邻且重复/高度相似的 `user+assistant` 轮次，并返回去重统计信息。
- 新增 `tools/find_adjacent_assistant_duplicates.py`，用于检测对话中相邻 assistant 消息的相似重复，并将命中对话导出为独立 JSON。
- 新增 `tools/filter_zero_overdue.py` case 分离工具，可将 `逾期天数=0` 的案例文件批量筛选并复制到新目录。
- 去重工具支持可配置相似度阈值（0.0~1.0）与忽略数字选项，适配金额/日期占位符场景。

### Changed
- 优化相邻去重保留逻辑：保留首次出现的轮次，删除后续重复，简化判定流程。
- 去重统计新增"重复对话数"与"删除轮对数"维度，便于评估数据质量。

### Performance
- 去重工具新增阈值筛选与统计次数输出，提升大数据集下的可观测性。

---

## [0.7.0] - 2026-07-15

### Added
- 新增 suning 项目占位信息与未逾期条件解析能力。
- `condition.py` 新增 `OverdueConditionEvaluator`，支持新格式条件表达式（`未逾期`、`未逾期&{逾期天数}小于0`、`未逾期&{逾期天数}等于0`）。
- 工厂方法 `create_condition_evaluator` 新增 `overdue` 类型分支。

### Changed
- 重构未逾期条件解析，实现职责分离，条件评估与元数据返回拆分为独立接口方法。
- 继承链条件解析升级至 V3，正确处理当前行与后代链的继承判断。

### Fixed
- 修复条件解析在逾期天数为负值/零值场景下的判定异常。

---

## [0.6.0] - 2026-07-06

### Added
- `main.py` 改用命令行运行，支持 `-c/--config` 指定配置文件。
- 业务规则配置化：跳转规则（`transition_rules`）支持白名单（`allow_list`）与黑名单（`deny_list`）两种模式。
- `config` 支持自动从 Excel 话术模板提取 `modules` 与 `max_repeat`，切换模板时无需手动同步。
- 输出文件命名统一化，文件名包含任务名、对话数、种子、时间戳。

### Changed
- 调整 `configs` 目录结构，配置项按功能模块分组并增加详细注释。
- 路径生成逻辑：将 `b_set` 概率的 50% 转移到当前模块自身，增强 B→A 跳转的合理性。
- 路径生成逻辑：累加 `a_set` 概率，确保 A 集模块在路径中只出现一个的规则生效。

### Deprecated
- `num_paths` 配置项改名为 `num_dialogues`（`num_dialogues` 优先级更高，旧名仍兼容）。

---

## [0.5.0] - 2026-06-24

### Added
- 新增 Trace（追踪）与分析报告：`TraceCollector` 记录每条对话的施压位置、再见触发、停止原因等决策过程。
- 新增 `core/analyzer.py` 分析器抽象及 `DefaultAnalyzer` 默认实现，输出施压位置/再见位置直方图、停止原因条形图、对话长度分布等可视化报告。
- 自动分析功能集成到配置与 `main.py`，生成对话后自动产出 HTML/PNG 报告。

### Changed
- 重构封装动态概率与曲线选择，施压概率计算支持指数/Sigmoid/线性多种曲线。

---

## [0.4.0] - 2026-06-17

### Added
- 抽象施压概率策略工厂 `create_pressure_strategy`，支持 `normalized` / `absolute` / `sigmoid` / `linear_decay` 四种归一化位置计算策略。
- 新增 `core/probability.py` 概率计算器，基于归一化位置 `t` 计算动态概率。
- 新增 `core/pressure_prob_strategy.py`，将策略选择与概率计算解耦。

### Changed
- 重构 `analyze` 抽象并完成测试，分析器支持依赖注入。

---

## [0.3.0] - 2026-06-11

### Added
- 提交首版 `README.md` 用户文档。
- 抽象时间生成器 `TimeGenerator` 及 `SimpleNaturalTimeGenerator`，支持口语化时间（如"今天下午3点"）。
- 实现 xiaoying 的 `data_loader` 工厂抽象，案例加载支持单目录（`default`）与双目录（`xiaoying`）模式。
- 抽象 `CaseLoader`、`ConditionEvaluator`，并通过工厂方法 `create_*` 创建实例。
- 集成分析报告到配置和 `main.py`。

### Changed
- 基础开发完善，核心组件高度解耦，符合开闭原则。

---

## [0.2.0] - 2026-06-04

### Added
- 新增 `pytest` 单元测试，覆盖时间生成器、案例加载器、条件解析器、数据加载与工厂模式创建对象。
- 重构 `dialogue_builder.py`，抽象私有方法构建对话，增加 Trace 记录以追溯话术来源。
- 重构施压话术模块符合 DRY 原则。
- 实现继承链"是否再见"检查与 flexible_stop 提前终止逻辑。

### Changed
- `data_loader.py` 取消 `load_sheet` 的预过滤，条件筛选改为在 `DialogueBuilder` 中由 `ConditionEvaluator` 动态执行。
- `path_generator.py` 实现路径文件复用与缓存命名规范化。
- 变量名 `stop_prob` 改为 `flexible_stop_prob`，符合清晰命名规范。

### Fixed
- 修复 `data_loader.py` 随机金额字段缺少防御保护的问题。

---

## [0.1.1] - 2026-05-27

### Added
- 实现对话生成断点续传，支持中断后从检查点恢复。
- 实现随机生成器注入（`RandomService`）与日志器依赖注入，确保可复现性与可测试性。
- 重构 `general_dialogue_builder.py`，统一对话构建入口。

### Changed
- 检查并完善 `config.py`、`logger.py`、`random_service.py`、`data_loader.py`、`path_generator.py` 等核心模块。

---

## [0.1.0] - 2026-04-29

### Added
- 项目首次提交，实现基础脚本与项目结构（排除 datas 数据目录）。
- 实现规则跳转与祖先继承链，正确替换话术标签。
- 实现通用数据采样规则与路径生成缓存。
- 细化条件匹配规则实现，强制生成不重复路径（直到达到目标数量或最大尝试次数）。
- 添加日志记录。

---

## 版本号说明

- **主版本号（X.0.0）**：不兼容的 API/配置变更。
- **次版本号（0.X.0）**：向下兼容的新功能。
- **修订号（0.0.X）**：向下兼容的问题修复与性能优化。

> 当前项目处于 `0.x` 阶段，API 与配置结构仍可能调整。从 `1.0.0` 起将严格遵循 SemVer 兼容性承诺。
