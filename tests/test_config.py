import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts_general.core.config import load_config


config_path="configs/general.yaml"
config=load_config(config_path)

print(config.company)
print(config.get("max_repeat.身份确认"))
# print(config.unkonw)
print()

data_copy = config.to_dict()
print(data_copy)
data_copy['company'] = '新公司'
print()
print(data_copy)
print()
print(config.company)