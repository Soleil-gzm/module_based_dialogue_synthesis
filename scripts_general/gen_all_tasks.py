"""
批量生成 8 条业务线的 base_{line}.yaml + tasks_{line}.yaml
使用方法：python scripts_general/gen_all_tasks.py
"""
import os

# ---------- 业务线定义 ----------
# (业务线名, generator_type, 阶段, seed起始)
BUSINESS_LINES = [
    ("M0",              "m0",              "首催", 21),
    ("M0_follow",       "m0_follow",       "跟催", 31),
    ("M1",              "m1",              "首催", 41),
    ("M1_follow",       "m1_follow",       "跟催", 51),
    ("M2",              "m2",              "首催", 61),
    ("M2_follow",       "m2_follow",       "跟催", 71),
    ("M3plus",          "m3_plus",         "首催", 81),
    ("M3plus_follow",   "m3_plus_follow",  "跟催", 91),
]

# ---------- 6 个任务定义 ----------
# (后缀, 中文类别)
TASKS = [
    ("WN_AN", "无意愿无能力"),
    ("WY_AN", "有意愿无能力"),
    ("WN_AY", "无意愿有能力"),
    ("WY_AY", "有意愿有能力"),
    ("CR",    "有投诉风险"),
    ("BP",    "易跳票客户"),
]

# ---------- base 模板 ----------
BASE_TEMPLATE = """# ============================================
# {line} 业务线 - 基础配置（6 个任务共用）
# 任务 YAML 通过 `base: "base_{line}.yaml"` 引用
# ============================================

company: "suning"
start_module:
  身份确认: 0.99
  语音留言: 0.01
output_dir: "output/json_datas/{line}"
paths_cache_dir: "paths"
paths_cache: "output/json_datas/{line}/paths/all_paths_{{num_paths}}_{{seed}}.json"
checkpoint_interval: 50000

a_set:
  - "通用原因"
  - "否认办理业务"
  - "工程款"
  - "未发工资"
  - "还错卡"
  - "生病住院"
  - "破产"
  - "失业"
  - "他人用款"
  - "忘记还款"
  - "盗刷"

b_set:
  - "敷衍"
  - "投诉处理"
  - "信息问题"
  - "不方便接电"
  - "对抗"
  - "没钱"
  - "诉求"
  - "承诺还款"
  - "无法沟通"

terminal_modules:
  - "已还款"

insert_nodes:
  - "失业"
  - "破产"
  - "生病住院"
  - "未发工资"
  - "工程款"
  - "通用原因"
  - "没钱"

pressure_prob: 0.3
pressure_dynamic_enabled: true
pressure_calc_type: "exponential"
pressure_start_prob: 0.5
pressure_end_prob: 1.0
pressure_curve_exponent: 3.5
pressure_max_total: 3
pressure_strategy:
  type: "normalized"
module_pressure_weights:
  没钱: 1.2
  失业: 1.0
  破产: 1.0
  生病住院: 1.0
  未发工资: 1.0
  工程款: 1.0
  通用原因: 0.9

flexible_stop_prob: 0.7
goodbye_termination_prob: 0.8
goodbye_dynamic_enabled: false
goodbye_calc_type: "exponential"
goodbye_start_prob: 0.05
goodbye_end_prob: 0.8
goodbye_exponent: 3.0
goodbye_min_idx: 2

time_generator:
  type: "simple_natural"

trace_enabled: true
logging:
  level: "DEBUG"
  file_prefix: "dialogue_builder"
  console: true
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  datefmt: "%Y-%m-%d %H:%M:%S"

dedup:
  enabled: true
  threshold: 0.85
  ignore_numbers: true
  output_suffix: "_dup"

analysis:
  enabled: true
  format: "html"
  diversity_modules:
  coverage_enabled: true

multiprocessing:
  num_processes: 20
"""

# ---------- 任务条目模板 ----------
TASK_ITEM = """  - name: "{line}_{suffix}"
    enabled: true
    task_name: "{line}_{suffix}"
    num_paths: 40000
    random_seed: {seed}
    excel_path: "output/datas/excel_48/{line}/【{line}】{cn}-{stage} - 20260922.xlsx"
    prob_auto_generate:
      enabled: true
      categories_yaml: "output/datas/config/prob_config/categories_{family}-0917.yaml"
      compress_mode: "log"
    case_loader:
      type: "xiaoying"
      replace_dir: "output/case_agent/{line}/{line}_{suffix}/case/replace{line}_{suffix}_4w"
      system_dir: "output/case_agent/{line}/{line}_{suffix}/case/system{line}_{suffix}_4w"
    case_auto_generate:
      enabled: true
      generator_type: "{gen}"
      num_cases: 40000
      prompt_system_path: "output/datas/prompt_agent/{line}/{line}_0918_{cn}.txt"
      prompt_replace_path: "output/datas/prompt_agent/prompt_template_for_backbone_replace.txt"
      force_regenerate: false
"""

TASKS_TEMPLATE = """# ============================================
# {line} 业务线 - 任务列表（6 个任务）
# ============================================

base: "base_{line}.yaml"

tasks:
{tasks_block}"""


def family_of(line: str) -> str:
    """取业务线系列标记：M0_follow -> M0；M3plus_follow -> M3plus"""
    return line.split("_")[0]


def main():
    for line, gen, stage, seed_start in BUSINESS_LINES:
        out_dir = os.path.join("configs", line)
        os.makedirs(out_dir, exist_ok=True)

        # 1. base_{line}.yaml
        base_path = os.path.join(out_dir, f"base_{line}.yaml")
        with open(base_path, "w", encoding="utf-8") as f:
            f.write(BASE_TEMPLATE.format(line=line))

        # 2. tasks_{line}.yaml
        family = family_of(line)
        blocks = []
        for i, (suffix, cn) in enumerate(TASKS):
            blocks.append(TASK_ITEM.format(
                line=line, suffix=suffix, seed=seed_start + i,
                cn=cn, stage=stage, gen=gen, family=family,
            ))
        tasks_path = os.path.join(out_dir, f"tasks_{line}.yaml")
        with open(tasks_path, "w", encoding="utf-8") as f:
            f.write(TASKS_TEMPLATE.format(line=line, tasks_block="\n".join(blocks)))

        print(f"✅ {line}: {base_path} + {tasks_path}")


if __name__ == "__main__":
    main()