"""
Step 4：拆分数据加载模块
操作：创建 core/data_loader.py，包含：

load_sheets(excel_path, modules, condition_keyword)：返回 {module: DataFrame}

load_prob_matrix(prob_path, modules)

load_cases(cases_dir)：返回 (cases_list, prompts_list)
原因：数据准备逻辑独立，便于测试和复用（例如更换 Excel 来源）。
"""

import os
import random
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from core.random_service import RandomService  # 新增导入


def load_sheets(
    excel_path: str, modules: List[str], keep_cols: List[str] = None
) -> Dict[str, pd.DataFrame]:
    """
    加载所有模块sheet，保留所有行（不再预过滤条件）。
    条件筛选将在 DialogueBuilder 中由 ConditionEvaluator 动态执行。
    """
    df_dict = {}
    for sheet in modules:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        if keep_cols is None:
            # 默认保留所有核心列（可根据需要增减）
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
        # 只保留需要的列，但不进行行过滤
        df_filtered = (
            df[keep_cols].copy()
            if all(c in df.columns for c in keep_cols)
            else df.loc[:, keep_cols].copy()
        )
        df_dict[sheet] = df_filtered
    return df_dict


def load_prob_matrix(prob_path: str, modules: List[str]) -> pd.DataFrame:
    """加载概率矩阵，第一行和第一列为模块名，值除以100"""
    prob_df = pd.read_excel(prob_path, header=0, index_col=0)
    prob_df = prob_df.reindex(index=modules, columns=modules)
    prob_df = prob_df / 100.0
    return prob_df


# def parse_case_info(
#     txt_path: str, rng: Optional[RandomService] = None
# ) -> Dict[str, Any]:
#     """解析单个案例文件，返回字段字典。如果提供 rng，则使用它生成随机值；否则使用全局 random。"""
#     data = {}
#     with open(txt_path, "r", encoding="utf-8") as f:
#         lines = f.readlines()
#     for line in lines:
#         line = line.strip()
#         if line.startswith("- 客服电话："):
#             data["客服电话"] = line.split("：")[1].strip()
#         elif line.startswith("- 机构名称："):
#             data["机构名称"] = line.split("：")[1].strip()
#         elif line.startswith("- 业务类型："):
#             data["业务类型"] = line.split("：")[1].strip()
#         elif line.startswith("- APP名称："):
#             data["APP名称"] = line.split("：")[1].strip()
#         elif line.startswith("- 抬头："):
#             data["抬头"] = line.split("：")[1].strip()
#         elif line.startswith("- 专员工号："):
#             data["专员工号"] = line.split("：")[1].strip()
#         elif line.startswith("- 客户姓名："):
#             data["客户姓名"] = line.split("：")[1].strip()
#         elif line.startswith("- 客户性别："):
#             data["客户性别"] = line.split("：")[1].strip()
#         elif line.startswith("- 客户姓氏："):
#             data["客户姓氏"] = line.split("：")[1].strip()
#         elif line.startswith("- 逾期天数："):
#             data["逾期天数"] = line.split("：")[1].strip()
#         elif line.startswith("- 今天日期："):
#             data["今天日期"] = line.split("：")[1].strip()
#         elif line.startswith("- 查账时间："):
#             data["查账时间"] = line.split("：")[1].strip()
#         elif line.startswith("- 当前时间："):
#             data["当前时间"] = line.split("：")[1].strip()
#         elif line.startswith("- 还款日："):
#             data["还款日"] = line.split("：")[1].strip()
#         elif line.startswith("- 逾期金额："):
#             data["逾期金额"] = line.split("：")[1].strip()
#         elif line.startswith("- 总欠款："):
#             data["总欠款"] = line.split("：")[1].strip()
#         elif line.startswith("- 本金："):
#             data["本金"] = line.split("：")[1].strip()
#         elif line.startswith("- 利息："):
#             data["利息"] = line.split("：")[1].strip()
#         elif line.startswith("- 违约金："):
#             data["违约金"] = line.split("：")[1].strip()
#         elif line.startswith("- 罚息："):
#             data["罚息"] = line.split("：")[1].strip()

#     # 获取逾期金额，防御处理
#     overdue_amount_str = data.get("逾期金额", "0")
#     try:
#         overdue_amount = float(overdue_amount_str)
#     except (ValueError, TypeError):
#         overdue_amount = 0.0
#         # 使用 print 或 logging 记录警告，建议使用 logging（需要先导入）
#         import logging

#         logging.warning(f"无法解析逾期金额: '{overdue_amount_str}'，使用默认值 0")

#     # 生成随机金额：逾期金额的 30%~70%
#     if rng is not None:
#         random_ratio = rng.uniform(0.3, 0.7)
#         random_hour = rng.randint(1, 4)
#         random_digits = rng.randint(100, 999)
#     else:
#         random_ratio = random.uniform(0.3, 0.7)
#         random_hour = random.randint(1, 4)
#         random_digits = random.randint(100, 999)

