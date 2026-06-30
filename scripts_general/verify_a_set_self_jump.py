"""
验证 A_set 模块自跳转概率增强功能
统计 A_set 模块的自跳转次数
"""

import sys
sys.path.insert(0, "scripts_general")

from core.config import load_config
from core.data_loader import load_prob_matrix
from core.random_service import RandomService
from core.path_generator import PathGenerator


def verify_a_set_self_jump():
    # 加载配置
    config = load_config("configs/general_Xiaoying_dynamic_0622.yaml")
    a_set = set(config.get("a_set", []))
    
    # 加载数据
    prob_df = load_prob_matrix(config.get("prob_path"), config.get("modules"))
    rng = RandomService(config.get("random_seed"))
    
    # 创建路径生成器
    path_gen = PathGenerator(config, prob_df, rng)
    
    # 生成路径并统计
    num_paths = 10000
    self_jump_count = {mod: 0 for mod in a_set}
    a_set_total_count = {mod: 0 for mod in a_set}
    
    for _ in range(num_paths):
        path = path_gen.generate_one()
        
        for i in range(len(path) - 1):
            current = path[i]
            next_node = path[i + 1]
            
            if current in a_set:
                a_set_total_count[current] += 1
                if current == next_node:
                    self_jump_count[current] += 1
    
    # 输出结果
    print(f"生成了 {num_paths} 条路径")
    print("\nA_set 模块自跳转统计：")
    print("-" * 60)
    print(f"{'模块':<15} {'总跳转次数':<12} {'自跳转次数':<12} {'自跳转率':<10}")
    print("-" * 60)
    
    for mod in a_set:
        total = a_set_total_count[mod]
        self_jump = self_jump_count[mod]
        rate = self_jump / total * 100 if total > 0 else 0
        print(f"{mod:<15} {total:<12} {self_jump:<12} {rate:.2f}%")
    
    print("-" * 60)
    
    # 计算整体自跳转率
    total_all = sum(a_set_total_count.values())
    self_jump_all = sum(self_jump_count.values())
    overall_rate = self_jump_all / total_all * 100 if total_all > 0 else 0
    print(f"{'总计':<15} {total_all:<12} {self_jump_all:<12} {overall_rate:.2f}%")
    
    # 保存部分路径示例到文件
    print("\n正在保存前 100 条路径示例到 verify_paths_sample.json ...")
    rng2 = RandomService(config.get("random_seed"))
    path_gen2 = PathGenerator(config, prob_df, rng2)
    sample_paths = [path_gen2.generate_one() for _ in range(100)]
    
    import json
    with open("verify_paths_sample.json", "w", encoding="utf-8") as f:
        json.dump(sample_paths, f, ensure_ascii=False, indent=2)
    print("路径示例已保存到 verify_paths_sample.json")


if __name__ == "__main__":
    verify_a_set_self_jump()
