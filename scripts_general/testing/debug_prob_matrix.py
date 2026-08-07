"""
调试 prob 表中 A_set 模块之间的概率值
"""

import sys
sys.path.insert(0, "scripts_general")

from core.config import load_config
from core.data_loader import load_prob_matrix


def debug_prob_matrix():
    # 加载配置
    config = load_config("configs/general_Xiaoying_dynamic_0622.yaml")
    a_set = config.get("a_set", [])
    
    # 加载 prob 表
    prob_df, modules = load_prob_matrix(config.get("prob_path"))
    
    print("A_set 模块列表：", a_set)
    print("\nA_set 模块之间的概率矩阵：")
    print("-" * 80)
    
    # 显示 a_set 模块之间的概率
    a_set_df = prob_df.loc[a_set, a_set]
    print(a_set_df)
    
    print("\n" + "=" * 80)
    print("检查每个 A_set 模块到其他 A_set 模块的概率之和：")
    print("-" * 80)
    
    for mod in a_set:
        row = prob_df.loc[mod]
        other_a_prob = row[row.index.isin(a_set) & (row.index != mod)].sum()
        self_prob = row[mod]
        print(f"{mod:<15} 自身概率: {self_prob:.4f}  其他A_set概率之和: {other_a_prob:.4f}  累加后: {self_prob + other_a_prob:.4f}")


if __name__ == "__main__":
    debug_prob_matrix()
