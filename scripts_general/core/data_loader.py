'''
Step 4：拆分数据加载模块
操作：创建 core/data_loader.py，包含：

load_sheets(excel_path, modules, condition_keyword)：返回 {module: DataFrame}

load_prob_matrix(prob_path, modules)

load_cases(cases_dir)：返回 (cases_list, prompts_list)
原因：数据准备逻辑独立，便于测试和复用（例如更换 Excel 来源）。
'''

import os
import random
import pandas as pd
from typing import List, Dict, Tuple, Any

def load_sheets(excel_path: str, modules: List[str], condition_keyword: str = '逾期') -> Dict[str, pd.DataFrame]:
    """
    加载所有模块sheet，筛选包含 condition_keyword 的行，并过滤掉包含随机占位符的行
    """
    df_dict = {}
    for sheet in modules:
        df = pd.read_excel(excel_path, sheet_name=sheet)
        # 筛选 conditions 列包含指定关键词的行
        mask = df['conditions(条件)'].apply(lambda x: isinstance(x, str) and condition_keyword in x)
        df_filtered = df[mask].copy()
        # 去掉 human 列中包含随机标签的行
        df_filtered = df_filtered[~df_filtered['human(客户)'].str.contains('{随机金额}|{随机时间}', na=False)]
        df_dict[sheet] = df_filtered
    return df_dict

def load_prob_matrix(prob_path: str, modules: List[str]) -> pd.DataFrame:
    """加载概率矩阵，第一行和第一列为模块名，值除以100"""
    prob_df = pd.read_excel(prob_path, header=0, index_col=0)
    prob_df = prob_df.reindex(index=modules, columns=modules)
    prob_df = prob_df / 100.0
    return prob_df

def parse_case_info(txt_path: str) -> Dict[str, Any]:
    """解析单个案例文件，返回字段字典"""
    data = {}
    with open(txt_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        if line.startswith('- 客服电话：'):
            data['客服电话'] = line.split('：')[1].strip()
        elif line.startswith('- 机构名称：'):
            data['机构名称'] = line.split('：')[1].strip()
        elif line.startswith('- 业务类型：'):
            data['业务类型'] = line.split('：')[1].strip()
        elif line.startswith('- APP名称：'):
            data['APP名称'] = line.split('：')[1].strip()
        elif line.startswith('- 抬头：'):
            data['抬头'] = line.split('：')[1].strip()
        elif line.startswith('- 专员工号：'):
            data['专员工号'] = line.split('：')[1].strip()
        elif line.startswith('- 姓名：'):
            data['客户姓名'] = line.split('：')[1].strip()
        elif line.startswith('- 性别：'):
            data['客户性别'] = line.split('：')[1].strip()
        elif line.startswith('- 逾期天数：'):
            data['逾期天数'] = line.split('：')[1].strip()
        elif line.startswith('- 今天日期：'):
            data['今天日期'] = line.split('：')[1].strip()
        elif line.startswith('- 查账时间：'):
            data['查账时间'] = line.split('：')[1].strip()
        elif line.startswith('- 还款日：'):
            data['还款日'] = line.split('：')[1].strip()
        elif line.startswith('- 逾期金额：'):
            data['逾期金额'] = line.split('：')[1].strip()
        elif line.startswith('- 总欠款：'):
            data['总欠款'] = line.split('：')[1].strip()
        elif line.startswith('- 本金：'):
            data['本金'] = line.split('：')[1].strip()
    # 生成随机金额：逾期金额的 30%~70%
    data['随机金额'] = str(round(float(data.get('逾期金额', 0)) * random.uniform(0.3, 0.7)))
    # 随机时间：查账时间 + 1~4小时
    data['随机时间'] = f"{data.get('查账时间', '')}过后{random.randint(1,4)}小时"
    data['随机数字'] = str(random.randint(100, 999))
    return data

def load_cases(cases_dir: str) -> Tuple[List[Dict], List[str]]:
    """加载所有案例，返回 (cases列表, prompts列表)"""
    case_files = sorted([f for f in os.listdir(cases_dir) if f.endswith('.txt')])
    cases = []
    prompts = []
    for fname in case_files:
        path = os.path.join(cases_dir, fname)
        cases.append(parse_case_info(path))
        with open(path, 'r', encoding='utf-8') as f:
            prompts.append(f.read())
    return cases, prompts