"""120일 2단계 OLS + 40일 가격/거래량 Z. 외부 접속과 파일 저장이 없는 계산 모듈."""
import json
import numpy as np
import pandas as pd
from .config import CONFIG, DAILY_COLUMNS, ModelConfig
from .data import exceeds_return_limit


def _ols(x, y, floor):
    """수치 안정성을 위해 X를 표준화해 추정한 뒤 원 단위 계수로 복원한다."""
    mean, scale = x.mean(axis=0), x.std(axis=0, ddof=0)
    if np.any(scale <= floor):
        return None
    design = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    coefficient, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != design.shape[1]:
        return None
    beta = coefficient[1:] / scale
    return float(coefficient[0] - mean @ beta), beta


def add_market_scores(panel, config=CONFIG):
    """[요구사항] 시장별 수익률 자체의 과거 120거래일 Z와 |Z|>=3 경보만 추가한다."""
    check = panel.groupby(["date", "market"])["market_return"].agg(["size", "count", "nunique"])
    if check["nunique"].gt(1).any() or ((check["count"] > 0) & (check["count"] < check["size"])).any():
        raise ValueError("같은 시장·날짜의 지수 수익률이 종목마다 다릅니다.")
    unique = panel[["date", "market", "market_return"]].drop_duplicates(["date", "market"])
    scored = []
    for market, group in unique.groupby("market"):
        group = group.sort_values("date").copy()
        reference = group.market_return.shift(1).rolling(config.market_z_window, min_periods=config.market_z_window)
        scale = reference.std(ddof=config.std_ddof)
        group["market_z"] = (group.market_return - reference.mean()) / scale.where(scale > config.scale_floor)
        group["market_alert"] = pd.Series(pd.NA, index=group.index, dtype="boolean")
        valid = np.isfinite(group.market_z)
        group.loc[valid, "market_alert"] = group.loc[valid, "market_z"].abs().ge(config.market_threshold)
        scored.append(group[["date", "market", "market_z", "market_alert"]])
    return panel.merge(pd.concat(scored), on=["date", "market"], validate="many_to_one")


