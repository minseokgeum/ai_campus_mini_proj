"""CSV 입력 검증과 35개 동일가중·자기 제외 산업 평균 구성."""
from pathlib import Path
import numpy as np
import pandas as pd
from .config import CONFIG, MARKET_SYMBOLS
from .universe import get_universe


def normalize_dates(frame, label):
    """CSV 날짜는 한국 거래일 라벨(YYYY-MM-DD)이다. 중간 날짜를 삭제하지 않는다."""
    result = frame.copy()
    if "date" not in result:
        raise ValueError(f"{label}: date 컬럼이 필요합니다.")
    result["date"] = pd.to_datetime(result["date"], errors="raise")
    if result["date"].isna().any() or result["date"].dt.tz is not None:
        raise ValueError(f"{label}: date는 시간대 없는 유효 거래일이어야 합니다.")
    if not result["date"].eq(result["date"].dt.normalize()).all():
        raise ValueError(f"{label}: 날짜에 시각을 넣지 마세요.")
    return result


def validate_calendar(calendar):
    calendar = normalize_dates(calendar, "calendar.csv").sort_values("date")
    if calendar.empty or calendar["date"].duplicated().any():
        raise ValueError("거래일 목록이 비었거나 중복되었습니다.")
    if calendar["date"].dt.dayofweek.ge(5).any():
        raise ValueError("거래일 목록에 주말이 있습니다.")
    return calendar.reset_index(drop=True)


def exceeds_return_limit(values, config=CONFIG):
    # 130/100-1 같은 부동소수점 계산으로 정확히 30%인 값이 잘못 제외되지 않게 한다.
    return values.abs().gt(config.max_abs_stock_return + config.scale_floor)


def read_inputs(data_dir, end=None):
    """수집한 CSV만 읽는다. 이 함수와 모델 실행은 인터넷에 접속하지 않는다."""
    root = Path(data_dir)
    calendar = validate_calendar(pd.read_csv(root / "calendar.csv"))
    stocks = normalize_dates(pd.read_csv(root / "stocks.csv", dtype={"code": str}), "stocks.csv")
    markets = normalize_dates(pd.read_csv(root / "markets.csv"), "markets.csv")
    universe = pd.read_csv(root / "universe.csv", dtype={"code": str})
    expected = get_universe()
    for column in ("is_peer", "is_target"):
        if column not in universe:
            raise ValueError(f"universe.csv: {column} 누락")
        values = universe[column].astype(str).str.lower().map({"true": True, "false": False})
        if values.isna().any():
            raise ValueError(f"universe.csv: {column}은 True/False여야 합니다.")
        universe[column] = values
    try:
        pd.testing.assert_frame_equal(universe[expected.columns].sort_values("code").reset_index(drop=True),
                                      expected.sort_values("code").reset_index(drop=True), check_dtype=False)
    except AssertionError as exc:
        raise ValueError("universe.csv가 고정 35 peer·6 target 설정과 다릅니다.") from exc
    if end is not None:
        end = pd.Timestamp(end)
        calendar = calendar.loc[calendar.date.le(end)]
        stocks = stocks.loc[stocks.date.le(end)]
        markets = markets.loc[markets.date.le(end)]
    return stocks, markets, validate_calendar(calendar), universe


