import json
import os
import random
from datetime import datetime, timedelta

from langchain_core.prompts import PromptTemplate
from soleil import generate_time, random_name
from soleil.data.combination import (generate_mask_combinations,
                                     load_mask_combinations,
                                     save_mask_combinations)

# ============== SAMPLERS: 所有动态字段的生成规则 ==============
# 每个 sampler 接收 **ctx，ctx 里是前面已生成的字段值。
# 返回值：单值 或 dict（一次生成多个关联字段，如姓名组）。

# ---- 非金额字段 ----

def _sample_name(**ctx):
    """姓名组：一次调用返回 姓/名/姓名/性别。"""
    last, first = random_name.random_chinese_name_parts()
    return {
        "姓": last,
        "名": first,
        "姓名": last + first,
        "性别": random_name.generate_gender(),
    }

def _sample_current_time(**ctx):
    return generate_time.generate_random_time()

def _sample_today_date(**ctx):
    return generate_time.generate_random_date()

def _sample_days_past_due(**ctx):
    """M3+: 逾期天数 30% 概率为 361～1500，否则 90~360。"""
    tmp = random.random()
    if tmp < 0.3:
        return random.randint(361, 1500)
    else:
        return random.randint(90, 360)

def _sample_jobnumber(**ctx):
    return generate_jobnumber()

def _sample_check_time(**ctx):
    """查账时间：依赖当前时间。"""
    return get_check_time(ctx.get("当前时间", "08:00"))

def _sample_payment_date(**ctx):
    """还款日：依赖今天日期、逾期天数。"""
    today = ctx.get("今天日期")
    days = ctx.get("逾期天数", 0)
    return (datetime.strptime(today, '%Y-%m-%d')
            - timedelta(days=days)).strftime('%Y-%m-%d')

def _sample_num_tranc(**ctx):
    """逾期笔数。"""
    return 0 if random.random() < 0.4 else random.randint(1, 5)

# ---- 金额字段 ----

def _sample_total_amount(**ctx):
    """总欠款：独立生成，4 段分层概率。"""
    tmp = random.random()
    if tmp < 0.2:       # 20%
        return round(random.uniform(50, 1000), 2)
    elif tmp < 0.6:     # 40%
        return round(random.uniform(1000, 10000), 2)
    elif tmp < 0.85:    # 25%
        return round(random.uniform(10000, 100000), 2)
    else:               # 15%
        return round(random.uniform(100000, 1000000), 2)


def _sample_amount(**ctx):
    """应还金额：依赖总欠款。fallback：总欠款为 0 时独立随机。"""
    total = ctx.get("总欠款", 0.0)
    return total

def _sample_principal(**ctx):
    """本金：依赖应还金额 × (0.20~1.20)。fallback：应还金额为 0 时独立随机。"""
    amount = ctx.get("应还金额", 0.0)
    if amount > 0:
        return round(amount * random.uniform(0.20, 1.20), 2)
    else:
        return round(random.uniform(10, 50000), 2)


def _sample_interest(**ctx):
    """利息：依赖应还金额 × (0.1~0.5)。fallback：应还金额为 0 时独立随机。"""
    amount = ctx.get("应还金额", 0.0)
    if amount > 0:
        return round(amount * random.uniform(0.1, 0.5), 2)
    else:
        return round(random.uniform(5, 10000), 2)


def _sample_penalty(**ctx):
    """罚息：依赖应还金额 × (0.1~0.5)。fallback：应还金额为 0 时独立随机。"""
    amount = ctx.get("应还金额", 0.0)
    if amount > 0:
        return round(amount * random.uniform(0.1, 0.5), 2)
    else:
        return round(random.uniform(5, 10000), 2)


SAMPLERS = {
    "姓名": _sample_name,
    "当前时间": _sample_current_time,
    "今天日期": _sample_today_date,
    "逾期天数": _sample_days_past_due,
    "专员工号": _sample_jobnumber,
    "查账时间": _sample_check_time,
    "还款日": _sample_payment_date,
    "总欠款": _sample_total_amount,
    "应还金额": _sample_amount,
    "本金":   _sample_principal,
    "利息":   _sample_interest,
    "罚息":   _sample_penalty,
    "逾期笔数":   _sample_num_tranc,
}

# ============== 字段分类 ==============

