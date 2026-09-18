import random
from datetime import datetime, timedelta
import json

from langchain_core.prompts import PromptTemplate
from soleil.data.combination import (
    generate_mask_combinations,
    save_mask_combinations,
    load_mask_combinations,
)

random.seed(39)

from soleil import random_name
from soleil import generate_time


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
    """S1: 首催，逾期天数1~31。"""
    return random.randint(1, 31)

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
    if total > 0:
        tmp = random.random()
        if tmp < 0.5:       # 50% → 总欠款的 5%~30%
            return round(total * random.uniform(0.05, 0.30), 2)
        elif tmp < 0.8:     # 30% → 总欠款的 30%~95%
            return round(total * random.uniform(0.30, 0.95), 2)
        else:               # 20% → = 总欠款
            return round(total, 2)
    else:
        tmp = random.random()
        if tmp < 0.3:
            return round(random.uniform(10, 1000), 2)
        elif tmp < 0.8:
            return round(random.uniform(1000, 10000), 2)
        else:
            return round(random.uniform(1000, 100000), 2)


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
    "逾期天数",       # 独立（S1: 1~30）
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
COMBINATION_FIELDS = ["总欠款", "本金", "利息", "罚息", "逾期笔数"]

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
    for time_str, time_hour in time_mapping.items():
        if time_hour >= min_check_hour:
            available_times.append(time_str)

    if not available_times:
        return "今天晚上8点"
    return available_times[0]

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
        days_past_due=data['逾期天数'],
        num_tranc=data['逾期笔数'],
        today_date=data["今天日期"],
        time_check=data["查账时间"],
        payment_date=data["还款日"],
        amount=data["应还金额"],
        total_amount=data["总欠款"],
        principal=data["本金"],
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
        time_check=data["查账时间"],
        current_time=data["当前时间"],
        payment_date=data["还款日"],
        amount=data["应还金额"] + '元',
        total_amount=data["总欠款"] + '元',
        principal=data["本金"] + '元',
        interest=data["利息"] + '元',
        penalty=data["罚息"] + '元',
    )


# ============== 主流程：S1（首催）=============

if __name__ == "__main__":
    import os

    COMBINATIONS_PATH = "combinations-S1-6w.json"
    TOTAL_CASES = 60000
    START_INDEX = 0
    # 验证集
    # TOTAL_CASES = 100
    # START_INDEX = 200 

    # ---- 每次重新生成，直接覆盖 ----
    combos = generate_mask_combinations(COMBINATION_FIELDS)
    save_mask_combinations(combos, COMBINATIONS_PATH)
    print(f"生成并保存 {len(combos)} 种组合到 {COMBINATIONS_PATH}")

    # ---- 均衡分配：每种组合生成相同数量 ----
    cases_per_combo = TOTAL_CASES // len(combos)
    remainder = TOTAL_CASES % len(combos)
    print(f"每种组合 {cases_per_combo} 条，余 {remainder} 条分配给前 {remainder} 种 → 总计 {TOTAL_CASES}")

    # ---- 输出目录（自动创建）----
    SYSTEM_DIR = "datas/suning-notdueS1-0918/S1/S1-6w/systemS1-6w"
    REPLACE_DIR = "datas/suning-notdueS1-0918/S1/S1-6w/replaceS1-6w"

    # 验证集
    # SYSTEM_DIR = "datas/suning-notdueM0-0917/M0/testify/system400"
    # REPLACE_DIR = "datas/suning-notdueM0-0917/M0/testify/replace400"
    os.makedirs(SYSTEM_DIR, exist_ok=True)
    os.makedirs(REPLACE_DIR, exist_ok=True)

    # ---- 生成 ----
    case_idx = 0
    for combo in combos:
        n = cases_per_combo + (1 if combo["id"] < remainder else 0)
        for _ in range(n):
            data = generate_data(combo["mask"])

            # === system prompt ===
            prompt_system = load_and_format_prompt_system(
                "scripts_general/case_generator/prompt/S1_due/prompt_template_for_system-S1-new-0918.txt", data
            )
            with open(f"{SYSTEM_DIR}/case_{START_INDEX +case_idx+1}.txt",
                      "w", encoding="utf-8") as f:
                f.write(prompt_system)

            # === replace prompt（日期转月日格式）===
            data_copy = dict(data)
            data_copy["今天日期"] = datetime.strptime(
                data_copy["今天日期"], "%Y-%m-%d").strftime("%m月%d日")
            data_copy["还款日"] = datetime.strptime(
                data_copy["还款日"], "%Y-%m-%d").strftime("%m月%d日")
            prompt_replace = load_and_format_prompt_replace(
                "scripts_general/case_generator/prompt/prompt_template_for_backbone_replace.txt", data_copy
            )
            with open(f"{REPLACE_DIR}/case_{START_INDEX +case_idx+1}.txt",
                      "w", encoding="utf-8") as f:
                f.write(prompt_replace)

            case_idx += 1

    print(f"完成，共生成 {case_idx} 条 case（S1: 首催）")
