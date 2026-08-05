#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
筛选包含 "逾期天数：0" 或 "<逾期天数>0" 的txt文件，复制到新目录。
"""

import os
import shutil
from pathlib import Path

# ========== 硬编码配置 ==========
INPUT_DIR1 = "datas/suning/not_overdue/cases1_replace"          # 第一个输入文件夹
INPUT_DIR2 = "datas/suning/not_overdue/cases1_system"          # 第二个输入文件夹
OUTPUT_ROOT = "datas/suning/not_overdue/suning_减免加强"          # 输出根目录（将在下面创建 folder1_filtered 和 folder2_filtered）
# ===================================


def file_contains_pattern(file_path: Path, patterns: list) -> bool:
    """
    检查文件内容是否包含任意一个模式（逐行读取，内存友好）
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                for pat in patterns:
                    if pat in line:
                        return True
    except UnicodeDecodeError:
        # 如果UTF-8解码失败，尝试其他编码
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                for line in f:
                    for pat in patterns:
                        if pat in line:
                            return True
        except Exception as e:
            print(f"⚠️ 无法读取文件 {file_path}: {e}")
    except Exception as e:
        print(f"⚠️ 读取文件 {file_path} 出错: {e}")
    return False


def process_folder(input_dir: Path, output_dir: Path, patterns: list):
    """
    遍历 input_dir 下的所有 .txt 文件，如果内容包含任一 pattern，则复制到 output_dir（保持目录结构）
    """
    if not input_dir.exists():
        print(f"❌ 输入目录不存在: {input_dir}")
        return

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 递归遍历所有 .txt 文件
    for txt_file in input_dir.rglob("*.txt"):
        if file_contains_pattern(txt_file, patterns):
            # 计算相对路径（相对于输入目录）
            rel_path = txt_file.relative_to(input_dir)
            dest_file = output_dir / rel_path
            # 确保目标目录存在
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            # 复制文件（保留元数据）
            shutil.copy2(txt_file, dest_file)
            print(f"✅ 复制: {txt_file} -> {dest_file}")


def main():
    patterns = ["逾期天数：0", "<逾期天数>0"]

    # 处理第一个输入目录
    print("📁 处理第一个输入目录...")
    process_folder(Path(INPUT_DIR1), Path(OUTPUT_ROOT) / "folder1_filtered", patterns)

    # 处理第二个输入目录
    print("\n📁 处理第二个输入目录...")
    process_folder(Path(INPUT_DIR2), Path(OUTPUT_ROOT) / "folder2_filtered", patterns)

    print("\n✅ 筛选完成！")


if __name__ == "__main__":
    main()