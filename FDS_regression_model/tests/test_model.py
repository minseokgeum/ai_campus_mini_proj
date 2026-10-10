"""실제 수집/성능 평가와 분리된 계산·입출력 계약 검사. 테스트 CSV는 임시 폴더에만 만든다."""
import contextlib
import io
import os
from unittest.mock import patch
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd

from semiconductor_model import detect, db_records, build_panel, read_inputs
from semiconductor_model.calendar import default_request_end, krx_calendar
from semiconductor_model.cleanup import clean_results
from semiconductor_model.config import DAILY_COLUMNS
from semiconductor_model.data import exceeds_return_limit
from semiconductor_model.download_data import download_inputs
from semiconductor_model.output import write_results
from semiconductor_model.paths import get_project_paths
from semiconductor_model.universe import get_universe
from semiconductor_model.__main__ import run_analysis


def model_panel(n=250):
    """회귀 정답을 독립적으로 계산할 수 있는 재현 가능한 입력."""
    rng = np.random.default_rng(71)
    market, sector = rng.normal(0, .01, (2, n))
    return pd.DataFrame({
        "date": pd.bdate_range("2024-01-02", periods=n), "code": "005930",
        "name": "삼성전자", "market": "KOSPI", "market_return": market,
        "sector_return": .6 * market + sector,
        "stock_return": .001 + .8 * market + 1.1 * sector + rng.normal(0, .004, n),
        "volume": np.exp(rng.normal(12, .2, n)), "peer_count": 35,
    })


def raw_inputs(n=310):
    """휴장일 API에 의존하지 않는 테스트 전용 달력과 37개 기업 원시 관측."""
    rng = np.random.default_rng(17)
    dates = pd.bdate_range("2024-01-02", periods=n)
    m1, m2, sector = rng.normal(0, .006, (3, n))
    stocks, markets = [], []
    for row in get_universe().itertuples(index=False):
        market = m1 if row.market == "KOSPI" else m2
        returns = .7 * market + sector + rng.normal(0, .004, n)
        stocks.append(pd.DataFrame({"date": dates, "code": row.code,
            "close": 30000 * np.cumprod(1 + returns),
            "volume": np.round(np.exp(rng.normal(12, .2, n)))}))
    for name, returns in [("KOSPI", m1), ("KOSDAQ", m2)]:
        markets.append(pd.DataFrame({"date": dates, "market": name,
                                    "close": 2000 * np.cumprod(1 + returns)}))
    return pd.concat(stocks, ignore_index=True), pd.concat(markets, ignore_index=True), pd.DataFrame({"date": dates})


class CalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel = model_panel()
        cls.result = detect(cls.panel)

    def test_exact_windows_and_column_contract(self):
        r = self.result
        self.assertEqual(list(r), DAILY_COLUMNS)
        self.assertEqual(len(r), len(self.panel))
        self.assertTrue(r.iloc[:120].expected_return.isna().all())
        self.assertTrue(r.iloc[:160].price_alert.isna().all())
        self.assertEqual(r.iloc[160].decision_status, "OK")
        self.assertTrue(r.iloc[:160].alert_type.isna().all())

    def test_two_stage_prediction_matches_independent_ols(self):
        t = 205
        past = self.panel.iloc[t-120:t]
        x = np.column_stack([np.ones(120), past.market_return, past.sector_return])
        coef = np.linalg.lstsq(x, past.stock_return, rcond=None)[0]
        expected = np.array([1, self.panel.iloc[t].market_return, self.panel.iloc[t].sector_return]) @ coef
        row = self.result.iloc[t]
        self.assertAlmostEqual(row.expected_return, expected, places=12)
        self.assertAlmostEqual(row.alpha + row.market_part + row.sector_part, expected, places=12)
        self.assertAlmostEqual(row.stock_return - row.expected_return, row.price_residual, places=12)

    def test_z_and_ratio_use_only_prior_40_sessions(self):
        t = 205
        row = self.result.iloc[t]
        residuals = self.result.price_residual.iloc[t-40:t]
        logs = np.log1p(self.panel.volume.iloc[t-40:t])
        self.assertAlmostEqual(row.price_z, (row.price_residual-residuals.mean())/residuals.std(ddof=1), places=11)
        self.assertAlmostEqual(row.volume_z, (np.log1p(self.panel.volume.iloc[t])-logs.mean())/logs.std(ddof=1), places=10)
        self.assertAlmostEqual(row.volume_ratio_40d, self.panel.volume.iloc[t]/self.panel.volume.iloc[t-40:t].mean(), places=12)

    def test_future_observations_cannot_change_past_results(self):
        changed = self.panel.copy()
        changed.loc[220:, "stock_return"] = .2
        changed.loc[220:, "volume"] *= 5
        changed.loc[220:, "market_return"] = -.12
        pd.testing.assert_frame_equal(self.result.iloc[:220], detect(changed).iloc[:220])

    def test_market_z_120_signed_two_sided(self):
        for shock in (-.12, .12):
            p = self.panel.copy()
            p.loc[249, "market_return"] = shock
            row = detect(p).iloc[-1]
            history = p.market_return.iloc[129:249]
            self.assertAlmostEqual(row.market_z, (shock-history.mean())/history.std(ddof=1), places=11)
            self.assertTrue(row.market_alert)
            self.assertEqual(np.sign(row.market_z), np.sign(shock))
        self.assertTrue(self.result.iloc[:120].market_alert.isna().all())

    def test_price_both_directions_and_one_sided_volume(self):
        for shock, direction in [(.12, "UP"), (-.12, "DOWN")]:
            p = self.panel.copy()
            p.loc[249, "stock_return"] = shock
            p.loc[249, "volume"] *= 10
            row = detect(p).iloc[-1]
            self.assertEqual(row.alert_type, "PRICE_AND_VOLUME")
            self.assertEqual(row.price_direction, direction)
            self.assertTrue(row.both_alert)
        p.loc[249, "volume"] = 1
        row = detect(p).iloc[-1]
        self.assertLess(row.volume_z, -2.5)
        self.assertFalse(row.volume_alert)

    def test_large_return_is_unevaluable_in_both_directions(self):
        for shock in (-.31, .31):
            p = self.panel.copy()
            p.loc[249, "stock_return"] = shock
            row = detect(p).iloc[-1]
            self.assertEqual(row.decision_status, "RETURN_EXCEEDS_30PCT")
            self.assertTrue(pd.isna(row.price_alert))
            self.assertTrue(pd.isna(row.volume_alert))
            self.assertTrue(pd.isna(row.alert_type))
            self.assertEqual(row.stock_return, shock)
        self.assertEqual(exceeds_return_limit(pd.Series([130/100-1, -.30, .3001, -.3001])).tolist(), [False, False, True, True])

    def test_missing_training_session_is_not_dropped(self):
        p = self.panel.copy()
        p.loc[190, "stock_return"] = np.nan
        row = detect(p).iloc[205]
        self.assertEqual(row.decision_status, "INCOMPLETE_REGRESSION_WINDOW")
        self.assertTrue(pd.isna(row.price_alert))

    def test_missing_price_z_blocks_even_large_volume_alert(self):
        p = self.panel.iloc[:140].copy()
        p.loc[139, "volume"] *= 100
        row = detect(p).iloc[-1]
        self.assertGreater(row.volume_z, 2.5)
        self.assertEqual(row.decision_status, "INCOMPLETE_PRICE_Z_WINDOW")
        self.assertTrue(pd.isna(row.volume_alert))

    def test_flat_inputs_are_not_falsely_normal(self):
        p = self.panel.copy()
        p["volume"] = 10000
        row = detect(p).iloc[-1]
        self.assertEqual(row.decision_status, "ZERO_VOLUME_SCALE")
        self.assertTrue(pd.isna(row.volume_alert))
        p = self.panel.copy()
        p["market_return"] = 0
        row = detect(p).iloc[-1]
        self.assertEqual(row.decision_status, "RANK_DEFICIENT_REGRESSION")
        self.assertTrue(pd.isna(row.market_alert))


class InputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stocks, cls.markets, cls.calendar = raw_inputs()

    def test_fixed_universe_and_leave_one_out(self):
        universe = get_universe()
        self.assertEqual((len(universe), int(universe.is_peer.sum()), int(universe.is_target.sum())), (37, 35, 6))
        panel = build_panel(self.stocks, self.markets, self.calendar)
        day = self.calendar.date.iloc[200]
        rows = panel.loc[panel.date.eq(day)].set_index("code")
        self.assertEqual(rows.loc["005930", "peer_count"], 35)
        self.assertEqual(rows.loc["000660", "peer_count"], 34)
        stocks = self.stocks.copy()
        mask = stocks.code.eq("000660") & stocks.date.eq(day)
        stocks.loc[mask, "close"] *= 1.1
        altered = build_panel(stocks, self.markets, self.calendar)
        new = altered.loc[altered.date.eq(day)].set_index("code")
        self.assertAlmostEqual(new.loc["000660", "sector_return"], rows.loc["000660", "sector_return"])
        self.assertNotAlmostEqual(new.loc["005930", "sector_return"], rows.loc["005930", "sector_return"])

    def test_peer_coverage_and_large_return_filter(self):
        day = self.calendar.date.iloc[200]
        stocks = self.stocks.copy()
        code = "403870"
        prev = stocks.loc[stocks.code.eq(code)].iloc[199].close
        stocks.loc[stocks.code.eq(code) & stocks.date.eq(day), "close"] = prev * 1.31
        panel = build_panel(stocks, self.markets, self.calendar)
        row = panel.loc[panel.code.eq("005930") & panel.date.eq(day)].iloc[0]
        self.assertEqual(row.peer_count, 34)
        non_targets = get_universe().query("is_peer and not is_target").code.tolist()
        for count, expected_valid in [(3, True), (4, False)]:
            missing = self.stocks.loc[~(self.stocks.code.isin(non_targets[:count]) & self.stocks.date.eq(day))]
            p = build_panel(missing, self.markets, self.calendar)
            for target, full_count in [("005930", 35), ("000660", 34)]:
                row = p.loc[p.code.eq(target) & p.date.eq(day)].iloc[0]
                self.assertEqual(row.peer_count, full_count-count)
                self.assertEqual(pd.notna(row.sector_return), expected_valid)

    def test_missing_quote_keeps_session_and_blocks_resumed_multiday_return(self):
        day = self.calendar.date.iloc[200]
        stocks = self.stocks.loc[~(self.stocks.code.eq("005930") & self.stocks.date.eq(day))]
        rows = build_panel(stocks, self.markets, self.calendar).query("code == '005930'").reset_index(drop=True)
        self.assertEqual(len(rows), len(self.calendar))
        self.assertEqual(rows.iloc[200].input_status, "MISSING_PRICE")
        self.assertEqual(rows.iloc[201].input_status, "MISSING_PREVIOUS_QUOTE")
        self.assertTrue(rows.iloc[200:202].stock_return.isna().all())
        self.assertTrue(pd.notna(rows.iloc[202].stock_return))

    def test_zero_volume_is_not_forward_filled(self):
        stocks = self.stocks.copy()
        day = self.calendar.date.iloc[200]
        stocks.loc[stocks.code.eq("005930") & stocks.date.eq(day), "volume"] = 0
        p = build_panel(stocks, self.markets, self.calendar).query("code == '005930'").reset_index(drop=True)
        self.assertEqual(p.iloc[200].input_status, "MISSING_OR_ZERO_VOLUME")
        self.assertTrue(p.iloc[200:202].stock_return.isna().all())

    def test_market_missing_and_calendar_conflict_raise(self):
        with self.assertRaisesRegex(ValueError, "거래일 지수 누락"):
            build_panel(self.stocks, self.markets.iloc[1:], self.calendar)
        with self.assertRaisesRegex(ValueError, "캘린더 밖"):
            build_panel(self.stocks, self.markets, self.calendar.iloc[1:])

    def test_duplicate_observations_raise(self):
        with self.assertRaisesRegex(ValueError, "중복"):
            build_panel(pd.concat([self.stocks, self.stocks.iloc[:1]]), self.markets, self.calendar)

    def test_known_holidays_and_kst_end_policy(self):
        dates = set(krx_calendar("2026-06-01", "2026-07-20").date)
        self.assertNotIn(pd.Timestamp("2026-06-03"), dates)
        self.assertNotIn(pd.Timestamp("2026-07-17"), dates)
        self.assertIn(pd.Timestamp("2026-06-04"), dates)
        self.assertEqual(default_request_end("2026-10-08T08:59:00Z"), pd.Timestamp("2026-10-07"))
        self.assertEqual(default_request_end("2026-10-08T09:00:00Z"), pd.Timestamp("2026-10-08"))


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project_root = Path(self.temp.name) / "repo"
        self.paths = get_project_paths(self.project_root)
        self.rows = detect(model_panel()).tail(5).reset_index(drop=True)
        # 계산 검사는 위에서 수행. 이곳은 네 가지 분류와 판정 불가의 저장 계약을 검사한다.
        kinds = ["NO_ALERT", "PRICE_ONLY", "VOLUME_ONLY", "PRICE_AND_VOLUME", pd.NA]
        self.rows["alert_type"] = pd.Series(kinds, dtype="string")
        self.rows["decision_status"] = ["OK"] * 4 + ["INCOMPLETE_PRICE_Z_WINDOW"]
        for col, values in {
            "price_alert": [False, True, False, True, pd.NA],
            "volume_alert": [False, False, True, True, pd.NA],
            "both_alert": [False, False, False, True, pd.NA],
            "market_alert": [True, False, False, True, True],
        }.items():
            self.rows[col] = pd.Series(values, dtype="boolean")
        self.rows["price_direction"] = pd.Series([pd.NA, "UP", pd.NA, "DOWN", pd.NA], dtype="string")

    def test_csv_json_and_db_contract(self):
        manifest = write_results(self.rows, self.project_root)
        self.assertEqual(manifest["stock_alert_json_count"], 3)
        self.assertEqual(len(list((self.paths.anomaly_dir).glob("*.json"))), 3)
        csv = pd.read_csv(self.paths.daily_csv, dtype={"code": str})
        self.assertEqual(list(csv), DAILY_COLUMNS)
        self.assertEqual(set(csv.code), {"005930"})
        self.assertTrue(pd.isna(csv.iloc[-1].price_alert))
        volume_row = self.rows.iloc[2]
        file = self.paths.anomaly_dir / f"{volume_row.date.date()}_삼성전자.json"
        payload = json.loads(file.read_text(encoding="utf-8"))
        anomaly = payload["anomaly"]
        self.assertIsNone(anomaly["direction"])
        self.assertNotIn("price_alert", anomaly)
        self.assertIsInstance(anomaly["market_alert"], bool)
        self.assertEqual(set(anomaly["regression"]), {"market_beta", "sector_beta", "market_contribution", "sector_contribution"})
        self.assertNotIn("NaN", file.read_text(encoding="utf-8"))
        self.assertEqual(set(payload), {"date", "code", "name", "market", "anomaly"})
        records = db_records(self.rows)
        self.assertIsNone(records[-1]["price_alert"])
        self.assertIsInstance(records[0]["price_alert"], bool)
        self.assertEqual(records[0]["code"], "005930")

    def test_rerun_removes_stale_generated_json(self):
        write_results(self.rows, self.project_root)
        other = self.project_root / "notes.txt"
        other.write_text("보존", encoding="utf-8")
        write_results(self.rows.iloc[[0]], self.project_root)
        self.assertEqual(list((self.paths.anomaly_dir).glob("*.json")), [])
        self.assertTrue(other.exists())

    def test_cleanup_dry_run_and_apply_keep_unrelated_files(self):
        write_results(self.rows, self.project_root)
        relatives = ["stored_data/dart/disclosure.xml", "stored_data/news/news.json",
                     "source_data/source_news/cleaned.json", "result/evidences.json",
                     "result/results.txt", "source_data/anormaly_result/.gitkeep",
                     "source_data/anormaly_result/manual_note.json",
                     "FDS_regression_model/data/stocks.csv"]
        others = [self.project_root / relative for relative in relatives]
        for other in others:
            other.parent.mkdir(parents=True, exist_ok=True)
            other.write_text("보존", encoding="utf-8")
        paths = clean_results(self.project_root)
        self.assertTrue(all(path.exists() for path in paths))
        clean_results(self.project_root, apply=True)
        self.assertTrue(all(other.read_text(encoding="utf-8") == "보존" for other in others))
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertTrue(self.paths.anomaly_dir.is_dir())
        self.assertTrue(self.paths.daily_csv.parent.is_dir())

    def test_cleanup_rejects_path_traversal(self):
        manifest = write_results(self.rows, self.project_root)
        manifest["generated_files"].append("../stocks.csv")
        (self.paths.manifest).write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "허용되지 않은 경로"):
            clean_results(self.project_root, apply=True)
        self.assertTrue((self.paths.daily_csv).exists())

    def test_unmanaged_csv_is_not_overwritten(self):
        self.paths.daily_csv.parent.mkdir(parents=True)
        file = self.paths.daily_csv
        file.write_text("사용자 파일", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "덮어쓰지"):
            write_results(self.rows, self.project_root)
        self.assertEqual(file.read_text(encoding="utf-8"), "사용자 파일")

    def test_cleanup_cannot_target_other_teams_json(self):
        manifest = write_results(self.rows, self.project_root)
        other = self.project_root / "source_data/source_news/news.json"
        other.parent.mkdir(parents=True)
        other.write_text("보존", encoding="utf-8")
        manifest["generated_files"].append("source_data/source_news/news.json")
        self.paths.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "허용되지 않은 경로"):
            clean_results(self.project_root, apply=True)
        self.assertEqual(other.read_text(encoding="utf-8"), "보존")

    def test_default_paths_do_not_depend_on_terminal_directory(self):
        fake_source = self.project_root / "FDS_regression_model/semiconductor_model/paths.py"
        self.paths.model_dir.mkdir(parents=True)
        elsewhere = Path(self.temp.name) / "elsewhere"
        elsewhere.mkdir()
        original_cwd = Path.cwd()
        try:
            with patch("semiconductor_model.paths.__file__", str(fake_source)):
                for cwd in (self.project_root, self.paths.model_dir, elsewhere):
                    os.chdir(cwd)
                    paths = get_project_paths()
                    self.assertEqual(paths, self.paths)
                    write_results(self.rows)  # project_root를 생략한 실제 기본 저장 검사
                    self.assertTrue(paths.daily_csv.is_file())
                    self.assertEqual(len(list(paths.anomaly_dir.glob("*.json"))), 3)
                    self.assertFalse((cwd / "outputs").exists())
        finally:
            os.chdir(original_cwd)


