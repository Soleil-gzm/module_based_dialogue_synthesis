"""
单元测试：PressureManager 模块（施压话术继承链、条件筛选等）
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from core.config import Config
from core.pressure_manager import PressureManager
from core.random_service import RandomService


# ========== 辅助：生成模拟施压话术 DataFrame ==========
def create_pressure_df():
    data = {
        "uid": [1, 2, 3, 4, 5, 6],
        "parent(继承)": [0, 1, 1, 2, 2, 0],
        "repeat(次数)": ["1", "1/2", "2", "1", "3", "1"],
        "conditions(条件)": ["", "逾期", "", "", "逾期", ""],
        "human(客户)": [
            "客户话术1",
            "客户话术2/客户话术2b",
            "客户话术3",
            "",
            "客户话术5",
            "客户话术6",
        ],
        "assistant(专员)": [
            "专员话术1",
            "专员话术2",
            "专员话术3",
            "专员话术4",
            "专员话术5",
            "专员话术6",
        ],
        "flexible_stop(可选不继承)": [0, 0, 1, 0, 0, 0],
        "是否再见": [0, 0, 0, 0, 0, 0],
    }
    df = pd.DataFrame(data)
    return df


def create_minimal_df():
    """创建一个只有必需列的空 DataFrame（用于测试空数据但列存在）"""
    data = {
        "uid": [],
        "parent(继承)": [],
        "repeat(次数)": [],
        "conditions(条件)": [],
        "human(客户)": [],
        "assistant(专员)": [],
        "flexible_stop(可选不继承)": [],
        "是否再见": [],
    }
    return pd.DataFrame(data)


# ========== 测试类 ==========
class TestPressureManager:
    @pytest.fixture
    def pressure_df(self):
        return create_pressure_df()

    @pytest.fixture
    def minimal_df(self):
        return create_minimal_df()

    @pytest.fixture
    def config(self):
        return Config({"flexible_stop_prob": 0.3})

    @pytest.fixture
    def rng(self):
        return RandomService(seed=42)

    @pytest.fixture
    def condition_evaluator_mock(self):
        """模拟条件解析器：仅当条件字符串包含"逾期"时返回True"""
        mock = MagicMock()
        mock.evaluate.side_effect = lambda cond_str, case: "逾期" in cond_str
        return mock

    # ---------- 基本功能测试 ----------
    def test_init_max_repeat(self, pressure_df, config, rng):
        pm = PressureManager(pressure_df, rng, config)
        assert pm.max_repeat == 3

    def test_get_pressure_segment_no_data(self, minimal_df, config, rng):
        """使用最小 DataFrame（有列但无数据），初始化成功，获取片段返回空"""
        pm = PressureManager(minimal_df, rng, config)
        seg, has_first = pm.get_pressure_segment(1, {}, MagicMock())
        assert seg == []
        assert has_first is False

    def test_get_pressure_segment_repeat_exceeds_max(self, pressure_df, config, rng):
        pm = PressureManager(pressure_df, rng, config)
        seg, has_first = pm.get_pressure_segment(10, {}, MagicMock())
        assert seg == []
        assert has_first is False

    def test_get_pressure_segment_no_candidates_repeat(self, pressure_df, config, rng):
        pm = PressureManager(pressure_df, rng, config)
        seg, has_first = pm.get_pressure_segment(99, {}, MagicMock())
        assert seg == []
        assert has_first is False

    def test_get_pressure_segment_condition_mismatch(
        self, pressure_df, config, rng, condition_evaluator_mock
    ):
        pm = PressureManager(pressure_df, rng, config)
        case = {"逾期天数": 0}  # 不满足条件
        seg, has_first = pm.get_pressure_segment(1, case, condition_evaluator_mock)
        # 应该能选到无条件行，片段非空
        assert len(seg) > 0

    # ---------- 继承链测试（模拟内部函数，避免真实调用） ----------
    @patch("core.pressure_manager.get_ancestors")
    @patch("core.pressure_manager.get_random_descendant_chain")
    @patch("core.pressure_manager.sample_utterance")
    def test_segment_contains_ancestors_current_descendants(
        self,
        mock_sample,
        mock_get_desc,
        mock_get_anc,
        pressure_df,
        config,
        rng,
        condition_evaluator_mock,
    ):
        """验证片段构建顺序：祖先 -> 当前 -> 后代，且正确调用 sample_utterance"""
        # 模拟祖先、后代、当前行（使用 MagicMock 模拟 pd.Series）
        mock_anc1 = MagicMock()
        mock_anc2 = MagicMock()
        mock_current = MagicMock()
        mock_desc1 = MagicMock()
        mock_desc2 = MagicMock()

        mock_get_anc.return_value = [mock_anc1, mock_anc2]
        mock_get_desc.return_value = [mock_desc1, mock_desc2]

        # sample_utterance 返回字符串
        mock_sample.side_effect = lambda row, is_human, rng: (
            f"{row}_human" if is_human else f"{row}_assistant"
        )

        pm = PressureManager(pressure_df, rng, config)

        # 我们需要让 get_pressure_segment 中的筛选通过，并且让 rng.choice 返回 mock_current
        # 方法：模拟条件评估总是 True，并模拟 rng.choice
        with patch.object(condition_evaluator_mock, "evaluate", return_value=True):
            # 直接修改 rng.choice 的行为
            original_choice = rng.choice
            rng.choice = MagicMock(return_value=mock_current)

            # 调用 get_pressure_segment，但注意传入的 case 任意
            seg, has_first = pm.get_pressure_segment(1, {}, condition_evaluator_mock)
            # 由于我们 mock 了 get_ancestors 等，会按照 mock 构建片段
            # 祖先2个 + 当前1个 + 后代2个 = 5轮
            assert len(seg) == 5
            # 每轮有 user 和 assistant 两个字段
            # 验证 sample_utterance 被调用正确次数：祖先2个*2 + 当前2 + 后代2个*2 = 10
            assert mock_sample.call_count == 10
            # 第一轮应有客户话术（祖先 mock 返回非空）
            assert has_first is True

            rng.choice = original_choice

    def test_has_customer_first_false(self, config, rng, condition_evaluator_mock):
        """测试第一轮无客户话术的情况（祖先或当前行的 human 为空）"""
        data = {
            "uid": [100],
            "parent(继承)": [0],
            "repeat(次数)": ["1"],
            "conditions(条件)": [""],
            "human(客户)": [""],
            "assistant(专员)": ["assistant only"],
            "flexible_stop(可选不继承)": [0],
            "是否再见": [0],
        }
        df = pd.DataFrame(data)
        pm = PressureManager(df, rng, config)

        # 让条件始终通过
        condition_evaluator_mock.evaluate.return_value = True

        with patch("core.pressure_manager.get_ancestors", return_value=[]):
            with patch(
                "core.pressure_manager.get_random_descendant_chain", return_value=[]
            ):
                with patch.object(rng, "choice", return_value=df.iloc[0]):
                    seg, has_first = pm.get_pressure_segment(
                        1, {}, condition_evaluator_mock
                    )
                    assert len(seg) == 1
                    assert seg[0]["user"] == ""
                    assert seg[0]["assistant"] == "assistant only"
                    assert has_first is False

    # ---------- 集成测试（真实调用继承函数，但使用可控数据） ----------
    def test_ancestors_and_descendants_integration(
        self, pressure_df, config, rng, condition_evaluator_mock
    ):
        """真实调用 get_ancestors 和 get_random_descendant_chain，验证继承逻辑"""
        # 选择 uid=2 的行 (parent=1)，期望祖先为 uid=1
        row = pressure_df[pressure_df["uid"] == 2].iloc[0]

        pm = PressureManager(pressure_df, rng, config)

        # 强制条件通过，并且强制 rng.choice 返回该行
        with patch.object(condition_evaluator_mock, "evaluate", return_value=True):
            # mock sample_utterance 避免真实的 Series 布尔歧义
            with patch("core.pressure_manager.sample_utterance", return_value="mocked"):
                original_choice = rng.choice
                rng.choice = MagicMock(return_value=row)

                seg, has_first = pm.get_pressure_segment(
                    1, {}, condition_evaluator_mock
                )

                rng.choice = original_choice

                # 至少应有祖先（uid=1）+ 当前（uid=2）+ 可能后代
                assert len(seg) >= 2
                # 验证片段中有 mock 的话术
                assert any(s["assistant"] == "mocked" for s in seg)

    def test_condition_filtering(
        self, pressure_df, config, rng, condition_evaluator_mock
    ):
        pm = PressureManager(pressure_df, rng, config)
        case = {"逾期天数": 30}  # 满足条件
        with patch.object(rng, "choice") as mock_choice:
            # 让 rng.choice 返回列表第一个元素，便于检查
            mock_choice.side_effect = lambda seq: seq[0]
            seg, has_first = pm.get_pressure_segment(1, case, condition_evaluator_mock)
            # 应该选中 uid=2 的行（条件"逾期"），其 assistant 为"专员话术2"
            # 检查片段中是否包含"专员话术2"
            assert any("专员话术2" in s["assistant"] for s in seg)

    def test_empty_segment_when_no_valid_rows(
        self, pressure_df, config, rng, condition_evaluator_mock
    ):
        pm = PressureManager(pressure_df, rng, config)
        seg, has_first = pm.get_pressure_segment(99, {}, condition_evaluator_mock)
        assert seg == []
        assert has_first is False
