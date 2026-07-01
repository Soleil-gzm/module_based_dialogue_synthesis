#!/usr/bin/env python3
"""
测试 _parse_repeat_value 函数的解析效果
"""

import sys
sys.path.insert(0, "scripts_general")

from core.config import _parse_repeat_value

# 测试用例
test_cases = [
    ("3", 3, "单个数字"),
    ("1/2", 2, "范围值（斜杠）"),
    ("1-3", 3, "范围值（短横线）"),
    (" 2 ", 2, "带空格的数字"),
    ("1 / 2", 2, "带空格的斜杠范围"),
    ("1 - 3", 3, "带空格的短横线范围"),
    (None, 1, "None 值"),
    ("", 1, "空字符串"),
    ("abc", 1, "无效字符串"),
    ("2/5", 5, "范围值 2/5"),
    ("1/2/3", 3, "多值分隔 1/2/3"),
    ("1/3/2/5", 5, "多值分隔 1/3/2/5"),
    ("1-2-3", 3, "多值分隔（短横线）1-2-3"),
    ("1/2/3/4/5", 5, "多值分隔 1/2/3/4/5"),
    (";1/2/3", 3, "带分号前缀 ;1/2/3"),
    (";1/2", 2, "带分号前缀 ;1/2"),
    ("1,2,3", 3, "逗号分隔 1,2,3"),
]

print("测试 _parse_repeat_value 函数：")
print("=" * 60)

all_passed = True
for value, expected, desc in test_cases:
    result = _parse_repeat_value(value)
    status = "✓" if result == expected else "✗"
    if result != expected:
        all_passed = False
    print(f"{status} {desc:25} | 输入: {str(value):15} | 期望: {expected} | 实际: {result}")

print("=" * 60)
if all_passed:
    print("所有测试通过！")
else:
    print("部分测试失败！")
