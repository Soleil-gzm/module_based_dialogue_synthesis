"""
阶段 0 · 步骤 2-3：生成条件评估黄金样本。

做法：
  1. 扫描 case 目录，按 (逾期符号, 总欠款/本金/利息/罚息/逾期笔数 是否>0) 生成签名，
     每个签名保留一个代表 case。
  2. 若真实 case 缺少某些关键组合（如逾期天数<0），构造合成 case 补齐。
  3. 对 inventory 中每个条件字符串 × 每个代表 case，跑当前 OverdueConditionEvaluator
     .evaluate_with_metadata，把 (condition_str, case_values, result) 存成黄金样本。

用法：
    cd scripts_general
    python -m testing.golden.generate_golden_samples \
        --inventory testing/golden/condition_inventory.json \
        --cases-dir "datas/suning/notdue_new/cases0_replace" \
        --output testing/golden/golden_samples.json \
        --report testing/golden/coverage_report.txt
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.data_loader import parse_case_info
from core.random_service import RandomService
from core.condition import OverdueConditionEvaluator

# 条件评估依赖的数值字段
NUMERIC_FIELDS = [
    ("总欠款_数值", "总欠款"),
    ("本金_数值", "本金"),
    ("利息_数值", "利息"),
    ("罚息_数值", "罚息"),
    ("逾期笔数_数值", "逾期笔数"),
]


def field_bin(val) -> int:
    """数值字段二元化：>0 → 1，否则 → 0"""
    try:
        return 1 if float(val) > 0 else 0
    except (ValueError, TypeError):
        return 0


def overdue_sign(val) -> int:
    """逾期天数符号：<0 → -1，=0 → 0，>0 → 1"""
    try:
        v = int(val)
    except (ValueError, TypeError):
        return 0
    return -1 if v < 0 else (0 if v == 0 else 1)


def case_signature(case: Dict[str, Any]) -> Tuple[int, int, int, int, int, int]:
    """返回 (overdue_sign, 总欠款, 本金, 利息, 罚息, 逾期笔数) 的二元签名"""
    sig = [overdue_sign(case.get("逾期天数", 0))]
    for key, _ in NUMERIC_FIELDS:
        sig.append(field_bin(case.get(key, 0)))
    return tuple(sig)


def signature_label(sig: Tuple) -> str:
    labels = ["逾期<0", "逾期=0", "逾期>0"]
    parts = [labels[sig[0] + 1]]
    names = ["总欠款", "本金", "利息", "罚息", "逾期笔数"]
    for name, b in zip(names, sig[1:]):
        parts.append(f"{name}{'非空' if b else '空'}")
    return " | ".join(parts)


def collect_representative_cases(cases_dir: str, max_scan: int = 0) -> List[Dict[str, Any]]:
    """
    扫描 case 目录，按签名去重，每个签名保留第一个遇到的 case。
    max_scan=0 表示全扫。
    """
    rng = RandomService(seed=0)  # 固定种子，保证随机字段可复现
    files = sorted([f for f in os.listdir(cases_dir) if f.endswith(".txt")])
    if max_scan:
        files = files[:max_scan]

    by_sig: Dict[Tuple, Dict[str, Any]] = {}
    for i, fname in enumerate(files):
        path = os.path.join(cases_dir, fname)
        case = parse_case_info(path, rng=rng)
        case["_filename"] = os.path.splitext(fname)[0]
        sig = case_signature(case)
        if sig not in by_sig:
            case["_signature"] = sig
            by_sig[sig] = case
        if (i + 1) % 2000 == 0:
            print(f"  已扫描 {i + 1}/{len(files)}，累计签名数 {len(by_sig)}")

    return list(by_sig.values())


def synth_missing_signatures(existing: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    系统性补齐签名空间，确保每个条件的 True/False 分支都被触发。

    真实 case 里利息/罚息恒为空，导致"利息不为空""罚息不为空"相关条件的
    True 分支从未被触发。这里枚举逾期符号 ∈ {-3, 0, 5} × 五字段所有 2^5 组合，
    去掉已存在的签名后补入，保证分支全覆盖。
    """
    import itertools

    existing_sigs = {c["_signature"] for c in existing}
    synth = []

    base_template = {
        "客服电话": "4000000000",
        "机构名称": "测试机构",
        "业务类型": "测试",
        "APP名称": "测试APP",
        "抬头": "测试",
        "专员工号": "0001",
        "客户姓名": "测试",
        "客户性别": "男",
        "客户姓氏": "测",
        "今天日期": "2026-09-01",
        "查账时间": "2026-09-01 10:00",
        "当前时间": "2026-09-01 10:00",
        "还款日": "2026-09-10",
        "应还金额": "0",
        "应还金额_数值": 0.0,
        "随机金额": "0",
        "随机数字": "1",
        "随机还款日": "1号",
        "随机时间": "今天上午10点",
        "违约金": "0",
        "违约金_数值": 0.0,
    }

    # 逾期符号：-3(<0) / 0(=0) / 5(>0)
    # 字段非空时的取值（>0 即可）
    nonzero = {"总欠款": 1000.0, "本金": 800.0, "利息": 100.0, "罚息": 50.0, "逾期笔数": 2}

    for od in (-3, 0, 5):
        # 枚举五字段的 2^5 种空/非空组合
        for combo in itertools.product([0, 1], repeat=5):
            case = dict(base_template)
            case["逾期天数"] = str(od)
            case["逾期天数_显示"] = str(abs(od))
            fields = ["总欠款", "本金", "利息", "罚息", "逾期笔数"]
            for fname, bit in zip(fields, combo):
                val = nonzero[fname] if bit else 0
                case[fname] = str(val)
                if fname == "逾期笔数":
                    case[f"{fname}_数值"] = int(val)
                else:
                    case[f"{fname}_数值"] = float(val)
            case["总本金"] = case["本金"]
            case["总本金_数值"] = case["本金_数值"]
            sig = case_signature(case)
            if sig in existing_sigs:
                continue
            case["_filename"] = f"<synthetic:od={od},{combo}>"
            case["_signature"] = sig
            synth.append(case)
            existing_sigs.add(sig)

    return synth


