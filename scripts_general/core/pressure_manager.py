'''
Step 8：实现施压话术管理器
操作：创建 core/pressure_manager.py，类 PressureManager：

从 df_dict['衔接施压话术'] 加载三段话术

提供 get_pressure_text(repeat_index) 方法，支持循环复用。
原因：施压逻辑独立，避免索引越界，且可灵活调整概率和话术来源。
'''

import random
import pandas as pd
from typing import List

class PressureManager:
    """管理衔接施压话术，支持循环复用"""
    def __init__(self, pressure_df: pd.DataFrame):
        self.pressure_list = self._load_pressure(pressure_df)
        self.index = 0

    def _load_pressure(self, df: pd.DataFrame) -> List[str]:
        """从DataFrame中加载三段施压话术（对应repeat 1,2,3）"""
        pressure_list = []
        for repeat in [1, 2, 3]:
            if df.empty:
                pressure_list.append('')
                continue
            mask = df['repeat(次数)'].apply(
                lambda x: str(repeat) in str(x).split('/') if pd.notna(x) else False)
            sub = df[mask]
            if sub.empty:
                pressure_list.append('')
                continue
            row = sub.sample(n=1).iloc[0]
            assistant_opt = row['assistant(专员)']
            if pd.notna(assistant_opt):
                opts = [s.strip() for s in assistant_opt.split('/') if s.strip()]
                pressure_list.append(random.choice(opts) if opts else '')
            else:
                pressure_list.append('')
        return pressure_list

    def get_next_pressure(self) -> str:
        """获取下一个施压话术（循环使用）"""
        if not self.pressure_list:
            return ''
        pressure = self.pressure_list[self.index % len(self.pressure_list)]
        self.index += 1
        return pressure

    def reset(self):
        self.index = 0