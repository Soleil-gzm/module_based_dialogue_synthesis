"""
调试 B_set 模块到 A_set 模块的概率分布
"""

import sys
sys.path.insert(0, "scripts_general")

from core.config import load_config
from core.data_loader import load_prob_matrix


def debug_b_to_a_prob():
    # 加载配置
    config = load_config("configs/general_Xiaoying_dynamic_0622.yaml")
    a_set = config.get("a_set", [])
    b_set = config.get("b_set", [])
    
    # 加载 prob 表
    prob_df, modules = load_prob_matrix(config.get("prob_path"))
    
    print("B_set 模块到 A_set 模块的概率分布：")
    print("=" * 100)
    
    for b_mod in b_set[:3]:  # 只看前3个 B_set 模块
        print(f"\n从 {b_mod} 出发：")
        print("-" * 100)
        row = prob_df.loc[b_mod]
        
        # 显示到所有 A_set 模块的概率
        a_probs = row[row.index.isin(a_set)]
        print("到 A_set 模块的概率：")
        for a_mod in a_set:
            prob = row[a_mod]
            if prob > 0:
                print(f"  {a_mod:<15}: {prob:.4f}")
        
        # 计算到 A_set 的总概率
        total_a_prob = a_probs.sum()
        print(f"\n到 A_set 的总概率: {total_a_prob:.4f}")
        
        # 显示到 B_set 模块的概率
        b_probs = row[row.index.isin(b_set)]
        print("\n到 B_set 模块的概率（前5个）：")
        for b_mod2 in b_set[:5]:
            prob = row[b_mod2]
            if prob > 0:
                print(f"  {b_mod2:<15}: {prob:.4f}")


if __name__ == "__main__":
    debug_b_to_a_prob()
