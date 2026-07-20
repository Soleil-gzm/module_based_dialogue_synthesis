import json
import logging
import os
from typing import List, Optional, Set

import numpy as np
import pandas as pd
from core.config import Config
from core.random_service import RandomService


class PathGenerator:
    def __init__(
        self,
        config: Config,
        prob_df: pd.DataFrame,
        rng: RandomService,
        logger: logging.Logger = None,
    ):
        self.config = config
        self.prob_df = prob_df
        self.rng = rng
        self.logger = logger or logging.getLogger("PathGenerator")
        self.modules = config.get("modules")            # 所有模块列表
        self.max_repeat = config.get("max_repeat")      # 每个模块最大重复次数
        self.terminal_nodes = set(config.get("terminal_modules", []))       # 终止模块
        self.a_set = set(config.get("a_set", []))
        self.b_set = set(config.get("b_set", []))
        self.start_module = config.get("start_module", self.modules[0])
        self.cache_path_template = config.get("paths_cache")
        self.self_loop_modules = config.get("self_loop_modules", {})
        self.transition_rules = config.get("transition_rules", {})      # 跳转规则

        # 验证缓存模板是否包含必要占位符
        if self.cache_path_template:
            if (
                "{num_paths}" not in self.cache_path_template
                or "{seed}" not in self.cache_path_template
            ):
                self.logger.warning(
                    f"缓存路径模板 {self.cache_path_template} 缺少 {{num_paths}} 或 {{seed}} 占位符，"
                    "生成的缓存文件可能会互相覆盖。建议修改为类似 'intermediate/all_paths_{num_paths}_{seed}.json'"
                )

    def _get_candidates_by_rules(self, current: str) -> List[str]:
        """
        根据配置的跳转规则获取当前模块的候选目标模块列表。
        
        规则优先级：
        1. 如果当前模块在 transition_rules 中有配置，按配置规则筛选
        2. 如果当前模块在 a_set 中，候选为 [current] + b_set
        3. 如果当前模块在 b_set 中，候选为 b_set（后续会追加 selected_a）
        4. 默认候选为所有模块
        
        Returns:
            List[str]: 候选模块列表
        """
        # 优先使用配置的跳转规则
        rule = self.transition_rules.get(current)
        if rule:
            mode = rule.get("mode", "deny_list")
            rule_modules = rule.get("modules", [])
            
            if mode == "allow_list":
                return rule_modules
            elif mode == "deny_list":
                return [m for m in self.modules if m not in rule_modules]
            else:
                self.logger.warning(f"未知的跳转规则模式: {mode}，使用默认规则")
        
        # A_set/B_set 规则（已配置化）
        if current in self.a_set:
            return [current] + list(self.b_set)
        elif current in self.b_set:
            return list(self.b_set)
        
        # 默认：所有模块
        return self.modules[:]

    def generate_one(self) -> List[str]:
        if self.self_loop_modules:
            rand_val = self.rng.uniform(0, 1)
            cum_prob = 0.0
            for module, prob in self.self_loop_modules.items():
                cum_prob += prob
                if rand_val < cum_prob:
                    max_repeat_val = self.max_repeat.get(module, 1)
                    return [module] * max_repeat_val

        path = [self.start_module]
        counts = {mod: 0 for mod in self.modules}
        counts[self.start_module] = 1
        banned = set()
        selected_a = None
        current = self.start_module

        while True:
            candidates = self._get_candidates_by_rules(current)
            
            if current in self.b_set and selected_a is not None:
                candidates.append(selected_a)

            candidates = [m for m in candidates if m not in banned]
            if selected_a is not None:
                candidates = [
                    m for m in candidates if m not in self.a_set or m == selected_a
                ]
            if self.self_loop_modules:
                candidates = [m for m in candidates if m not in self.self_loop_modules]
            for terminal_mod in self.terminal_nodes:
                if terminal_mod not in candidates:
                    prob_val = self.prob_df.loc[current].get(terminal_mod)
                    if pd.notna(prob_val) and prob_val > 0:
                        candidates.append(terminal_mod)
            if not candidates:
                break

            probs = self.prob_df.loc[current].copy()

            # 增强从 B_set 跳回被选中 A_set 模块的概率
            # 由于路径中只能有一个 A_set 模块，将其他 A_set 模块的概率累加到 selected_a
            if current in self.b_set and selected_a is not None:
                # 计算其他 A_set 模块的概率之和
                other_a_prob = probs[
                    probs.index.isin(self.a_set) & (probs.index != selected_a)
                ].sum()
                # 如果 selected_a 在 probs 中，累加概率
                if selected_a in probs.index and other_a_prob > 0:
                    probs[selected_a] = probs[selected_a] + other_a_prob

            probs = probs[
                probs.index.isin(candidates)
            ]  # 只保留当前模块到 candidates 列表中模块的转移概率，移除那些不符合候选规则的目标模块。

            if probs.sum() == 0:
                break
            probs /= probs.sum()
            # print(probs.sum())
            # 使用 numpy 随机选择（通过 self.rng 管理种子）
            next_node = self.rng.np_choice(probs.index.to_numpy(), p=probs.to_numpy())

            if next_node in self.a_set and selected_a is None:
                selected_a = next_node

            path.append(next_node)
            counts[next_node] += 1
            max_repeat_val = self.max_repeat.get(next_node, 100)
            if counts[next_node] >= max_repeat_val:
                banned.add(next_node)
                
                rule = self.transition_rules.get(next_node)
                if rule and rule.get("force_stop_on_max_repeat", False):
                    break
            
            if next_node in self.terminal_nodes:
                break
            current = next_node
        return path

    def generate(
        self, num_paths: int, seed: int, cache_path: Optional[str] = None
    ) -> List[List[str]]:
        """生成多条路径，支持缓存（缓存文件名默认包含参数，避免覆盖）
        
        注意：路径可以重复生成，直接按 num_paths 数量生成，不去重。
        """
        if cache_path is None and self.cache_path_template:
            try:
                cache_path = self.cache_path_template.format(
                    num_paths=num_paths, seed=seed
                )
            except KeyError as e:
                self.logger.error(
                    f"缓存模板缺少占位符 {e}，请确保模板包含 {{num_paths}} 和 {{seed}}"
                )
                raise

        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            if (
                cache_data.get("seed") == seed
                and cache_data.get("num_paths") == num_paths
            ):
                self.logger.info(
                    f"从缓存加载 {len(cache_data['paths'])} 条路径 (文件: {cache_path})"
                )
                return cache_data["paths"]
            else:
                self.logger.info("缓存种子或数量不匹配，重新生成路径")

        self.logger.info(f"开始生成 {num_paths} 条路径...")
        paths = []
        for i in range(num_paths):
            path = self.generate_one()
            paths.append(path)
            if (i + 1) % 10000 == 0:
                self.logger.info(f"已生成 {i + 1}/{num_paths} 条路径")

        if cache_path:
            cache_data = {"seed": seed, "num_paths": num_paths, "paths": paths}
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.info(f"路径缓存已保存至 {cache_path}")

        return paths