# 静态字段（固定值，不参与生成）
STATIC_FIELDS = {
    "机构名称": "星图金融",
    "业务类型": "任性贷",
    "APP名称": "星图金融",
    "抬头": "星图金融",
}

# 所有动态字段（拓扑序：被依赖的在前，决定 generate_data 的计算顺序）
GENERATED_FIELDS = [
    "姓名",          # → dict: {姓, 名, 姓名, 性别}
    "当前时间",       # 独立
    "今天日期",       # 独立
    "逾期天数",       # 独立（M3+）
    "专员工号",       # 独立
    "查账时间",       # 依赖 当前时间
    "还款日",         # 依赖 今天日期, 逾期天数
    "总欠款",         # mask 驱动，独立
    "应还金额",       # 始终非 0，依赖 总欠款
    "本金",           # mask 驱动，依赖 应还金额
    "利息",           # mask 驱动，依赖 应还金额
    "罚息",           # mask 驱动，依赖 应还金额
    "逾期笔数",       # mask 驱动，独立
]

# 参与 mask 组合枚举的字段（可以为 0 或非 0）
COMBINATION_FIELDS = ["本金", "利息", "罚息", "逾期笔数"]

# 始终非 0 的字段（不参与 mask，由依赖关系计算）
ALWAYS_NONZERO_FIELDS = ["应还金额"]

# 需要 2 位小数格式化的字段
NUMERIC_FIELDS = ["总欠款", "应还金额", "本金", "利息", "罚息"]


# ============== 工具函数 ==============

def get_check_time(current_time):
    """根据当前时间生成查账时间（当前时间+至少2小时）"""
    hour, minute = map(int, current_time.split(':'))
    min_check_hour = hour + 3

    available_times = []
    time_mapping = {
        "今天中午12点": 12,
        "今天下午1点": 13,
        "今天下午2点": 14,
        "今天下午3点": 15,
        "今天下午4点": 16,
        "今天下午5点": 17,
        "今天下午6点": 18,
        "今天晚上8点": 20,
    }
    available_times = [t for t, h in time_mapping.items() if h >= min_check_hour]

    if not available_times:
        return "今天晚上8点"
    return random.choice(available_times)

def generate_jobnumber():
    """
    生成符合分布规律的专员工号。
    分为四段区间，概率分别为 20%、30%、20%、30%。
    """
    tmp = random.random()
    if tmp < 0.2:
        return random.randint(1000, 100000)
    elif tmp < 0.5:      # 0.2 ~ 0.5 → 30%
        return random.randint(100000, 1000000)
    elif tmp < 0.7:      # 0.5 ~ 0.7 → 20%
        return random.randint(1000000, 10000000)
    else:                # 0.7 ~ 1.0 → 30%
        return random.randint(10000000, 100000000)

def generate_data(mask_dict):
    """根据 mask 生成一条 case 数据。

    所有动态字段统一走 SAMPLERS 循环，按 GENERATED_FIELDS 拓扑序执行：
      - COMBINATION_FIELDS + mask=0 → 直接写 0
      - COMBINATION_FIELDS + mask=1 → 调 sampler
      - ALWAYS_NONZERO_FIELDS       → 始终调 sampler
      - 其他字段                     → 始终调 sampler
    sampler 返回 dict 时合并多个关联字段（如姓名组）。
    """
    values = {}
    for field in GENERATED_FIELDS:
        if field in COMBINATION_FIELDS and mask_dict.get(field, 0) == 0:
            values[field] = 0
        else:
            result = SAMPLERS[field](**values)
            if isinstance(result, dict):
                values.update(result)  # 姓名组等：一次填充多个字段
            else:
                values[field] = result

    # 金额字段格式化为 2 位小数字符串
    for f in NUMERIC_FIELDS:
        values[f] = "{:.2f}".format(values[f])

    return {**STATIC_FIELDS, **values}


def load_and_format_prompt_system(prompt_path, data):
    """加载 prompt template，替换 case 标签。"""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt_template_load = PromptTemplate.from_template(prompt_template)
    return prompt_template_load.format(
        jobnumber=data["专员工号"],
        info_name=data["姓名"],
        info_gender=data["性别"],
        payment_date=data["还款日"],
        today_date=data["今天日期"],
        days_past_due=data['逾期天数'],
        num_tranc=data['逾期笔数'],
        time_check=data["查账时间"],
        total_amount=data["总欠款"],
        principal=data["本金"],
        amount=data["应还金额"],
        interest=data["利息"],
        penalty=data["罚息"],
    )


