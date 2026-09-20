# run.py
import argparse

from config import CONFIG
# 导入各业务线模块
from generators import m0, m0_follow, s1, s1_follow, suning_backend

# 业务线模块映射
GENERATORS = {
    "suning_backend": suning_backend,
    "s1": s1,
    "s1_follow": s1_follow,
    "m0": m0,
    "m0_follow": m0_follow,
}

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
        
        cfg = CONFIG[case_name]
        if not cfg.get("enabled", True):
            print(f"⏸️ {cfg['name']} 已在配置中禁用，跳过。")
            continue

        print(f"🚀 开始生成 {cfg['name']} ...")
        module = GENERATORS[case_name]
        
        # 调用各个模块的 generate 函数
        module.generate(cfg)
        print("-" * 50)

    print("🎉 所有任务执行完毕！")

if __name__ == "__main__":
    main()