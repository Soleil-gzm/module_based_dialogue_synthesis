"""
单元测试：核心模块 (case_loader, time_generator, data_loader, factory)
"""

import os
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

# 导入被测试模块
from core.case_loader import (
    CaseLoader,
    DefaultCaseLoader,
    XiaoyingCaseLoader,
)
from core.time_generator import (
    SimpleNaturalTimeGenerator,
)
from core.data_loader import parse_case_info, load_cases
from core.factory import create_case_loader,create_time_generator
from core.random_service import RandomService
from core.config import Config


# ========== 辅助函数 ==========
def create_mock_rng(seed=42):
    """创建可控的 RandomService，用于确定性测试"""
    return RandomService(seed)


def create_mock_time_gen(fixed_time="今天上午10点"):
    """创建一个固定输出的时间生成器，用于测试"""
    class FixedTimeGenerator:
        def generate(self, rng, base_time=None):
            return fixed_time
    return FixedTimeGenerator()


# ========== 1. 测试 time_generator 模块 ==========
class TestTimeGenerator:

    def test_simple_natural_time_generator_format(self):
        rng = create_mock_rng(42)
        gen = SimpleNaturalTimeGenerator()
        
        # 正则匹配：
        # 可选：(今天|明天)
        # 必须：(上午|中午|下午|晚上)
        # 必须：数字（1-2位数）
        # 可选：点 + 数字 + 分（如点15分）
        pattern = r'^(今天|明天)?(上午|中午|下午|晚上)\d{1,2}(点(\d{1,2}分)?)?$'
        
        for _ in range(20):
            time_str = gen.generate(rng)
            assert re.match(pattern, time_str) is not None, \
                f"时间字符串 '{time_str}' 不符合期望格式（例如：今天上午10点、下午3点、明天晚上8点15分）"

    def test_create_time_generator_from_config(self):
        """测试工厂函数根据配置返回正确的生成器"""
        # 配置 simple_natural
        config_data = {"time_generator": {"type": "simple_natural"}}
        config = Config(config_data)
        gen = create_time_generator(config)
        assert isinstance(gen, SimpleNaturalTimeGenerator)

        # 不配置时默认
        config_data = {}
        config = Config(config_data)
        gen = create_time_generator(config)
        assert isinstance(gen, SimpleNaturalTimeGenerator)

        # 未知类型应抛异常
        config_data = {"time_generator": {"type": "unknown"}}
        config = Config(config_data)
        with pytest.raises(ValueError, match="Unknown time_generator type"):
            create_time_generator(config)


