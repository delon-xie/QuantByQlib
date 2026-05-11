"""
factor_injector 单元测试
覆盖：validate_factor / get_valid_factors / save/load/clear / get_inject_status
所有 Qlib / SessionManager 依赖均用 unittest.mock patch 隔离，无需真实数据。

关键技术说明：
  factor_injector.py 内所有外部依赖均为函数内延迟导入（lazy import），
  patch 路径必须是其原始模块，例如：
    "data.qlib_manager._find_data_dir"  而非
    "strategies.factor_injector._find_data_dir"
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _make_multi_series(dates, instruments, values):
    """构造 (datetime, instrument) MultiIndex 的 pd.Series"""
    import pandas as pd
    idx = pd.MultiIndex.from_product([dates, instruments],
                                     names=["datetime", "instrument"])
    return pd.Series(list(values)[:len(idx)], index=idx)


# ──────────────────────────────────────────────────────────────
#  1. validate_factor
# ──────────────────────────────────────────────────────────────
class TestValidateFactor(unittest.TestCase):

    def _make_cal_path_mock(self, n_dates: int = 300):
        """返回模拟日历文件路径 mock，有 n_dates 行"""
        import pandas as pd
        cal_dates = pd.date_range("2020-01-02", periods=n_dates, freq="B")
        cal_text  = "\n".join(d.strftime("%Y-%m-%d") for d in cal_dates)
        mock = MagicMock()
        mock.exists.return_value = True
        mock.read_text.return_value = cal_text
        return mock

    def _make_data_dir_mock(self, cal_mock):
        """模拟 _find_data_dir() 返回的 data_dir 对象"""
        # data_dir / "calendars" / "day.txt"
        cal_dir = MagicMock()
        cal_dir.__truediv__ = MagicMock(return_value=cal_mock)
        data_dir = MagicMock()

        def _div(key):
            return cal_dir if key == "calendars" else MagicMock()

        data_dir.__truediv__ = MagicMock(side_effect=_div)
        return data_dir

    def test_valid_factor_passes_ic_threshold(self):
        """IC 均值 ≥ 0.03 时应返回 True"""
        import pandas as pd
        import numpy as np

        dates       = pd.date_range("2023-01-02", periods=60, freq="B")
        instruments = ["aapl", "msft", "nvda", "amzn", "googl"]
        n           = len(dates) * len(instruments)

        rng         = np.random.default_rng(42)
        factor_vals = rng.standard_normal(n)
        ret_vals    = factor_vals * 0.7 + rng.standard_normal(n) * 0.1

        factor_df = pd.DataFrame({0: _make_multi_series(dates, instruments, factor_vals)})
        ret_df    = pd.DataFrame({0: _make_multi_series(dates, instruments, ret_vals)})

        cal_mock  = self._make_cal_path_mock(300)
        data_dir  = self._make_data_dir_mock(cal_mock)

        mock_D = MagicMock()
        mock_D.features.side_effect = [factor_df, ret_df]

        with patch("qlib.data.D", mock_D), \
             patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor(
                "Ref($close,5)/$close-1",
                ["aapl", "msft", "nvda", "amzn", "googl"],
                threshold_ic=0.03,
            )
        self.assertTrue(result)

    def test_invalid_factor_fails_ic_threshold(self):
        """高阈值下随机噪声因子应返回 False"""
        import pandas as pd
        import numpy as np

        dates       = pd.date_range("2023-01-02", periods=60, freq="B")
        instruments = ["aapl", "msft"]
        n           = len(dates) * len(instruments)

        rng         = np.random.default_rng(0)
        factor_vals = rng.standard_normal(n)
        ret_vals    = rng.standard_normal(n)   # 完全独立，IC ≈ 0

        factor_df = pd.DataFrame({0: _make_multi_series(dates, instruments, factor_vals)})
        ret_df    = pd.DataFrame({0: _make_multi_series(dates, instruments, ret_vals)})

        cal_mock = self._make_cal_path_mock(300)
        data_dir = self._make_data_dir_mock(cal_mock)

        mock_D = MagicMock()
        mock_D.features.side_effect = [factor_df, ret_df]

        with patch("qlib.data.D", mock_D), \
             patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor(
                "random_noise",
                ["aapl", "msft"],
                threshold_ic=0.80,   # 极高阈值，随机数据必然失败
            )
        self.assertFalse(result)

    def test_validate_factor_missing_calendar(self):
        """日历文件不存在时应返回 False（不抛异常）"""
        cal_mock = MagicMock()
        cal_mock.exists.return_value = False
        data_dir = self._make_data_dir_mock(cal_mock)

        with patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor("$close", ["aapl"], threshold_ic=0.03)
        self.assertFalse(result)

    def test_validate_factor_too_few_calendar_dates(self):
        """日历行数不足 VALIDATE_DAYS+5 时应返回 False"""
        cal_mock = self._make_cal_path_mock(n_dates=10)  # 远少于 252+5
        data_dir = self._make_data_dir_mock(cal_mock)

        with patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor("$close", ["aapl"], threshold_ic=0.03)
        self.assertFalse(result)

    def test_validate_factor_exception_returns_false(self):
        """D.features 抛异常时应静默返回 False"""
        cal_mock = self._make_cal_path_mock(300)
        data_dir = self._make_data_dir_mock(cal_mock)

        mock_D = MagicMock()
        mock_D.features.side_effect = RuntimeError("Qlib crash")

        with patch("qlib.data.D", mock_D), \
             patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor("$close", ["aapl"], threshold_ic=0.03)
        self.assertFalse(result)

    def test_validate_factor_empty_data_returns_false(self):
        """D.features 返回空 DataFrame 时应返回 False"""
        import pandas as pd

        cal_mock = self._make_cal_path_mock(300)
        data_dir = self._make_data_dir_mock(cal_mock)

        mock_D = MagicMock()
        mock_D.features.return_value = pd.DataFrame()

        with patch("qlib.data.D", mock_D), \
             patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor("$close", ["aapl"], threshold_ic=0.03)
        self.assertFalse(result)

    def test_validate_factor_insufficient_common_samples(self):
        """公共样本不足 30 时应返回 False"""
        import pandas as pd
        import numpy as np

        # 只有 5 行数据（< 30）
        dates       = pd.date_range("2023-01-02", periods=5, freq="B")
        instruments = ["aapl"]
        n           = len(dates) * len(instruments)

        rng         = np.random.default_rng(1)
        factor_vals = rng.standard_normal(n)
        ret_vals    = rng.standard_normal(n)

        factor_df = pd.DataFrame({0: _make_multi_series(dates, instruments, factor_vals)})
        ret_df    = pd.DataFrame({0: _make_multi_series(dates, instruments, ret_vals)})

        cal_mock = self._make_cal_path_mock(300)
        data_dir = self._make_data_dir_mock(cal_mock)

        mock_D = MagicMock()
        mock_D.features.side_effect = [factor_df, ret_df]

        with patch("qlib.data.D", mock_D), \
             patch("data.qlib_manager._find_data_dir", return_value=data_dir):
            from strategies.factor_injector import validate_factor
            result = validate_factor("$close", ["aapl"], threshold_ic=0.03)
        self.assertFalse(result)


# ──────────────────────────────────────────────────────────────
#  2. save / load / clear / get_inject_status
# ──────────────────────────────────────────────────────────────
class TestPersistence(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmpdir  = tempfile.mkdtemp()
        self._tmp_json = Path(self._tmpdir) / "valid_factors.json"
        self._patcher = patch(
            "strategies.factor_injector.VALID_FACTORS_FILE",
            self._tmp_json,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load_roundtrip(self):
        from strategies.factor_injector import save_valid_factors, load_valid_factors
        exprs = ["Ref($close,5)/$close-1", "$volume/Ref($volume,10)-1"]
        save_valid_factors(exprs)
        loaded = load_valid_factors(max_age_hours=24.0)
        self.assertEqual(loaded, exprs)

    def test_load_empty_when_file_missing(self):
        from strategies.factor_injector import load_valid_factors
        self.assertEqual(load_valid_factors(), [])

    def test_load_expired_returns_empty(self):
        import os
        from strategies.factor_injector import save_valid_factors, load_valid_factors
        save_valid_factors(["Ref($close,5)/$close-1"])
        old_time = time.time() - 3601
        os.utime(self._tmp_json, (old_time, old_time))
        self.assertEqual(load_valid_factors(max_age_hours=1.0), [])

    def test_clear_valid_factors(self):
        from strategies.factor_injector import (
            save_valid_factors, load_valid_factors, clear_valid_factors
        )
        save_valid_factors(["$close"])
        clear_valid_factors()
        self.assertEqual(load_valid_factors(), [])

    def test_clear_nonexistent_file_no_error(self):
        from strategies.factor_injector import clear_valid_factors
        clear_valid_factors()   # 不应抛出

    def test_get_inject_status_no_file(self):
        from strategies.factor_injector import get_inject_status
        status = get_inject_status()
        self.assertFalse(status["injected"])
        self.assertEqual(status["count"], 0)
        self.assertIsNone(status["updated_at"])

    def test_get_inject_status_with_file(self):
        from strategies.factor_injector import save_valid_factors, get_inject_status
        exprs = ["Ref($close,5)/$close-1", "$high/$low-1"]
        save_valid_factors(exprs)
        status = get_inject_status()
        self.assertTrue(status["injected"])
        self.assertEqual(status["count"], 2)
        self.assertIsNotNone(status["updated_at"])
        self.assertEqual(len(status["expressions"]), 2)

    def test_save_creates_parent_dir(self):
        deeper = Path(self._tmpdir) / "sub" / "deep" / "valid_factors.json"
        with patch("strategies.factor_injector.VALID_FACTORS_FILE", deeper):
            from strategies.factor_injector import save_valid_factors
            save_valid_factors(["$close"])
        self.assertTrue(deeper.exists())

    def test_load_invalid_json_returns_empty(self):
        self._tmp_json.parent.mkdir(parents=True, exist_ok=True)
        self._tmp_json.write_text("NOT_VALID_JSON", encoding="utf-8")
        from strategies.factor_injector import load_valid_factors
        self.assertEqual(load_valid_factors(), [])

    def test_json_format_has_required_keys(self):
        from strategies.factor_injector import save_valid_factors
        save_valid_factors(["$open/$close-1"])
        data = json.loads(self._tmp_json.read_text(encoding="utf-8"))
        self.assertIn("updated_at", data)
        self.assertIn("count", data)
        self.assertIn("expressions", data)
        self.assertEqual(data["count"], 1)


# ──────────────────────────────────────────────────────────────
#  3. get_valid_factors（批量验证流程）
# ──────────────────────────────────────────────────────────────
class TestGetValidFactors(unittest.TestCase):
    """
    get_valid_factors 内部使用 lazy import：
      from rdagent_integration.session_manager import get_session_manager
      from strategies.qlib_strategy import _qlib_init_check, _get_qlib_data_end_date
    必须 patch 原始模块路径。
    """

    def setUp(self):
        import tempfile
        self._tmpdir   = tempfile.mkdtemp()
        self._tmp_json = Path(self._tmpdir) / "valid_factors.json"
        self._patcher  = patch(
            "strategies.factor_injector.VALID_FACTORS_FILE",
            self._tmp_json,
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _mock_session(self, factors):
        """构建 session_manager mock，返回给定的 factors 列表"""
        mock_mgr = MagicMock()
        mock_mgr.get_latest.return_value = {"factors": factors}
        mock_session_module = MagicMock()
        mock_session_module.get_session_manager.return_value = mock_mgr
        return mock_session_module

    def test_no_session_returns_empty(self):
        mock_mgr = MagicMock()
        mock_mgr.get_latest.return_value = None
        mock_mod  = MagicMock()
        mock_mod.get_session_manager.return_value = mock_mgr

        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}):
            from strategies.factor_injector import get_valid_factors
            result = get_valid_factors()
        self.assertEqual(result, [])

    def test_empty_factors_session_returns_empty(self):
        mock_mod = self._mock_session([])
        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}):
            from strategies.factor_injector import get_valid_factors
            result = get_valid_factors()
        self.assertEqual(result, [])

    def test_prefilter_excludes_low_ic(self):
        """ic_mean 明确低于阈值的因子不应进入 Qlib 验证"""
        mock_mod = self._mock_session([
            {"expression": "bad_factor", "ic_mean": 0.001},
        ])

        # validate_factor 是在同模块内调用的，可以直接 patch
        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}), \
             patch("strategies.factor_injector.validate_factor") as mock_vf, \
             patch("strategies.qlib_strategy._qlib_init_check"), \
             patch("strategies.qlib_strategy._get_qlib_data_end_date"):
            from strategies.factor_injector import get_valid_factors
            result = get_valid_factors(min_ic=0.03)

        mock_vf.assert_not_called()   # 预筛已过滤
        self.assertEqual(result, [])

    def test_prefilter_passes_unknown_ic(self):
        """ic_mean=None 的因子应进入 Qlib 验证"""
        mock_mod = self._mock_session([
            {"expression": "unknown_ic_factor", "ic_mean": None},
        ])
        validated = []

        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}), \
             patch("strategies.factor_injector.validate_factor",
                    side_effect=lambda e, u, t: validated.append(e) or True), \
             patch("strategies.qlib_strategy._qlib_init_check"), \
             patch("strategies.qlib_strategy._get_qlib_data_end_date"):
            from strategies.factor_injector import get_valid_factors
            result = get_valid_factors(min_ic=0.03)

        self.assertIn("unknown_ic_factor", validated)
        self.assertIn("unknown_ic_factor", result)

    def test_qlib_unavailable_falls_back_to_reported_ic(self):
        """Qlib 不可用时应信任 RD-Agent 报告的 ic_mean"""
        mock_mod = self._mock_session([
            {"expression": "factor_a", "ic_mean": 0.05},
            {"expression": "factor_b", "ic_mean": 0.01},
            {"expression": "factor_c", "ic_mean": None},
        ])

        # factor_injector 中 _qlib_init_check 是 lazy import 自 strategies.qlib_strategy
        # 需要直接 patch strategies.qlib_strategy 模块上的函数
        import strategies.qlib_strategy as qs_mod
        original_check = qs_mod._qlib_init_check

        def raise_runtime(*a, **kw):
            raise RuntimeError("Qlib 未就绪")

        qs_mod._qlib_init_check = raise_runtime
        try:
            with patch.dict("sys.modules",
                            {"rdagent_integration.session_manager": mock_mod}):
                from strategies.factor_injector import get_valid_factors
                result = get_valid_factors(min_ic=0.03)
        finally:
            qs_mod._qlib_init_check = original_check

        self.assertIn("factor_a", result)   # ic=0.05 ≥ 0.03
        self.assertIn("factor_c", result)   # ic=None，默认通过
        self.assertNotIn("factor_b", result)  # ic=0.01 < 0.03

    def test_progress_callback_called(self):
        """progress_cb 应在关键节点被调用"""
        mock_mod = self._mock_session([
            {"expression": "expr1", "ic_mean": 0.05},
        ])
        progress_calls = []

        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}), \
             patch("strategies.factor_injector.validate_factor",
                    return_value=True), \
             patch("strategies.qlib_strategy._qlib_init_check"), \
             patch("strategies.qlib_strategy._get_qlib_data_end_date"):
            from strategies.factor_injector import get_valid_factors
            get_valid_factors(
                min_ic=0.03,
                progress_cb=lambda pct, msg: progress_calls.append(pct),
            )

        self.assertGreater(len(progress_calls), 0)
        # 最后一次应 >= 90%
        self.assertGreaterEqual(progress_calls[-1], 90)

    def test_session_manager_exception_returns_empty(self):
        """session_manager 抛出异常时应返回空列表，不崩溃"""
        mock_mod = MagicMock()
        mock_mod.get_session_manager.side_effect = ImportError("module not found")

        with patch.dict("sys.modules",
                        {"rdagent_integration.session_manager": mock_mod}):
            from strategies.factor_injector import get_valid_factors
            result = get_valid_factors()
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
