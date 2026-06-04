import pandas as pd

prob_df = pd.read_excel("datas/prob.xlsx", header=None)
print("原始形状:", prob_df.shape)
print("列数:", prob_df.shape[1])
print("前两行:\n", prob_df.iloc[:2, :5])
