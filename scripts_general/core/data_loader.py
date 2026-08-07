"""
数据加载模块。

load_sheets(excel_path, modules, keep_cols) → {module: DataFrame}
load_prob_matrix(prob_path) → (prob_df, modules)  # modules 的唯一来源
load_cases(cases_dir, rng, time_gen) → (cases_list, prompts_list)
"""

import logging
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from core.random_service import RandomService
from core.time_generator import SimpleNaturalTimeGenerator, TimeGenerator

logger = logging.getLogger(__name__)


def load_sheets(
    excel_path: str, modules: List[str], keep_cols: List[str] = None
) -> Dict[str, pd.DataFrame]:
    """
    按 prob 表定义的 modules 加载 Excel sheets，校验一致性。
    - prob 表要求的模块在 Excel 中缺失 → 报错
    - Excel 中多余的 sheet（非模块）→ 警告并忽略
    """
    xls = pd.ExcelFile(excel_path)
    excel_sheets = set(xls.sheet_names)

    # 校验：prob 表要求的模块必须存在于 Excel
    missing = [m for m in modules if m not in excel_sheets]
    if missing:
        xls.close()
        raise ValueError(f"Excel 缺少 prob 表要求的模块 sheet: {missing}")

    # 提示：Excel 中有 prob 表未定义的 sheet（忽略）
    known_extra = {"链接施压话术", "逻辑"}
    extra = excel_sheets - set(modules) - known_extra
    if extra:
        logger.warning(f"Excel 中有 prob 表未定义的 sheet（已忽略）: {extra}")

    if keep_cols is None:
        keep_cols = [
            "uid",
            "parent(继承)",
            "repeat(次数)",
            "conditions(条件)",
            "human(客户)",
            "assistant(专员)",
            "flexible_stop(可选不继承)",
            "是否再见",
        ]

    df_dict = {}
    for sheet in modules:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        # 只保留需要的列，但不进行行过滤
        df_filtered = (
            df[keep_cols].copy()
            if all(c in df.columns for c in keep_cols)
            else df.loc[:, keep_cols].copy()
        )
        df_dict[sheet] = df_filtered
    xls.close()
    return df_dict


def load_prob_matrix(prob_path: str) -> Tuple[pd.DataFrame, List[str]]:
    """
    加载概率矩阵，模块名从 index/columns 提取（唯一来源）。
    校验行列模块名一致后返回 (prob_df, modules)。
    """
    prob_df = pd.read_excel(prob_path, header=0, index_col=0)

    # 标准化模块名（strip 空白）
    modules = [str(m).strip() for m in prob_df.index]
    prob_df.index = modules
    prob_df.columns = [str(c).strip() for c in prob_df.columns]

    # 校验行列一致（以行模块名为基准）
    row_modules = set(prob_df.index)
    col_modules = set(prob_df.columns)
    missing_cols = row_modules - col_modules
    extra_cols = col_modules - row_modules

    if missing_cols:
        raise ValueError(
            f"prob 表列缺少行中定义的模块:\n"
            f"  缺失列模块: {sorted(missing_cols)}\n"
            f"  行模块名: {list(prob_df.index)}"
        )
    if extra_cols:
        logger.warning(f"prob 表有多余的列（行中未定义，已忽略）: {sorted(extra_cols)}")
        prob_df = prob_df.drop(columns=list(extra_cols))

    prob_df = prob_df / 100.0
    return prob_df, modules


