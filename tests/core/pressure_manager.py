import pandas as pd
from typing import List
from core.random_service import RandomService

class PressureManager:
    """管理衔接施压话术，支持循环复用"""
    def __init__(self, pressure_df: pd.DataFrame, rng: RandomService):
        self.rng = rng
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
            row = sub.sample(n=1, random_state=self.rng.randint(0, 2**32-1)).iloc[0]
            assistant_opt = row['assistant(专员)']
            if pd.notna(assistant_opt):
                opts = [s.strip() for s in assistant_opt.split('/') if s.strip()]
                pressure_list.append(self.rng.choice(opts) if opts else '')
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