"""
对话相邻去重模块。

对生成的对话 JSON 进行相邻重复轮对（user+assistant）去重，
调用 soleil.deduplicator.process 实现。

输出文件名为原文件名加后缀（默认 _dup）。
"""

import json
import os
from typing import Dict, Optional

try:
    from soleil import deduplicator as _soleil_dedup
    _HAS_SOLEIL = True
except ImportError:
    _HAS_SOLEIL = False


class DialogueDeduplicator:
    """对话相邻去重器。"""

    def __init__(
        self,
        threshold: float = 0.85,
        ignore_numbers: bool = True,
        output_suffix: str = "_dup",
    ):
        self.threshold = threshold
        self.ignore_numbers = ignore_numbers
        self.output_suffix = output_suffix

    def deduplicate_file(self, input_file: str) -> Optional[str]:
        """
        读取 input_file，去重后写入同目录下加后缀的文件。
        返回输出文件路径；若 soleil 未安装或失败返回 None。
        """
        if not _HAS_SOLEIL:
            return None

        if not os.path.exists(input_file):
            raise FileNotFoundError(f"输入文件不存在: {input_file}")

        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        processed, stats = _soleil_dedup.process(
            data,
            threshold=self.threshold,
            ignore_numbers=self.ignore_numbers,
            return_stats=True,
        )

        base, ext = os.path.splitext(input_file)
        output_file = f"{base}{self.output_suffix}{ext}"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)

        return output_file, stats