def parse_case_info(
    txt_path: str,
    rng: Optional[RandomService] = None,
    time_gen: Optional[TimeGenerator] = None,
) -> Dict[str, Any]:
    """
    解析单个案例文件，返回字段字典。
    如果提供 rng，则使用它生成随机值；否则使用全局 random。
    如果提供 time_gen，则用它生成自然时间；否则使用 SimpleNaturalTimeGenerator。
    """
    data = {}
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith("- 客服电话："):
            data["客服电话"] = line.split("：")[1].strip()
        elif line.startswith("- 机构名称："):
            data["机构名称"] = line.split("：")[1].strip()
        elif line.startswith("- 业务类型："):
            data["业务类型"] = line.split("：")[1].strip()
        elif line.startswith("- APP名称："):
            data["APP名称"] = line.split("：")[1].strip()
        elif line.startswith("- 抬头："):
            data["抬头"] = line.split("：")[1].strip()
        elif line.startswith("- 专员工号："):
            data["专员工号"] = line.split("：")[1].strip()
        elif line.startswith("- 客户姓名："):
            data["客户姓名"] = line.split("：")[1].strip()
        elif line.startswith("- 客户性别："):
            data["客户性别"] = line.split("：")[1].strip()
        elif line.startswith("- 客户姓氏："):
            data["客户姓氏"] = line.split("：")[1].strip()
        elif line.startswith("- 逾期天数："):
            raw_overdue = line.split("：")[1].strip()
            data["逾期天数"] = raw_overdue
            try:
                overdue_value = int(raw_overdue)
            except (ValueError, TypeError):
                overdue_value = 0
            data["逾期天数_显示"] = str(abs(overdue_value))
        elif line.startswith("- 今天日期："):
            data["今天日期"] = line.split("：")[1].strip()
        elif line.startswith("- 查账时间："):
            data["查账时间"] = line.split("：")[1].strip()
        elif line.startswith("- 当前时间："):
            data["当前时间"] = line.split("：")[1].strip()
        elif line.startswith("- 还款日："):
            data["还款日"] = line.split("：")[1].strip()
        elif line.startswith("- 应还金额："):
            raw = line.split("：")[1].strip()
            data["应还金额"] = raw
            match = re.search(r"[\d.]+", raw)
            data["应还金额_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 总欠款："):
            raw = line.split("：")[1].strip()
            data["总欠款"] = raw
            match = re.search(r"[\d.]+", raw)
            data["总欠款_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 本金："):
            raw = line.split("：")[1].strip()
            data["本金"] = raw
            match = re.search(r"[\d.]+", raw)
            data["本金_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 利息："):
            raw = line.split("：")[1].strip()
            data["利息"] = raw
            match = re.search(r"[\d.]+", raw)
            data["利息_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 违约金："):
            raw = line.split("：")[1].strip()
            data["违约金"] = raw
            match = re.search(r"[\d.]+", raw)
            data["违约金_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 罚息："):
            raw = line.split("：")[1].strip()
            data["罚息"] = raw
            match = re.search(r"[\d.]+", raw)
            data["罚息_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 应还金额："):
            raw = line.split("：")[1].strip()
            data["应还金额"] = raw
            match = re.search(r"[\d.]+", raw)
            data["应还金额_数值"] = float(match.group()) if match else 0.0
        elif line.startswith("- 总本金："):
            raw = line.split("：")[1].strip()
            data["总本金"] = raw
            match = re.search(r"[\d.]+", raw)
            data["总本金_数值"] = float(match.group()) if match else 0.0

    # 获取应还金额数值（用于随机金额生成）
    overdue_amount = data.get("应还金额_数值", 0.0)

    # 生成随机字段
    if rng is not None:
        random_ratio = rng.uniform(0.3, 0.6)          # 30%~60%
        random_digits = rng.randint(1, 10)            # 1-10 整数
        random_repay_day = rng.randint(1, 28)         # 1-28 整数
    else:
        random_ratio = random.uniform(0.3, 0.6)
        random_digits = random.randint(1, 10)
        random_repay_day = random.randint(1, 28)

    data["随机金额"] = str(round(overdue_amount * random_ratio))
    data["随机数字"] = str(random_digits)
    data["随机还款日"] = f"{random_repay_day}号"      # 新增字段

    # 生成自然口语化时间
    if rng is not None:
        if time_gen is None:
            time_gen = SimpleNaturalTimeGenerator()
        data["随机时间"] = time_gen.generate(rng, base_time=data.get("查账时间"))
    else:
        periods = ["上午", "下午"]
        period = random.choice(periods)
        hour = random.randint(9, 18)
        data["随机时间"] = f"今天{period}{hour}点"

    return data

def load_cases(
    cases_dir: str,
    rng: Optional[RandomService] = None,
    time_gen: Optional[TimeGenerator] = None,
) -> Tuple[List[Dict], List[str]]:
    """
    加载所有案例，返回 (cases列表, prompts列表)。
    如果提供 rng，则传递给 parse_case_info。
    如果提供 time_gen，则传递给 parse_case_info 用于生成自然时间。
    """
    case_files = sorted([f for f in os.listdir(cases_dir) if f.endswith(".txt")])
    cases = []
    prompts = []
    for fname in case_files:
        path = os.path.join(cases_dir, fname)
        cases.append(parse_case_info(path, rng=rng, time_gen=time_gen))
        with open(path, "r", encoding="utf-8") as f:
            prompts.append(f.read())
    return cases, prompts
