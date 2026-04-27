#!/usr/bin/env python3
"""
生成项目结构树（至多两级）并追加到 README.md
- 排除 .git, .vscode 文件夹
- datas/ 目录只显示直接子项（不展开更深）
- 其他目录显示两级结构
- 包含所有文件（包括不被 git 追踪的）
"""

import os
from pathlib import Path

EXCLUDED_DIRS = {'.git', '.vscode'}          # 排除的目录名
DATA_DIRS = {'datas', 'data'}                # 只显示一级子项的特殊目录（不展开更深）

def generate_tree(root_dir, max_depth=2, current_depth=0, prefix='', is_last_root=False):
    """
    递归生成目录树字符串
    root_dir: 当前要扫描的目录（Path 对象）
    max_depth: 最大深度（根目录为0，第一级子项深度1，第二级深度2）
    current_depth: 当前深度
    prefix: 前缀（用于缩进）
    is_last_root: 仅在根目录的第一层子项中用于控制前缀，外部调用无需指定
    """
    lines = []
    # 获取当前目录下所有条目（文件和文件夹），排除隐藏文件？不排除，只排除特定目录
    items = sorted(root_dir.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    for i, item in enumerate(items):
        # 跳过排除的文件夹
        if item.is_dir() and item.name in EXCLUDED_DIRS:
            continue
        
        is_last = (i == len(items) - 1)
        connector = '└── ' if is_last else '├── '
        
        # 添加当前项的名称（如果是目录，加斜杠便于区分）
        display_name = item.name + '/' if item.is_dir() else item.name
        lines.append(f"{prefix}{connector}{display_name}")
        
        # 如果是目录且深度未超过限制，递归处理
        if item.is_dir() and current_depth + 1 < max_depth:
            # 特殊处理：如果当前目录是 datas/ 或 data/，则不再深入下一级
            if item.name in DATA_DIRS:
                continue
            # 递归子目录
            sub_prefix = prefix + ('    ' if is_last else '│   ')
            sub_lines = generate_tree(item, max_depth, current_depth + 1, sub_prefix, False)
            lines.extend(sub_lines)
    return lines

def main():
    # 项目根目录：脚本所在目录
    project_root = Path(__file__).parent.resolve()
    print(f"项目根目录: {project_root}")

    # 生成结构字符串（根目录深度为0，我们不显示根目录本身，只显示其下的内容）
    # 所以手动处理根目录下的第一级
    root_items = sorted(project_root.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    tree_lines = []
    for i, item in enumerate(root_items):
        if item.is_dir() and item.name in EXCLUDED_DIRS:
            continue
        is_last = (i == len(root_items) - 1)
        connector = '└── ' if is_last else '├── '
        display_name = item.name + '/' if item.is_dir() else item.name
        tree_lines.append(f"{connector}{display_name}")
        
        # 如果是目录且需要显示子项（深度1 -> 深度2）
        if item.is_dir():
            # 排除的目录已在上面跳过，这里不需要重复判断
            # 特殊处理：如果当前目录是 datas/ 或 data/，则显示其下第一级子项（深度2）但不继续深入
            if item.name in DATA_DIRS:
                # 显示其下第一级子项，但不递归更深
                sub_items = sorted(item.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                for j, sub in enumerate(sub_items):
                    if sub.is_dir() and sub.name in EXCLUDED_DIRS:
                        continue
                    sub_last = (j == len(sub_items) - 1)
                    sub_prefix = '    ' if is_last else '│   '
                    sub_connector = '└── ' if sub_last else '├── '
                    sub_display = sub.name + '/' if sub.is_dir() else sub.name
                    tree_lines.append(f"{sub_prefix}{sub_connector}{sub_display}")
            else:
                # 其他目录：递归显示其下第一级子项（深度2）
                sub_prefix = '    ' if is_last else '│   '
                sub_lines = generate_tree(item, max_depth=2, current_depth=1, prefix=sub_prefix)
                tree_lines.extend(sub_lines)

    structure_text = "\n".join(tree_lines)
    print("生成的目录树预览：")
    print(structure_text[:500] + ("..." if len(structure_text) > 500 else ""))

    # 追加到 README.md
    readme_path = project_root / "README.md"
    header = "\n## 项目结构\n\n```\n"
    footer = "\n```\n"

    if not readme_path.exists():
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("# 项目说明\n")
        print("README.md 不存在，已创建空文件")

    with open(readme_path, 'a', encoding='utf-8') as f:
        f.write(header)
        f.write(structure_text)
        f.write(footer)

    print(f"✅ 项目结构已追加到 {readme_path}")

if __name__ == "__main__":
    main()