class IntegrationTests(unittest.TestCase):
    def test_downloader_csv_to_model_to_json_without_network(self):
        stocks, markets, calendar = raw_inputs()
        calls = []

        def reader(symbol, start, end):
            calls.append(symbol)
            if symbol.startswith("NAVER:"):
                return stocks.loc[stocks.code.eq(symbol.split(":")[1])].set_index("date")[["close", "volume"]].rename(columns={"close": "Close", "volume": "Volume"})
            name = {"YAHOO:^KS11": "KOSPI", "YAHOO:^KQ11": "KOSDAQ"}[symbol]
            return markets.loc[markets.market.eq(name)].set_index("date")[["close"]].rename(columns={"close": "Close"})

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            project = Path(tmp) / "team_repo"
            paths = get_project_paths(project)
            data = paths.data_dir
            download_inputs(project_root=project, start=calendar.date.min(), end=calendar.date.max(),
                            calendar=calendar, reader=reader, now="2026-10-08T09:00:00Z")
            loaded = read_inputs(data)
            self.assertEqual(len(loaded[0]), len(stocks))
            result = run_analysis(project_root=project, end=str(calendar.date.max().date()))
            self.assertEqual(len(calls), 39)
            self.assertEqual(len(result), int(calendar.date.ge("2025-01-01").sum()) * 6)
            self.assertTrue(result.date.ge("2025-01-01").all())
            self.assertTrue(result.decision_status.eq("OK").all())
            alerts = result.price_alert | result.volume_alert
            self.assertEqual(len(list(paths.anomaly_dir.glob("*.json"))), int(alerts.sum()))
            clean_results(project, apply=True)
            self.assertTrue((data / "stocks.csv").exists())


if __name__ == "__main__":
    unittest.main()