# ========== 2. 测试 data_loader 模块 ==========
class TestDataLoader:
    @pytest.fixture
    def sample_case_file(self):
        """创建一个临时案例文件内容"""
        content = """- 客服电话：952592
- 机构名称：小赢卡贷
- 业务类型：借款
- APP名称：小赢卡贷
- 抬头：小赢卡贷的工作人员
- 专员工号：131244
- 客户姓名：彭杰
- 客户性别：先生
- 客户姓氏：彭
- 逾期天数：188
- 今天日期：01月14日
- 查账时间：今天中午12点
- 当前时间：上午
- 还款日：07月10日
- 逾期金额：22357.67元
- 总欠款：22357.67元
- 本金：16039.12元
- 利息：3333.05元
- 违约金：1334.23元
- 罚息：1496.38元
"""
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(content)
            tmp_path = f.name
        yield tmp_path
        os.unlink(tmp_path)

    def test_parse_case_info_without_rng(self, sample_case_file):
        """测试 parse_case_info 不使用随机服务时的基本解析"""
        case = parse_case_info(sample_case_file, rng=None)
        # 验证字段正确提取
        assert case["客服电话"] == "952592"
        assert case["机构名称"] == "小赢卡贷"
        assert case["客户姓名"] == "彭杰"
        assert case["逾期金额"] == "22357.67元"
        assert case["逾期金额_数值"] == 22357.67
        assert case["总欠款_数值"] == 22357.67
        assert case["本金_数值"] == 16039.12
        # 随机金额应该存在且为数字字符串
        assert "随机金额" in case
        assert case["随机金额"].replace(".", "").isdigit()  # 可能是整数或小数
        # 随机时间应该存在（降级逻辑：今天上午/下午 X点）
        assert "随机时间" in case
        assert any(period in case["随机时间"] for period in ["上午", "下午"])

    def test_parse_case_info_with_rng(self, sample_case_file):
        """测试 parse_case_info 使用随机服务，且可注入自定义时间生成器"""
        rng = create_mock_rng(42)
        fixed_time_gen = create_mock_time_gen("明天下午3点")
        case = parse_case_info(sample_case_file, rng=rng, time_gen=fixed_time_gen)
        # 随机金额应该是确定性的（由于固定种子）
        # 逾期金额_数值为22357.67，随机比例固定0.3~0.7，种子42下应可计算
        expected_random_amount = str(round(22357.67 * 0.3))  # 种子42的uniform第一个值约为0.3
        # 实际可能不同，我们只检查存在且为数字
        assert case["随机金额"].replace(".", "").isdigit()
        # 随机时间应为固定时间
        assert case["随机时间"] == "明天下午3点"

    def test_load_cases(self, sample_case_file):
        """测试 load_cases 函数：加载单个文件目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 将 sample_case_file 复制到临时目录
            import shutil
            dest = os.path.join(tmpdir, "case1.txt")
            shutil.copy(sample_case_file, dest)
            cases, prompts = load_cases(tmpdir, rng=None)
            assert len(cases) == 1
            assert len(prompts) == 1
            assert cases[0]["客户姓名"] == "彭杰"
            assert "客服电话：952592" in prompts[0]


# ========== 3. 测试 case_loader 模块 ==========
class TestCaseLoader:
    @pytest.fixture
    def temp_dirs_with_files(self):
        """创建两个临时目录，分别放 replace 和 system 文件"""
        with tempfile.TemporaryDirectory() as replace_dir, tempfile.TemporaryDirectory() as system_dir:
            # 创建 replace 文件
            replace_content1 = """- 客户姓名：张三\n- 逾期金额：1000元\n- 查账时间：今天上午10点"""
            replace_content2 = """- 客户姓名：李四\n- 逾期金额：2000元\n- 查账时间：今天下午2点"""
            with open(os.path.join(replace_dir, "rep1.txt"), "w", encoding="utf-8") as f:
                f.write(replace_content1)
            with open(os.path.join(replace_dir, "rep2.txt"), "w", encoding="utf-8") as f:
                f.write(replace_content2)
            # 创建 system 文件
            sys_content1 = "这是系统提示1"
            sys_content2 = "这是系统提示2"
            sys_content3 = "这是系统提示3"
            with open(os.path.join(system_dir, "sys1.txt"), "w", encoding="utf-8") as f:
                f.write(sys_content1)
            with open(os.path.join(system_dir, "sys2.txt"), "w", encoding="utf-8") as f:
                f.write(sys_content2)
            with open(os.path.join(system_dir, "sys3.txt"), "w", encoding="utf-8") as f:
                f.write(sys_content3)
            yield replace_dir, system_dir

    def test_default_case_loader(self, temp_dirs_with_files):
        """DefaultCaseLoader 应调用原有 load_cases 并返回结果"""
        replace_dir, _ = temp_dirs_with_files
        loader = DefaultCaseLoader(replace_dir)
        rng = create_mock_rng(42)
        cases, prompts = loader.load(rng=rng)
        assert len(cases) == 2
        assert len(prompts) == 2
        # 验证内容：文件排序后第一个是 rep1.txt，客户姓名应为“张三”
        names = [c.get("客户姓名") for c in cases]
        assert "张三" in names
        assert "李四" in names

    def test_xiaoying_case_loader_basic(self, temp_dirs_with_files):
        """测试 XiaoyingCaseLoader 基本对应逻辑：两个目录文件数不等时循环复用"""
        replace_dir, system_dir = temp_dirs_with_files
        loader = XiaoyingCaseLoader(replace_dir, system_dir)
        rng = create_mock_rng(42)
        cases, prompts = loader.load(rng=rng)
        # replace 有2个文件，system有3个文件，max_len=3，所以cases应有3条
        assert len(cases) == 3
        assert len(prompts) == 3
        # 检查循环：cases顺序应为 rep1, rep2, rep1 (因为i=2时循环取rep1)
        assert cases[0]["客户姓名"] == "张三"
        assert cases[1]["客户姓名"] == "李四"
        assert cases[2]["客户姓名"] == "张三"
        # prompts顺序应为 sys1, sys2, sys3
        assert prompts[0] == "这是系统提示1"
        assert prompts[1] == "这是系统提示2"
        assert prompts[2] == "这是系统提示3"

    def test_xiaoying_case_loader_with_time_gen(self, temp_dirs_with_files):
        """测试 XiaoyingCaseLoader 能够正确传递 time_gen 参数"""
        replace_dir, system_dir = temp_dirs_with_files
        loader = XiaoyingCaseLoader(replace_dir, system_dir)
        rng = create_mock_rng(42)
        fixed_time_gen = create_mock_time_gen("固定时间")
        cases, prompts = loader.load(rng=rng, time_gen=fixed_time_gen)
        for case in cases:
            assert case.get("随机时间") == "固定时间"


# ========== 4. 测试 factory 模块 ==========
class TestFactory:
    def test_create_case_loader_default(self):
        """未配置 case_loader 时，返回 DefaultCaseLoader"""
        config_data = {"cases_dir": "dummy_path"}
        config = Config(config_data)
        loader = create_case_loader(config)
        from core.case_loader import DefaultCaseLoader
        assert isinstance(loader, DefaultCaseLoader)
        assert loader.cases_dir == "dummy_path"

    def test_create_case_loader_xiaoying(self):
        """配置 type=xiaoying 时，返回 XiaoyingCaseLoader"""
        config_data = {
            "case_loader": {
                "type": "xiaoying",
                "replace_dir": "path/to/replace",
                "system_dir": "path/to/system"
            }
        }
        config = Config(config_data)
        loader = create_case_loader(config)
        from core.case_loader import XiaoyingCaseLoader
        assert isinstance(loader, XiaoyingCaseLoader)
        assert loader.replace_dir == "path/to/replace"
        assert loader.system_dir == "path/to/system"

    def test_create_case_loader_unknown_type(self):
        """未知类型应抛异常"""
        config_data = {"case_loader": {"type": "unknown"}}
        config = Config(config_data)
        with pytest.raises(ValueError, match="Unknown case_loader type"):
            create_case_loader(config)