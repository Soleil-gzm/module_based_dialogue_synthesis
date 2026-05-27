'''
Step 5：拆分路径生成器
操作：创建 core/path_generator.py，类 PathGenerator：

初始化接收 config（含模块列表、MAX_REPEAT、A/B集、终止模块等）和 prob_df

方法 generate(num_paths, seed) 返回 List[List[str]]

内部实现当前 generate_path 的逻辑，支持缓存。
原因：路径生成是独立业务逻辑，单独封装后可单独优化或替换（如改用概率矩阵采样不同算法）。
'''

import json
import random
import numpy as np
import pandas as pd
from typing import List, Set, Dict, Optional
from core.config import Config

class PathGenerator:
    """根据概率矩阵和业务规则生成模块序列"""
    def __init__(self, config: Config, prob_df: pd.DataFrame):
        self.config = config
        self.prob_df = prob_df
        self.modules = config.get('modules')
        self.max_repeat = config.get('max_repeat')
        self.terminal_nodes = set(config.get('terminal_modules', []))
        self.a_set = set(config.get('a_set', []))
        self.b_set = set(config.get('b_set', []))
        self.start_module = config.get('start_module', self.modules[0])

    def generate_one(self) -> List[str]:
        """生成一条模块路径"""
        path = [self.start_module]
        counts = {mod: 0 for mod in self.modules}
        counts[self.start_module] = 1
        banned = set()
        selected_a = None
        current = self.start_module

        while True:
            # 确定候选集
            if current == "身份确认":
                candidates = ["告知", "三方"]
            elif current == "告知":
                candidates = [m for m in self.modules if m not in ["身份确认", "转告"]]
            elif current == "信息核实":
                candidates = [m for m in self.modules if m not in ["告知", "身份确认", "三方", "转告"]]
            elif current in self.a_set:
                candidates = [current] + list(self.b_set)
            elif current in self.b_set:
                candidates = list(self.b_set)
                if selected_a is not None:
                    candidates.append(selected_a)
            else:
                candidates = self.modules[:]

            # 移除禁用模块
            candidates = [m for m in candidates if m not in banned]
            # 如果已有选中的A集，禁止其他A集
            if selected_a is not None:
                candidates = [m for m in candidates if m not in self.a_set or m == selected_a]

            if not candidates:
                break

            # 概率选择
            probs = self.prob_df.loc[current].copy()
            probs = probs[probs.index.isin(candidates)]
            if probs.sum() == 0:
                break
            probs /= probs.sum()
            next_node = np.random.choice(probs.index, p=probs)

            # 硬约束：已还款只能从告知或信息核实进入
            if next_node == "已还款" and current not in ["告知", "信息核实"]:
                continue

            # 记录选中的A集
            if next_node in self.a_set and selected_a is None:
                selected_a = next_node

            path.append(next_node)
            counts[next_node] += 1

            # 达到最大重复次数则禁用（不终止）
            max_repeat_val = self.max_repeat.get(next_node, 100)
            if counts[next_node] >= max_repeat_val:
                banned.add(next_node)

            # 终止模块则结束
            if next_node in self.terminal_nodes:
                break

            current = next_node

        return path

    def generate(self, num_paths: int, seed: int, cache_path: Optional[str] = None) -> List[List[str]]:
        """生成多条不重复路径，支持缓存"""
        random.seed(seed)
        np.random.seed(seed)

        if cache_path:
            import os
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get("seed") == seed and cache_data.get("num_paths") == num_paths:
                    print(f"从缓存加载 {len(cache_data['paths'])} 条路径")
                    return cache_data["paths"]
                else:
                    print("缓存种子或数量不匹配，重新生成")

        paths = []
        paths_set = set()
        max_attempts = num_paths * 10
        attempts = 0
        while len(paths) < num_paths and attempts < max_attempts:
            attempts += 1
            path = self.generate_one()
            path_tuple = tuple(path)
            if path_tuple not in paths_set:
                paths_set.add(path_tuple)
                paths.append(path)
            if attempts % 10000 == 0:
                print(f"已尝试 {attempts} 次，当前唯一路径数 {len(paths)}")

        if len(paths) < num_paths:
            print(f"警告：仅生成 {len(paths)} 条不重复路径，达到最大尝试次数")

        if cache_path:
            cache_data = {"seed": seed, "num_paths": num_paths, "paths": paths}
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

        return paths