def detect(panel, config=CONFIG):
    """완전한 거래일 행을 가진 입력 -> 6개 기업의 일별 계산 결과.

    build_panel()로 만든 패널을 권장한다. 누락 거래일을 삭제하지 않는다.
    [요구사항] 120개 직전 거래일이 모두 유효해야 회귀하고, 과거 40일 잔차로 Z를 만든다.
    [요구사항] 부호 있는 수익률/Z를 보관하고 가격은 양방향, 거래량은 증가 방향만 탐지한다.
    """
    required = {"date", "code", "name", "market", "stock_return", "market_return", "sector_return", "volume", "peer_count"}
    if not required <= set(panel):
        raise ValueError(f"필수 입력 누락: {sorted(required-set(panel))}")
    p = panel.copy()
    p["date"] = pd.to_datetime(p.date, errors="raise")
    if p.empty or p.date.isna().any() or p.code.isna().any():
        raise ValueError("빈 입력 또는 날짜/종목 코드 결측")
    if p.date.dt.tz is not None or not p.date.eq(p.date.dt.normalize()).all():
        raise ValueError("date는 시간대 없는 거래일 날짜여야 합니다.")
    p["code"] = p.code.astype(str).str.zfill(6)
    if not p.code.str.fullmatch(r"\d{6}").all() or p.duplicated(["date", "code"]).any():
        raise ValueError("종목 코드는 6자리이고 기업·날짜는 중복될 수 없습니다.")
    if p[["name", "market"]].isna().any().any() or not p.market.isin(["KOSPI", "KOSDAQ"]).all():
        raise ValueError("기업명/상장시장 정보를 확인하세요.")
    if p.groupby("code")[["name", "market"]].nunique().gt(1).any().any():
        raise ValueError("동일 기업의 이름·상장시장이 입력 중 변경되었습니다.")
    sessions = p.date.nunique()
    if p.groupby("code").size().ne(sessions).any():
        raise ValueError("거래일 행 누락: 결측을 NaN 행으로 유지하고 시간 축을 압축하지 마세요.")
    for column in ["stock_return", "market_return", "sector_return", "volume"]:
        p[column] = pd.to_numeric(p[column], errors="raise")
        if np.isinf(p[column]).any():
            raise ValueError(f"{column}: 무한대는 입력할 수 없습니다.")
    p = p.drop(columns=[c for c in ["market_z", "market_alert"] if c in p])
    p = add_market_scores(p, config)
    parts = []
    for _, group in p.groupby("code", sort=True):
        g = group.sort_values("date").reset_index(drop=True).copy()
        excessive = exceeds_return_limit(g.stock_return, config)
        r = g.stock_return.mask(excessive)
        usable = np.isfinite(g.volume) & g.volume.gt(0) & ~excessive
        if "usable_quote" in g:
            if not g.usable_quote.isin([True, False]).all():
                raise ValueError("usable_quote는 True/False여야 합니다.")
            usable &= g.usable_quote
        # 원시 가격/거래량 문제는 당일의 모든 종목 경보를 판정 불가로 만든다.
        input_status = (g.input_status.astype(str).copy() if "input_status" in g
                        else pd.Series("OK", index=g.index))
        input_status.loc[~np.isfinite(g.volume) | g.volume.le(0)] = "MISSING_OR_ZERO_VOLUME"
        input_status.loc[excessive] = "RETURN_EXCEEDS_30PCT"
        r = r.where(input_status.eq("OK"))
        usable &= input_status.eq("OK") | input_status.eq("MISSING_PREVIOUS_QUOTE")
        columns = ["sector_pure_return", "alpha", "beta_market", "beta_sector", "market_part",
                   "sector_part", "expected_return", "price_residual"]
        for column in columns:
            g[column] = np.nan
        status = pd.Series("INSUFFICIENT_REGRESSION_HISTORY", index=g.index)
        values = np.column_stack([r, g.market_return, g.sector_return])
        for t in range(config.train_window, len(g)):
            train, today = values[t-config.train_window:t], values[t]
            if not np.isfinite(today).all():
                status.iloc[t] = "MISSING_CURRENT_INPUT"
                continue
            if not np.isfinite(train).all():
                status.iloc[t] = "INCOMPLETE_REGRESSION_WINDOW"
                continue
            # 1단계: 섹터 평균에서 해당 종목 상장시장의 영향을 제거한다.
            first = _ols(train[:, [1]], train[:, 2], config.scale_floor)
            if first is None:
                status.iloc[t] = "RANK_DEFICIENT_REGRESSION"
                continue
            a_sector, b_sector = first[0], first[1][0]
            pure_train = train[:, 2] - (a_sector + b_sector * train[:, 1])
            pure_today = today[2] - (a_sector + b_sector * today[1])
            # 2단계: 종목 수익률 = alpha + 시장 beta*시장 수익률 + 섹터 beta*순섹터 + 잔차.
            second = _ols(np.column_stack([train[:, 1], pure_train]), train[:, 0], config.scale_floor)
            if second is None:
                status.iloc[t] = "RANK_DEFICIENT_REGRESSION"
                continue
            alpha, beta = second
            market_part, sector_part = beta[0] * today[1], beta[1] * pure_today
            expected = alpha + market_part + sector_part
            g.loc[t, columns] = [pure_today, alpha, *beta, market_part, sector_part, expected, today[0]-expected]
            status.iloc[t] = "OK"
        # 과거 날짜마다 당시의 과거 자료로 생성한 잔차만 사용한다. 당일 포함 금지.
        reference = g.price_residual.shift(1).rolling(config.z_window, min_periods=config.z_window)
        price_scale = reference.std(ddof=config.std_ddof)
        g["price_z"] = (g.price_residual-reference.mean()) / price_scale.where(price_scale > config.scale_floor)
        log_volume = np.log1p(g.volume.where(usable))
        volume_reference = log_volume.shift(1).rolling(config.z_window, min_periods=config.z_window)
        volume_scale = volume_reference.std(ddof=config.std_ddof)
        g["volume_z"] = (log_volume-volume_reference.mean()) / volume_scale.where(volume_scale > config.scale_floor)
        mean_volume = g.volume.where(usable).shift(1).rolling(40, min_periods=40).mean()
        # [요구사항] 로그 거래량이 아닌 원거래량의 직전 40거래일 산술평균 대비 배율.
        g["volume_ratio_40d"] = g.volume.where(usable) / mean_volume.where(mean_volume > 0)
        status.loc[status.eq("OK") & ~np.isfinite(g.price_z)] = "INCOMPLETE_PRICE_Z_WINDOW"
        status.loc[price_scale.le(config.scale_floor) & g.price_residual.notna()] = "ZERO_PRICE_SCALE"
        status.loc[status.eq("OK") & ~np.isfinite(g.volume_z)] = "INCOMPLETE_VOLUME_Z_WINDOW"
        status.loc[status.eq("INCOMPLETE_VOLUME_Z_WINDOW") & volume_scale.le(config.scale_floor)] = "ZERO_VOLUME_SCALE"
        status.loc[~input_status.eq("OK")] = input_status.loc[~input_status.eq("OK")]
        valid = status.eq("OK") & np.isfinite(g.price_z) & np.isfinite(g.volume_z)
        # [요구사항] 판정 불가를 False/NO_ALERT로 바꾸지 않는다. CSV 빈값, JSON/DB null.
        for column in ["price_alert", "volume_alert", "both_alert"]:
            g[column] = pd.Series(pd.NA, index=g.index, dtype="boolean")
        g.loc[valid, "price_alert"] = g.loc[valid, "price_z"].abs().ge(config.price_threshold)
        g.loc[valid, "volume_alert"] = g.loc[valid, "volume_z"].ge(config.volume_threshold)
        g.loc[valid, "both_alert"] = g.loc[valid, "price_alert"] & g.loc[valid, "volume_alert"]
        g["alert_type"] = pd.Series(pd.NA, index=g.index, dtype="string")
        price = g.price_alert.fillna(False)
        volume = g.volume_alert.fillna(False)
        # 반드시 both를 먼저 분류한다. fillna(False)는 아래 마스크 계산에만 사용한다.
        g.loc[valid, "alert_type"] = np.select(
            [condition[valid].to_numpy(dtype=bool) for condition in (price & volume, price, volume)],
            ["PRICE_AND_VOLUME", "PRICE_ONLY", "VOLUME_ONLY"], default="NO_ALERT")
        g["price_direction"] = pd.Series(pd.NA, index=g.index, dtype="string")
        # 예상 대비 방향은 중심 보정된 Z의 부호가 아닌 실제 잔차의 부호다.
        g.loc[valid & price & g.price_residual.gt(0), "price_direction"] = "UP"
        g.loc[valid & price & g.price_residual.lt(0), "price_direction"] = "DOWN"
        g["decision_status"] = status
        parts.append(g[DAILY_COLUMNS])
    return pd.concat(parts, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)


def db_records(frame):
    """DB 저장용 Python 자료형으로 변환: 코드 앞자리 0 유지, 결측 -> None, 불리언 유지."""
    export = frame[DAILY_COLUMNS].copy()
    export["date"] = pd.to_datetime(export.date).dt.strftime("%Y-%m-%d")
    return json.loads(export.to_json(orient="records", double_precision=15))
