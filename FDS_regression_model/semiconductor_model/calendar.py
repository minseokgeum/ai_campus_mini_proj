"""휴장일과 시세 누락을 구분하기 위한 KRX 거래일 목록."""
import warnings
import pandas as pd


def default_request_end(now=None):
    """한국 시간 18시 이전에는 전날까지 요청한다. 당일 미완성/지연 일봉 방지용이다."""
    now = pd.Timestamp.now(tz="Asia/Seoul") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError("now에는 시간대가 있어야 합니다.")
    now = now.tz_convert("Asia/Seoul")
    day = now.normalize() if now.hour >= 18 else now.normalize() - pd.Timedelta(days=1)
    return day.tz_localize(None)


def krx_calendar(start, end):
    """원본 ZIP의 XKRX 및 확인된 휴장일 보정 정책을 유지한다.

    모델 실행 시에는 다시 생성하지 않고 수집 시 저장한 calendar.csv를 사용한다.
    지수 관측일로 거래일을 추정하지 않으므로 거래일의 지수 누락이 숨겨지지 않는다.
    """
    try:
        import pandas_market_calendars as mcal
    except ImportError as exc:
        raise RuntimeError('수집 의존성을 설치하세요: python -m pip install -e ".[data]"') from exc
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=r".*break_start.*discontinued.*", category=UserWarning)
        cal = mcal.get_calendar("XKRX")
        # 일봉에 사용하지 않는 과거 점심 휴장 구간에 관한 경고를 제거한다.
        for field in ("break_start", "break_end"):
            if field in cal.regular_market_times:
                cal.remove_time(field)
        schedule = cal.schedule(start_date=start, end_date=end,
                                market_times=["market_open", "market_close"])
    dates = pd.DatetimeIndex(schedule.index).tz_localize(None).normalize()
    # 첨부 코드의 휴장일 보정. 공급 자료와 충돌하면 데이터 검증에서 중단한다.
    closures = pd.to_datetime(["2026-06-03", "2026-07-17"])
    keep = ~dates.isin(closures)
    result = pd.DataFrame({"date": dates[keep],
                           "market_close": pd.to_datetime(schedule.loc[keep, "market_close"], utc=True).to_numpy()})
    if result.empty:
        raise ValueError("요청 범위에 한국 거래일이 없습니다.")
    return result.reset_index(drop=True)
