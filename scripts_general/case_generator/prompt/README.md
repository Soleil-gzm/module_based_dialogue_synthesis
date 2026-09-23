## 苏宁案例模拟

`conda activate rag`

新的模板，新的话术

#### 说明

- 生成苏宁模拟案例，用于构造simulation data以及backbone data

`generate-random-cases-S1.py`
    用于生成backbone数据
    cases1_system
    cases1_backbone

`generate-random-cases-S1-follow.py`
    用于生成backbone数据
    cases3_system
    cases3_backbone

`generate-random-cases-M0.py`
    用于生成backbone数据
    cases0_system
    cases0_backbone

# M0,逾期天数=0

# S1/M1 + M1_follow: 逾期天数一个月，就是1-30天

# M2/M2_folow: 逾期天数 29～62

# 后端，就是M3+，逾期超过3个月，逾期天数大于90天  逾期天数 30% 概率361～1500，否则 90~360

M0：未逾期；
S1：逾期-首催；
S1-follow：逾期-跟催

# 验证集

M0：1-100, M0-follow：101-200, S1： 201-300, S1-follow：301-400

M0: 4w
M0-follow: 1w
S1: 6w
S1-follow: 2w

# 2026.9.23 更新业务数据

逾期天数：
M0： 0
M1：1-31
M2/M3： 29-91
M3+：40% 90-180  30% 181-360 30% 361-1500

应换金额！= 0, M3+ 应换金额=总欠款（防御性不为0）

首催4w,跟催 2w

mapping:

推荐英文缩写方案
采用 意愿（Willingness）+ 能力（Ability） 的组合，用 Y/N 表示有/无，简洁易记：

中文标签        推荐缩写         含义
有意愿有能力     WY_AY         Willing Yes, Ability Yes
有意愿无能力     WY_AN         Willing Yes, Ability No
无意愿有能力     WN_AY         Willing No, Ability Yes
无意愿无能力     WN_AN         Willing No, Ability No
有投诉风险         CR             Complaint Risk
易跳票客户         BP              Break Promise
