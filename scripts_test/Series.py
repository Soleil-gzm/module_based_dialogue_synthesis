import numpy as np
import pandas as pd

df = pd.DataFrame({"A": [1, 2, 3], "B": [10, 20, 30], "C": [100, 200, 300]})

print("原始数据：")
print(df)
print()

# axis=1，按行应用
print("每行求和：")
print(df.apply(sum, axis=1))
print()

# 每行最大值-最小值
print("每行极差：")
print(df.apply(lambda x: x.max() - x.min(), axis=1))