def load_and_format_prompt_replace(prompt_path, data):
    """加载 prompt template（带查账时间 + 元后缀）。"""
    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    prompt_template_load = PromptTemplate.from_template(prompt_template)
    return prompt_template_load.format(
        jobnumber=data["专员工号"],
        info_name=data["姓名"],
        info_gender=data["性别"],
        info_last_name=data["姓"],
        days_past_due=data['逾期天数'],
        num_tranc=data['逾期笔数'],
        today_date=data["今天日期"],
        payment_date=data["还款日"],
        time_check=data["查账时间"],
        current_time=data["当前时间"],
        total_amount=data["总欠款"] + '元',
        principal=data["本金"] + '元',
        amount=data["应还金额"] + '元',
        interest=data["利息"] + '元',
        penalty=data["罚息"] + '元',
    )


# ============== 主流程：M3+（首催）=============
def generate(config):
    # ========== 1. 准备组合（共用枚举，两份都基于同一组合集） ==========
    combos = generate_mask_combinations(COMBINATION_FIELDS)
    save_mask_combinations(combos, config["combinations_path"])
    print(f"生成并保存 {len(combos)} 种组合到 {config['combinations_path']}")

    # ========== 2. 组织两份任务 ==========
    tasks = [{
        "label":       "主 case",
        "seed":        config["seed"],
        "total":       config["total_cases"],
        "system_dir":  config["system_dir"],
        "replace_dir": config["replace_dir"],
        "start":       0,                       # 主输出从 case_1 开始
    }]
    tcfg = config.get("testify")
    if tcfg:
        tasks.append({
            "label":       "testify",
            "seed":        tcfg["seed"],        # ← 独立 seed，保证内容不同
            "total":       tcfg["end"] - tcfg["start"] + 1,
            "system_dir":  tcfg["system_dir"],
            "replace_dir": tcfg["replace_dir"],
            "start":       tcfg["start"],       # 从 case_{start} 开始编号
        })

    # ========== 3. 依次执行两轮 ==========
    for task in tasks:
        random.seed(task["seed"])               # ← 关键：每轮独立重置种子
        SYSTEM_DIR  = task["system_dir"]
        REPLACE_DIR = task["replace_dir"]
        TOTAL       = task["total"]
        START       = task["start"]
        os.makedirs(SYSTEM_DIR, exist_ok=True)
        os.makedirs(REPLACE_DIR, exist_ok=True)

        cases_per_combo = TOTAL // len(combos)
        remainder = TOTAL % len(combos)
        print(f"[{task['label']}] 每种组合 {cases_per_combo} 条，余 {remainder} 条 → 总计 {TOTAL}")

        case_idx = 0
        for combo in combos:
            n = cases_per_combo + (1 if combo["id"] < remainder else 0)
            for _ in range(n):
                data = generate_data(combo["mask"])

                # ---- 跟催业务线专用（仅 _follow.py / _follow.py 保留此行）----
                # follow_info = random.choice(FOLLOW_INFO_OPTIONS)

                # === system prompt ===
                prompt_system = load_and_format_prompt_system(
                    config["prompt_system_path"], data,
                    # follow_info=follow_info,   # 仅 _follow.py / _follow.py 保留此行
                )
                with open(f"{SYSTEM_DIR}/case_{START + case_idx + 1}.txt",
                          "w", encoding="utf-8") as f:
                    f.write(prompt_system)

                # === replace prompt（日期转月日格式）===
                data_copy = dict(data)
                data_copy["今天日期"] = datetime.strptime(
                    data_copy["今天日期"], "%Y-%m-%d").strftime("%m月%d日")
                data_copy["还款日"] = datetime.strptime(
                    data_copy["还款日"], "%Y-%m-%d").strftime("%m月%d日")
                prompt_replace = load_and_format_prompt_replace(
                    config["prompt_replace_path"], data_copy
                )
                with open(f"{REPLACE_DIR}/case_{START + case_idx + 1}.txt",
                          "w", encoding="utf-8") as f:
                    f.write(prompt_replace)

                case_idx += 1

        print(f"[{task['label']}] 完成，共生成 {case_idx} 条")