def build_panel(stocks, markets, calendar, universe=None, config=CONFIG):
    """원시 종가·거래량을 회귀 입력으로 변환한다.

    [요구사항] 휴장일은 calendar에 없으며, 거래일의 결측은 NaN 행으로 남긴다.
    가격/거래량을 앞 값 또는 0으로 채우지 않는다. 거래정지 뒤 첫 다기간 수익률도 제외한다.
    절대 수익률 30% 초과 값은 peer 평균과 회귀 학습에서 제외한다.
    대상 기업의 관측 수익률은 진단을 위해 stock_return에 그대로 남긴다.
    """
    universe = get_universe() if universe is None else universe.copy()
    calendar = validate_calendar(calendar)
    dates = pd.DatetimeIndex(calendar.date, name="date")
    stocks, markets = normalize_dates(stocks, "stocks"), normalize_dates(markets, "markets")
    for frame, columns, keys, label in [
        (stocks, {"date", "code", "close", "volume"}, ["date", "code"], "stocks"),
        (markets, {"date", "market", "close"}, ["date", "market"], "markets"),
    ]:
        if not columns <= set(frame):
            raise ValueError(f"{label}: 필수 컬럼 누락 {sorted(columns-set(frame))}")
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError(f"{label}: 식별자 결측/중복")
        outside = frame.loc[~frame.date.isin(dates), "date"]
        if len(outside):
            raise ValueError(f"{label}: 거래일 캘린더 밖의 시세 {outside.dt.strftime('%Y-%m-%d').unique()[:5].tolist()}. 휴장일/요청 범위를 확인하세요.")
    stocks["code"] = stocks["code"].astype(str).str.zfill(6)
    if stocks.duplicated(["date", "code"]).any() or not stocks.code.str.fullmatch(r"\d{6}").all():
        raise ValueError("종목 코드는 중복 없는 6자리 문자열이어야 합니다.")
    if set(stocks.code) != set(universe.code):
        raise ValueError("stocks.csv에는 수집 대상 37개 기업이 모두 있어야 합니다.")
    if set(markets.market) != set(MARKET_SYMBOLS):
        raise ValueError("KOSPI와 KOSDAQ 지수가 모두 필요합니다.")
    market_parts = []
    for market in MARKET_SYMBOLS:
        raw = markets.loc[markets.market.eq(market)].set_index("date")
        close = pd.to_numeric(raw.close, errors="coerce").reindex(dates)
        close = close.where(np.isfinite(close) & close.gt(0))
        # 원본 정책: 공식 거래일의 지수 누락은 휴장일로 간주하지 않고 입력 오류로 중단.
        if close.isna().any():
            missing = dates[close.isna()].strftime("%Y-%m-%d").tolist()
            raise ValueError(f"{market}: 거래일 지수 누락 {missing[:10]}. 캘린더와 원자료를 확인하세요.")
        market_parts.append(pd.DataFrame({"date": dates, "market": market,
                                          "market_return": close.pct_change(fill_method=None).to_numpy()}))
    market_daily = pd.concat(market_parts, ignore_index=True)
    stock_parts = []
    for row in universe.itertuples(index=False):
        raw = stocks.loc[stocks.code.eq(row.code)].set_index("date")
        close = pd.to_numeric(raw.close, errors="coerce").reindex(dates)
        volume = pd.to_numeric(raw.volume, errors="coerce").reindex(dates)
        good_price = np.isfinite(close) & close.gt(0)
        good_volume = np.isfinite(volume) & volume.gt(0)
        usable = good_price & good_volume
        returns = close.where(usable).pct_change(fill_method=None)
        excessive = exceeds_return_limit(returns, config)
        status = np.select([~good_price, ~good_volume, excessive, returns.isna()],
                           ["MISSING_PRICE", "MISSING_OR_ZERO_VOLUME", "RETURN_EXCEEDS_30PCT", "MISSING_PREVIOUS_QUOTE"],
                           default="OK")
        stock_parts.append(pd.DataFrame({
            "date": dates, "code": row.code, "name": row.name, "market": row.market,
            "stock_return": returns.to_numpy(), "model_stock_return": returns.mask(excessive).to_numpy(),
            "volume": volume.to_numpy(), "usable_quote": usable.to_numpy(), "input_status": status,
        }))
    daily = pd.concat(stock_parts, ignore_index=True)
    wide = daily.pivot(index="date", columns="code", values="model_stock_return").reindex(dates)
    peer_codes = universe.loc[universe.is_peer, "code"].tolist()
    bench_parts = []
    for target in universe.loc[universe.is_target].itertuples(index=False):
        # [요구사항] 시장 구분 없는 35개 풀. 대상 자신이 포함된 경우에만 제외한다.
        peer_returns = wide[[code for code in peer_codes if code != target.code]]
        count = peer_returns.notna().sum(axis=1)
        required = int(np.ceil(peer_returns.shape[1] * config.min_peer_coverage))
        sector = peer_returns.mean(axis=1).where(count.ge(required))
        bench_parts.append(pd.DataFrame({"date": dates, "code": target.code,
                                        "sector_return": sector.to_numpy(), "peer_count": count.to_numpy()}))
    panel = daily.loc[daily.code.isin(universe.loc[universe.is_target, "code"])].merge(
        pd.concat(bench_parts), on=["date", "code"], validate="one_to_one")
    panel = panel.merge(market_daily, on=["date", "market"], validate="many_to_one")
    return panel.sort_values(["code", "date"]).reset_index(drop=True)