def minimal_case_for_eval(case: Dict[str, Any]) -> Dict[str, Any]:
    """黄金样本只记录与条件评估相关的字段，避免文件膨胀"""
    keep = {
        "逾期天数": case.get("逾期天数", "0"),
        "总欠款_数值": case.get("总欠款_数值", 0),
        "本金_数值": case.get("本金_数值", 0),
        "利息_数值": case.get("利息_数值", 0),
        "罚息_数值": case.get("罚息_数值", 0),
        "逾期笔数_数值": case.get("逾期笔数_数值", 0),
    }
    return keep


def main():
    parser = argparse.ArgumentParser(description="生成条件评估黄金样本")
    parser.add_argument("--inventory", required=True, help="scan_conditions 输出的 JSON")
    parser.add_argument("--cases-dir", required=True, help="case 数据目录（replace_dir）")
    parser.add_argument("--output", required=True, help="黄金样本输出 JSON")
    parser.add_argument("--report", default=None, help="覆盖报告输出 txt")
    parser.add_argument("--max-scan", type=int, default=0, help="最多扫描的 case 数（0=全扫）")
    args = parser.parse_args()

    with open(args.inventory, "r", encoding="utf-8") as f:
        inventory = json.load(f)
    conditions = sorted(inventory["inventory"].keys())
    print(f"加载 {len(conditions)} 个条件字符串")

    print(f"扫描 case 目录: {args.cases_dir}")
    real_cases = collect_representative_cases(args.cases_dir, max_scan=args.max_scan)
    print(f"真实 case 得到 {len(real_cases)} 个签名代表")

    synth = synth_missing_signatures(real_cases)
    print(f"补充 {len(synth)} 个合成 case 覆盖缺失签名")

    all_cases = real_cases + synth
    print(f"代表 case 总数: {len(all_cases)}")

    # 跑黄金样本
    evaluator = OverdueConditionEvaluator()
    samples: List[Dict[str, Any]] = []
    true_count = 0
    false_count = 0
    for cond in conditions:
        for case in all_cases:
            result = evaluator.evaluate_with_metadata(cond, case)
            matched = bool(result["matched"])
            if matched:
                true_count += 1
            else:
                false_count += 1
            samples.append({
                "condition": cond,
                "case_signature": list(case["_signature"]),
                "case_signature_label": signature_label(case["_signature"]),
                "case_source": case["_filename"],
                "case_values": minimal_case_for_eval(case),
                "result": result,
            })

    payload = {
        "generated_by": "generate_golden_samples.py",
        "evaluator": "OverdueConditionEvaluator",
        "conditions_count": len(conditions),
        "cases_count": len(all_cases),
        "samples_count": len(samples),
        "matched_true": true_count,
        "matched_false": false_count,
        "samples": samples,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n黄金样本已写入: {args.output}")
    print(f"  样本数: {len(samples)} = {len(conditions)} 条件 × {len(all_cases)} case")
    print(f"  matched=True: {true_count}  matched=False: {false_count}")

    # 覆盖报告
    if args.report:
        lines = []
        lines.append("===== 黄金样本签名覆盖报告 =====\n")
        lines.append(f"条件字符串数: {len(conditions)}")
        lines.append(f"代表 case 数: {len(all_cases)}（真实 {len(real_cases)} + 合成 {len(synth)}）\n")
        lines.append("----- 代表 case 签名清单 -----")
        for c in all_cases:
            tag = "合成" if str(c["_filename"]).startswith("<synthetic") else "真实"
            lines.append(f"  [{tag}] {signature_label(c['_signature'])}  <- {c['_filename']}")
        lines.append("")
        lines.append("----- 每个条件的 matched=True/False 分布 -----")
        from collections import defaultdict
        cond_stats = defaultdict(lambda: {"t": 0, "f": 0})
        for s in samples:
            k = cond_stats[s["condition"]]
            if s["result"]["matched"]:
                k["t"] += 1
            else:
                k["f"] += 1
        for cond in conditions:
            st = cond_stats[cond]
            lines.append(f"  [{st['t']:>3}T / {st['f']:>3}F]  {cond}")
        os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"覆盖报告已写入: {args.report}")


if __name__ == "__main__":
    main()
