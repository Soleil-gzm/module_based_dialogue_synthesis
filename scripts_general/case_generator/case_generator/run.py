# run.py
import argparse

# from config import CONFIG
# from config_test import CONFIG
from config_agent import CONFIG
# 导入各业务线模块
from generators import m0, m0_follow, m1, m1_follow, suning_backend,m2,m2_follow,m3_plus,m3_plus_follow

# 业务线模块映射
GENERATORS = {
    "suning_backend": suning_backend,
    "m0": m0,
    "m0_follow": m0_follow,
    "m1": m1,
    "m1_follow": m1_follow,
    "m2": m2,
    "m2_follow": m2_follow,
    "m3_plus": m3_plus,
    "m3_plus_follow": m3_plus_follow,
}

def _normalize_configs(cfg_value):
    """统一 CONFIG[case_name] 的格式：dict → [dict]，list → list。
    这样配置里既可写单套 dict（兼容旧 config），也可写多套 list。"""
    if isinstance(cfg_value, dict):
        return [cfg_value]
    return list(cfg_value)


def main():
    parser = argparse.ArgumentParser(description="统一生成测试数据入口")
    parser.add_argument(
        "--cases", nargs="+", 
        default=list(GENERATORS.keys()),
        help="指定要生成的业务线，默认生成全部"
    )
    args = parser.parse_args()

    for case_name in args.cases:
        if case_name not in CONFIG:
            print(f"⚠️ 未找到配置：{case_name}")
            continue

        configs = _normalize_configs(CONFIG[case_name])
        for idx, cfg in enumerate(configs, 1):
            if not cfg.get("enabled", True):
                print(f"⏸️ {cfg.get('name', case_name)} 已在配置中禁用，跳过。")
                continue

            label = cfg.get('name', case_name)
            if len(configs) > 1:
                label = f"{label} ({idx}/{len(configs)})"
            print(f"🚀 开始生成 {label} ...")
            module = GENERATORS[case_name]

            # 调用各个模块的 generate 函数
            module.generate(cfg)
            print("-" * 50)

    print("🎉 所有任务执行完毕！")

if __name__ == "__main__":
    main()