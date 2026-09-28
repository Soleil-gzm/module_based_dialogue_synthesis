"""
prob 表自动生成模块

封装 scripts_general/excel2prob/excel2prob/ 下的 candidates_builder 与 prob_builder，
供 main.py 在加载 prob 表前按 yaml 开关自动调用。

公开接口：
    generate_prob_from_excel(excel_path, categories_yaml_path, ...) -> str
    返回生成的 prob Excel 文件绝对路径，供 load_prob_matrix() 使用。

输出路径规则：
    1. 显式传入 output_path 时使用该路径
    2. 否则默认放在 excel_path 同级目录，文件名为 {stem}_auto_prob.xlsx
       （覆盖同名旧文件，避免目录堆积多个时间戳版本）
"""

import importlib.util
import logging
import os
from typing import Optional

logger = logging.getLogger("DialogueBuilder")

# excel2prob 子模块目录（固定相对位置：scripts_general/excel2prob/excel2prob/）
_EXCEL2PROB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "excel2prob", "excel2prob")
)


def _load_excel2prob_module(module_name: str, file_name: str):
    """用 importlib 显式加载 excel2prob 子目录下的模块，避免污染 sys.path。"""
    file_path = os.path.join(_EXCEL2PROB_DIR, file_name)
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"excel2prob 子模块文件不存在: {file_path}。"
            f"请确认 scripts_general/excel2prob/excel2prob/ 目录完整。"
        )
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _get_default_output_path(excel_path: str) -> str:
    """默认输出路径：excel_path 同级目录下 {stem}_auto_prob.xlsx。"""
    excel_dir = os.path.dirname(os.path.abspath(excel_path))
    stem = os.path.splitext(os.path.basename(excel_path))[0]
    return os.path.join(excel_dir, f"{stem}_auto_prob.xlsx")


def generate_prob_from_excel(
    excel_path: str,
    categories_yaml_path: str,
    output_path: Optional[str] = None,
    compress_mode: str = "log",
    save_candidates: bool = False,
    candidates_output_path: Optional[str] = None,
) -> str:
    """
    根据话术 Excel + 类别 YAML 自动生成 prob 表。

    Args:
        excel_path: 话术模板 Excel 路径
        categories_yaml_path: 类别定义 YAML（A/B/C/manual/fixed_prob/boost 等）
        output_path: 生成的 prob Excel 输出路径，None 则默认放 excel_path 同级
        compress_mode: 压缩方式，none / sqrt / log
        save_candidates: 是否保存中间 candidates JSON
        candidates_output_path: candidates JSON 输出路径，None 则与 prob 同目录

    Returns:
        生成的 prob Excel 文件绝对路径
    """
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"话术 Excel 文件不存在: {excel_path}")
    if not os.path.exists(categories_yaml_path):
        raise FileNotFoundError(f"类别 YAML 文件不存在: {categories_yaml_path}")

    if output_path is None:
        output_path = _get_default_output_path(excel_path)
    output_path = os.path.abspath(output_path)

    logger.info("=" * 60)
    logger.info("自动生成 prob 表")
    logger.info(f"  话术 Excel: {excel_path}")
    logger.info(f"  类别 YAML:  {categories_yaml_path}")
    logger.info(f"  压缩方式:   {compress_mode}")
    logger.info(f"  输出路径:   {output_path}")
    logger.info("=" * 60)

    # 显式加载 excel2prob 子模块，避免污染 sys.path
    candidates_builder = _load_excel2prob_module(
        "excel2prob_candidates_builder", "candidates_builder.py"
    )
    prob_builder = _load_excel2prob_module(
        "excel2prob_prob_builder", "prob_builder.py"
    )

    # 1. 生成候选 payload
    payload = candidates_builder.build_candidates(excel_path, categories_yaml_path)
    if payload.get("unused_modules"):
        logger.warning(
            f"话术 Excel 中存在未被类别 YAML 使用的模块: "
            f"{', '.join(payload['unused_modules'])}"
        )

    # 可选：保存中间 candidates JSON
    if save_candidates:
        if candidates_output_path is None:
            candidates_output_path = os.path.join(
                os.path.dirname(output_path),
                f"{os.path.splitext(os.path.basename(excel_path))[0]}_candidates.json",
            )
        candidates_builder.save_candidates(payload, candidates_output_path)
        logger.info(f"  candidates 已保存: {candidates_output_path}")

    # 2. 生成 prob 矩阵
    matrix = prob_builder.build_prob_matrix(payload, categories_yaml_path, compress_mode)

    # 3. 保存 prob Excel
    prob_builder.save_prob_matrix(matrix, output_path)
    logger.info(f"  prob 表已生成: {output_path}")

    # 4. 校验
    issues = prob_builder.validate_matrix(matrix)
    if issues:
        logger.warning("  prob 表校验提示:")
        for issue in issues:
            logger.warning(f"    ⚠️ {issue}")
    else:
        logger.info("  prob 表校验: OK")

    return output_path