#     data["随机金额"] = str(round(float(data.get("逾期金额", 0)) * random_ratio))
#     # 随机时间：查账时间 + 1~4小时
#     data["随机时间"] = f"{data.get('查账时间', '')}过后{random_hour}小时"
#     data["随机数字"] = str(random_digits)
#     return data


def parse_case_info(
    txt_path: str, rng: Optional[RandomService] = None
) -> Dict[str, Any]:
    """解析单个案例文件，返回字段字典。如果提供 rng，则使用它生成随机值；否则使用全局 random。"""
    import re

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
            data["逾期天数"] = line.split("：")[1].strip()
        elif line.startswith("- 今天日期："):
            data["今天日期"] = line.split("：")[1].strip()
        elif line.startswith("- 查账时间："):
            data["查账时间"] = line.split("：")[1].strip()
        elif line.startswith("- 当前时间："):
            data["当前时间"] = line.split("：")[1].strip()
        elif line.startswith("- 还款日："):
            data["还款日"] = line.split("：")[1].strip()
        elif line.startswith("- 逾期金额："):
            raw = line.split("：")[1].strip()
            data["逾期金额"] = raw  # 保留原始字符串（带单位）
            # 提取数值部分
            match = re.search(r"[\d.]+", raw)
            if match:
                data["逾期金额_数值"] = float(match.group())
            else:
                data["逾期金额_数值"] = 0.0
        elif line.startswith("- 总欠款："):
            raw = line.split("：")[1].strip()
            data["总欠款"] = raw
            match = re.search(r"[\d.]+", raw)
            if match:
                data["总欠款_数值"] = float(match.group())
            else:
                data["总欠款_数值"] = 0.0
        elif line.startswith("- 本金："):
            raw = line.split("：")[1].strip()
            data["本金"] = raw
            match = re.search(r"[\d.]+", raw)
            if match:
                data["本金_数值"] = float(match.group())
            else:
                data["本金_数值"] = 0.0
        elif line.startswith("- 利息："):
            raw = line.split("：")[1].strip()
            data["利息"] = raw
            match = re.search(r"[\d.]+", raw)
            if match:
                data["利息_数值"] = float(match.group())
            else:
                data["利息_数值"] = 0.0
        elif line.startswith("- 违约金："):
            raw = line.split("：")[1].strip()
            data["违约金"] = raw
            match = re.search(r"[\d.]+", raw)
            if match:
                data["违约金_数值"] = float(match.group())
            else:
                data["违约金_数值"] = 0.0
        elif line.startswith("- 罚息："):
            raw = line.split("：")[1].strip()
            data["罚息"] = raw
            match = re.search(r"[\d.]+", raw)
            if match:
                data["罚息_数值"] = float(match.group())
            else:
                data["罚息_数值"] = 0.0

    # 获取逾期金额数值（优先使用已提取的数值）
    overdue_amount = data.get("逾期金额_数值", 0.0)

    # 生成随机金额：逾期金额的 30%~70%
    if rng is not None:
        random_ratio = rng.uniform(0.3, 0.7)
        random_hour = rng.randint(1, 4)
        random_digits = rng.randint(100, 999)
    else:
        random_ratio = random.uniform(0.3, 0.7)
        random_hour = random.randint(1, 4)
        random_digits = random.randint(100, 999)

    data["随机金额"] = str(round(overdue_amount * random_ratio))
    # 随机时间：查账时间 + 1~4小时
    data["随机时间"] = f"{data.get('查账时间', '')}过后{random_hour}小时"
    data["随机数字"] = str(random_digits)
    return data


def load_cases(
    cases_dir: str, rng: Optional[RandomService] = None
) -> Tuple[List[Dict], List[str]]:
    """加载所有案例，返回 (cases列表, prompts列表)。如果提供 rng，则传递给 parse_case_info。"""
    case_files = sorted([f for f in os.listdir(cases_dir) if f.endswith(".txt")])
    cases = []
    prompts = []
    for fname in case_files:
        path = os.path.join(cases_dir, fname)
        cases.append(parse_case_info(path, rng=rng))
        with open(path, "r", encoding="utf-8") as f:
            prompts.append(f.read())
    return cases, prompts


def load_replace_cases(
    replace_dir: str, rng: Optional[RandomService] = None
) -> List[Dict[str, Any]]:
    """从 cases_replace 文件夹加载所有用于占位替换的案例，返回字典列表。"""
    case_files = sorted([f for f in os.listdir(replace_dir) if f.endswith(".txt")])
    cases = []
    for fname in case_files:
        path = os.path.join(replace_dir, fname)
        cases.append(parse_case_info(path, rng=rng))
    return cases


def load_system_prompts(system_dir: str) -> List[str]:
    """从 cases_system 文件夹加载所有系统提示文本（原始内容）。"""
    prompt_files = sorted([f for f in os.listdir(system_dir) if f.endswith(".txt")])
    prompts = []
    for fname in prompt_files:
        path = os.path.join(system_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            prompts.append(f.read())
    return prompts
