"""
案例加载器抽象及实现
支持：
- 默认加载器：从单个目录读取 .txt，同时作为 case 和 prompt（原有行为）
- 小赢加载器：从 replace_dir 加载 case 数据，从 system_dir 加载 prompt 数据
"""

import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from core.data_loader import parse_case_info  # 复用原有解析函数
from core.random_service import RandomService


class CaseLoader(ABC):
    """案例加载器抽象接口"""

    @abstractmethod
    def load(self, rng: Optional[RandomService] = None) -> Tuple[List[Dict], List[str]]:
        """
        返回 (cases_list, prompts_list)
        cases_list: 每个元素是用于占位填充的字典
        prompts_list: 每个元素是用于 system 消息的字符串
        """
        pass


class DefaultCaseLoader(CaseLoader):
    """默认加载器：与原有 data_loader.load_cases 行为一致"""

    def __init__(self, cases_dir: str):
        self.cases_dir = cases_dir

    def load(self, rng: Optional[RandomService] = None) -> Tuple[List[Dict], List[str]]:
        from core.data_loader import load_cases  # 避免循环导入

        return load_cases(self.cases_dir, rng=rng)


class XiaoyingCaseLoader(CaseLoader):
    """
    小赢专用加载器：
    - replace_dir: 存放案例数据（占位填充用），文件格式为 "- 字段：值"
    - system_dir: 存放系统提示文本，文件内容直接作为 prompt
    两个目录中的文件按文件名排序后一一对应。
    若数量不一致，以较少的为准，另一方循环复用。
    """

    def __init__(self, replace_dir: str, system_dir: str):
        self.replace_dir = replace_dir
        self.system_dir = system_dir

    def _get_sorted_files(self, directory: str, ext: str = ".txt") -> List[str]:
        files = [f for f in os.listdir(directory) if f.endswith(ext)]
        return sorted(files)

    def load(self, rng: Optional[RandomService] = None) -> Tuple[List[Dict], List[str]]:
        replace_files = self._get_sorted_files(self.replace_dir)
        system_files = self._get_sorted_files(self.system_dir)

        if not replace_files:
            raise ValueError(f"替换案例目录为空: {self.replace_dir}")
        if not system_files:
            raise ValueError(f"系统提示目录为空: {self.system_dir}")

        cases = []
        prompts = []

        # 确定配对长度：使用两个目录中文件数的最小公倍数？这里简单使用最大值并循环复用
        max_len = max(len(replace_files), len(system_files))

        for i in range(max_len):
            # 循环取 replace 文件
            replace_file = replace_files[i % len(replace_files)]
            replace_path = os.path.join(self.replace_dir, replace_file)
            case = parse_case_info(replace_path, rng=rng)  # 复用原有解析函数
            cases.append(case)

            # 循环取 system 文件
            system_file = system_files[i % len(system_files)]
            system_path = os.path.join(self.system_dir, system_file)
            with open(system_path, "r", encoding="utf-8") as f:
                prompt = f.read()
            prompts.append(prompt)

        return cases, prompts
