"""
批量处理话术 Excel，生成对应的 prob 表

用法（在项目根目录执行）：
    python excel2prob/run.py
    或
    python -m excel2prob.run

输出：
    intermediate/candidates/{excel名}_candidates_{时间戳}.json  （可选）
    intermediate/prob/{excel名}_prob_{压缩方法}_{时间戳}.xlsx
"""

import os
import sys
import traceback
from datetime import datetime
from glob import glob

# ============================================================
# 把 run.py 所在目录加入 sys.path，保证同目录的模块能被导入
# ============================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from candidates_builder import build_candidates, save_candidates
from prob_builder import build_prob_matrix, save_prob_matrix, validate_matrix


# ============================================================
# 硬编码配置（改这里即可）
# ============================================================
EXCEL_DIR = "datas/suning-notdueS1-0918"                       # 输入：话术 Excel 文件夹
YAML_PATH = "datas/suning-notdueS1-0918/categories_S1-0918.yaml"                 # 输入：类别定义 YAML
CANDIDATES_DIR = "datas/suning-notdueS1-0918/prob_generator/candidates"                      # 中间产物目录
PROB_DIR = "datas/suning-notdueS1-0918/prob_generator/prob"                                  # 最终产物目录
COMPRESS_MODE = "log"                                           # "none" / "sqrt" / "log"
SAVE_CANDIDATES = True                                          # 是否保存中间 JSON


def main():
    excel_files = sorted(glob(os.path.join(EXCEL_DIR, "*.xlsx")))
    # 排除 Excel 打开时的临时文件 ~$xxx.xlsx
    excel_files = [f for f in excel_files if not os.path.basename(f).startswith("~$")]

    if not excel_files:
        print(f"未找到 Excel 文件: {EXCEL_DIR}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"共发现 {len(excel_files)} 个 Excel 文件")
    print(f"压缩方式: {COMPRESS_MODE}")
    print(f"时间戳: {timestamp}\n")

    success = 0
    failed = []

    for idx, excel_path in enumerate(excel_files, 1):
        stem = os.path.splitext(os.path.basename(excel_path))[0]
        print(f"[{idx}/{len(excel_files)}] {stem}")

        try:
            # 1. 生成候选
            payload = build_candidates(excel_path, YAML_PATH)

            if SAVE_CANDIDATES:
                candidates_path = os.path.join(
                    CANDIDATES_DIR, f"{stem}_candidates_{timestamp}.json"
                )
                save_candidates(payload, candidates_path)
                print(f"  candidates: {candidates_path}")

            # 未使用模块提示
            if payload["unused_modules"]:
                print(f"  未使用模块: {', '.join(payload['unused_modules'])}")

            # 2. 生成 prob
            matrix = build_prob_matrix(payload, YAML_PATH, COMPRESS_MODE)
            prob_filename = f"{stem}_prob_{COMPRESS_MODE}_{timestamp}.xlsx"
            prob_path = os.path.join(PROB_DIR, prob_filename)
            save_prob_matrix(matrix, prob_path)
            print(f"  prob: {prob_path}")

            # 3. 校验
            issues = validate_matrix(matrix)
            if issues:
                print(f"  校验提示:")
                for issue in issues:
                    print(f"    ⚠️ {issue}")
            else:
                print(f"  校验: OK")

            success += 1

        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            traceback.print_exc()
            failed.append((stem, str(e)))

        print()

    # 汇总
    print("=" * 60)
    print(f"完成: 成功 {success} / 共 {len(excel_files)}")
    if failed:
        print(f"\n失败列表:")
        for name, err in failed:
            print(f"  {name}: {err}")


if __name__ == "__main__":
    main()