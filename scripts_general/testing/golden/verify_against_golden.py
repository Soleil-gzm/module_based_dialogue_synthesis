"""
阶段 0 · 步骤 4：黄金样本回归验证脚本。

重构条件解析器后，用此脚本比对"新解析器输出"与"黄金样本"是否一致。
当前先用 ConditionParser 跑一遍做自洽性检查（应 100% 通过）。

用法：
    cd scripts_general
    python -m testing.golden.verify_against_golden \
        --golden testing/golden/golden_samples.json \
        [--evaluator overdue|keyword]   # 默认 overdue，重构后可换新解析器

退出码：0=全部一致，1=存在差异。
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.condition import ConditionParser


def reconstruct_case(case_values: Dict[str, Any]) -> Dict[str, Any]:
    """从黄金样本里存的极简字段还原成评估器所需 case（补齐缺省键）"""
    case = {
        "逾期天数": str(case_values.get("逾期天数", "0")),
        "总欠款_数值": case_values.get("总欠款_数值", 0),
        "本金_数值": case_values.get("本金_数值", 0),
        "利息_数值": case_values.get("利息_数值", 0),
        "罚息_数值": case_values.get("罚息_数值", 0),
        "逾期笔数_数值": case_values.get("逾期笔数_数值", 0),
    }
    return case


def verify(golden_path: str) -> Tuple[int, int, List[Dict]]:
    with open(golden_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    evaluator = ConditionParser()
    samples: List[Dict] = payload["samples"]
    passed = 0
    failed = 0
    diffs: List[Dict] = []

    for i, s in enumerate(samples):
        cond = s["condition"]
        case = reconstruct_case(s["case_values"])
        expected = s["result"]
        actual = evaluator.evaluate_with_metadata(cond, case)

        # 核心比对：matched 必须一致
        if bool(actual["matched"]) != bool(expected["matched"]):
            failed += 1
            diffs.append({
                "index": i,
                "condition": cond,
                "case_values": s["case_values"],
                "expected_matched": expected["matched"],
                "actual_matched": actual["matched"],
                "expected_parsed": expected.get("parsed_condition"),
                "actual_parsed": actual.get("parsed_condition"),
            })
        else:
            passed += 1

    return passed, failed, diffs


def main():
    parser = argparse.ArgumentParser(description="黄金样本回归验证")
    parser.add_argument("--golden", required=True, help="golden_samples.json 路径")
    args = parser.parse_args()

    print(f"加载黄金样本: {args.golden}")
    print(f"使用评估器: ConditionParser")

    passed, failed, diffs = verify(args.golden)
    total = passed + failed

    print(f"\n===== 验证结果 =====")
    print(f"总样本: {total}")
    print(f"通过:   {passed}")
    print(f"失败:   {failed}")

    if diffs:
        print(f"\n----- 前 20 条差异 -----")
        for d in diffs[:20]:
            print(
                f"  [{d['index']}] cond={d['condition']} | "
                f"case={d['case_values']} | "
                f"期望 matched={d['expected_matched']}({d['expected_parsed']}) "
                f"实际 matched={d['actual_matched']}({d['actual_parsed']})"
            )
        if len(diffs) > 20:
            print(f"  ... 还有 {len(diffs) - 20} 条差异未显示")

    if failed:
        diff_path = args.golden.replace(".json", ".diff.json")
        with open(diff_path, "w", encoding="utf-8") as f:
            json.dump(diffs, f, ensure_ascii=False, indent=2)
        print(f"\n差异详情已写入: {diff_path}")
        sys.exit(1)
    else:
        print("\n全部一致 ✅")
        sys.exit(0)


if __name__ == "__main__":
    main()
