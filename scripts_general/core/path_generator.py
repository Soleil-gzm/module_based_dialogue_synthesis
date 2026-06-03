import json
import os
import logging
import numpy as np
import pandas as pd
from typing import List, Set, Optional
from core.config import Config
from core.random_service import RandomService

class PathGenerator:
    def __init__(self, config: Config, prob_df: pd.DataFrame, rng: RandomService, logger: logging.Logger = None):
        self.config = config
        self.prob_df = prob_df
        self.rng = rng
        self.logger = logger or logging.getLogger('PathGenerator')
        self.modules = config.get('modules')
        self.max_repeat = config.get('max_repeat')
        self.terminal_nodes = set(config.get('terminal_modules', []))
        self.a_set = set(config.get('a_set', []))
        self.b_set = set(config.get('b_set', []))
        self.start_module = config.get('start_module', self.modules[0])
        self.cache_path_template = config.get('paths_cache')

        # 验证缓存模板是否包含必要占位符
        if self.cache_path_template:
            if '{num_paths}' not in self.cache_path_template or '{seed}' not in self.cache_path_template:
                self.logger.warning(
                    f"缓存路径模板 {self.cache_path_template} 缺少 {{num_paths}} 或 {{seed}} 占位符，"
                    "生成的缓存文件可能会互相覆盖。建议修改为类似 'intermediate/all_paths_{num_paths}_{seed}.json'"
                )

    def generate_one(self) -> List[str]:
        path = [self.start_module]
        counts = {mod: 0 for mod in self.modules}
        counts[self.start_module] = 1
        banned = set()
        selected_a = None
        current = self.start_module

        while True:
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

            candidates = [m for m in candidates if m not in banned]
            if selected_a is not None:
                candidates = [m for m in candidates if m not in self.a_set or m == selected_a]
            if not candidates:
                break

            probs = self.prob_df.loc[current].copy()
            probs = probs[probs.index.isin(candidates)]     # 只保留当前模块到 candidates 列表中模块的转移概率，移除那些不符合候选规则的目标模块。
            if probs.sum() == 0:
                break
            probs /= probs.sum()
            # 使用 numpy 随机选择（通过 self.rng 管理种子）
            next_node = self.rng.np_choice(probs.index.to_numpy(), p=probs.to_numpy())

            if next_node == "已还款" and current not in ["告知", "信息核实"]:
                continue
            if next_node in self.a_set and selected_a is None:
                selected_a = next_node

            path.append(next_node)
            counts[next_node] += 1
            max_repeat_val = self.max_repeat.get(next_node, 100)
            if counts[next_node] >= max_repeat_val:
                banned.add(next_node)
            if next_node in self.terminal_nodes:
                break
            current = next_node
        return path

    def generate(self, num_paths: int, seed: int, cache_path: Optional[str] = None) -> List[List[str]]:
        """生成多条不重复路径，支持缓存（缓存文件名默认包含参数，避免覆盖）"""
        if cache_path is None and self.cache_path_template:
            try:
                cache_path = self.cache_path_template.format(num_paths=num_paths, seed=seed)
            except KeyError as e:
                self.logger.error(f"缓存模板缺少占位符 {e}，请确保模板包含 {{num_paths}} 和 {{seed}}")
                raise

        if cache_path and os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            if cache_data.get("seed") == seed and cache_data.get("num_paths") == num_paths:
                self.logger.info(f"从缓存加载 {len(cache_data['paths'])} 条路径 (文件: {cache_path})")
                return cache_data["paths"]
            else:
                self.logger.info("缓存种子或数量不匹配，重新生成路径")

        self.logger.info(f"开始生成 {num_paths} 条不重复路径...")
        paths = []
        paths_set = set()   # 确保路径唯一
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
                self.logger.info(f"已尝试 {attempts} 次，当前唯一路径数 {len(paths)}")

        if len(paths) < num_paths:
            self.logger.warning(f"仅生成 {len(paths)} 条不重复路径，达到最大尝试次数 {max_attempts}")

        if cache_path:
            cache_data = {"seed": seed, "num_paths": num_paths, "paths": paths}
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"路径缓存已保存至 {cache_path}")
            
        return paths