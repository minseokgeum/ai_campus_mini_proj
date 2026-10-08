"""팀원용 사전 데이터 수집 명령. FinanceDataReader -> 재사용 가능한 CSV 4개."""
import argparse
import contextlib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import socket
import tempfile
import time
import pandas as pd
from .calendar import default_request_end, krx_calendar
from .config import DATA_START, MARKET_SYMBOLS
from .data import build_panel, validate_calendar
from .universe import get_universe
from .paths import get_project_paths


@contextlib.contextmanager
def network_timeout(seconds=20):
    """수집 CLI의 순차 요청에 타임아웃 적용. 모델 계산 모듈에는 적용하지 않는다."""
    import requests
    original = requests.sessions.Session.request
    previous_socket_timeout = socket.getdefaulttimeout()

    def bounded(self, method, url, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = seconds
        return original(self, method, url, **kwargs)

    requests.sessions.Session.request = bounded
    socket.setdefaulttimeout(seconds)
    try:
        yield
    finally:
        requests.sessions.Session.request = original
        socket.setdefaulttimeout(previous_socket_timeout)


def fetch_daily(symbol, start, end, reader=None):
    """한 종목/지수를 조회한다. 종료일을 하루 넓혀 요청 후 직접 자른다."""
    if reader is None:
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise RuntimeError('python -m pip install -e ".[data]"로 수집 의존성을 설치하세요.') from exc
        reader = fdr.DataReader
    error = None
    for attempt in range(2):
        try:
            with network_timeout():
                raw = reader(symbol, str(pd.Timestamp(start).date()),
                             str((pd.Timestamp(end) + pd.Timedelta(days=1)).date()))
            if raw is None or raw.empty or "Close" not in raw:
                raise ValueError("빈 시세 또는 Close 누락")
            raw = raw.copy()
            index = pd.DatetimeIndex(pd.to_datetime(raw.index))
            if index.tz is not None:
                index = index.tz_localize(None)  # 공급자가 붙인 현지 일자 라벨 유지
            raw.index = index.normalize()
            raw.index.name = "date"
            if raw.index.has_duplicates:
                raise ValueError("중복 거래일")
            raw = raw.sort_index().loc[pd.Timestamp(start):pd.Timestamp(end)]
            if raw.empty:
                raise ValueError("요청 구간에 자료 없음")
            return raw
        except Exception as exc:
            error = exc
            if attempt == 0:
                time.sleep(0.5)
    raise RuntimeError(f"{symbol} 수집 실패: {error}") from error


def check_listing(universe):
    """선택 점검: 현재 KRX 상장 목록을 고정 기업 코드·시장과 대조한다."""
    import FinanceDataReader as fdr
    with network_timeout():
        listing = fdr.StockListing("KRX")
    listing = listing.copy()
    listing["Code"] = listing.Code.astype(str).str.strip().str.zfill(6)
    listing["Market"] = listing.Market.astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True).replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    check = universe.merge(listing[["Code", "Name", "Market"]], left_on="code", right_on="Code",
                           how="left", validate="one_to_one")
    if (check.name.ne(check.Name) | check.market.ne(check.Market)).any():
        raise ValueError("고정 기업 목록과 현재 상장 목록이 다릅니다. 기업명·시장 변경 여부를 확인하세요.")


def download_inputs(output_dir=None, start=DATA_START, end=None, verify_listing=False,
                    calendar=None, reader=None, now=None, project_root=None):
    """[요구사항] 2024년 준비 자료부터 확보하여 2025년~현재 분석에 사용한다.

    stocks.csv/markets.csv는 원시 관측만 저장한다. 결측 거래일 행 추가와 30% 초과
    필터는 build_panel에서 수행한다. 달력의 휴장일과 원시 시세가 충돌하면 중단한다.
    """
    requested_end = default_request_end(now) if end is None else pd.Timestamp(end)
    if requested_end > default_request_end(now):
        raise ValueError("확정 일봉 수집 상한을 넘었습니다. 한국 시간 18시 전에는 전날까지 요청하세요.")
    if pd.Timestamp(start) > requested_end:
        raise ValueError("수집 시작일이 종료일보다 늦습니다.")
    custom_calendar = calendar is not None
    calendar = krx_calendar(start, requested_end) if calendar is None else validate_calendar(calendar)
    calendar = validate_calendar(calendar.loc[calendar.date.between(pd.Timestamp(start), requested_end)])
    end = calendar.date.max()
    universe = get_universe()
    if verify_listing:
        check_listing(universe)
    stocks, markets = [], []
    for index, row in enumerate(universe.itertuples(index=False), start=1):
        print(f"[{index}/37] {row.code} {row.name} 수집", flush=True)
        raw = fetch_daily(f"NAVER:{row.code}", start, end, reader)
        if "Volume" not in raw:
            raise ValueError(f"{row.code}: Volume 누락")
        part = raw[["Close", "Volume"]].rename(columns={"Close": "close", "Volume": "volume"}).reset_index()
        part.insert(1, "code", row.code)
        stocks.append(part)
    for market, symbol in MARKET_SYMBOLS.items():
        print(f"{market} 지수 수집", flush=True)
        raw = fetch_daily(symbol, start, end, reader)
        part = raw[["Close"]].rename(columns={"Close": "close"}).reset_index()
        part.insert(1, "market", market)
        markets.append(part)
    stocks, markets = pd.concat(stocks, ignore_index=True), pd.concat(markets, ignore_index=True)
    # 저장 전 검증: 휴장일 충돌/거래일 지수 누락/중복이면 CSV 세트를 완성하지 않는다.
    build_panel(stocks, markets, calendar, universe)
    root = (get_project_paths(project_root).data_dir if output_dir is None
            else Path(output_dir).expanduser().resolve())
    if root.is_symlink():
        raise ValueError("수집 폴더에 심볼릭 링크를 사용할 수 없습니다.")
    root.mkdir(parents=True, exist_ok=True)
    names = ["stocks.csv", "markets.csv", "calendar.csv", "universe.csv", "data_manifest.json"]
    old_manifest = root / "data_manifest.json"
    if old_manifest.exists():
        if json.loads(old_manifest.read_text(encoding="utf-8")).get("generated_by") != "semiconductor_model.data.v2":
            raise ValueError("다른 프로그램의 데이터 폴더입니다.")
    elif any((root / name).exists() for name in names):
        raise ValueError("기존 CSV를 덮어쓰지 않습니다. 새 수집 폴더를 지정하세요.")
    if any((root / name).is_symlink() for name in names):
        raise ValueError("수집 파일 경로에 심볼릭 링크가 있습니다.")
    stage = Path(tempfile.mkdtemp(prefix=".fds_download_", dir=root))
    try:
        for name, frame in [("stocks.csv", stocks), ("markets.csv", markets),
                            ("calendar.csv", calendar), ("universe.csv", universe)]:
            frame.to_csv(stage / name, index=False, encoding="utf-8-sig")
        versions = {}
        for package in ["finance-datareader", "pandas_market_calendars", "pandas", "numpy"]:
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = "unavailable"
        manifest = {"generated_by": "semiconductor_model.data.v2", "requested_start": str(pd.Timestamp(start).date()),
                    "requested_end": str(requested_end.date()), "last_session": str(end.date()),
                    "collected_at": pd.Timestamp.now(tz="UTC").isoformat(),
                    "stock_source": "FDR NAVER Close/Volume", "market_symbols": MARKET_SYMBOLS,
                    "listing_checked": verify_listing, "packages": versions,
                    "calendar_source": "provided_calendar" if custom_calendar else "XKRX_with_project_closures",
                    "calendar_closure_overrides": [] if custom_calendar else ["2026-06-03", "2026-07-17"],
                    "historical_publication_times_verified": False,
                    "sha256": {name: hashlib.sha256((stage / name).read_bytes()).hexdigest() for name in names[:-1]}}
        (stage / "data_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for name in names:
            (stage / name).replace(root / name)
    finally:
        shutil.rmtree(stage)
    print(f"수집 완료: {root.resolve()} / 마지막 거래일 {end.date()}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="37개 기업·두 지수·거래일 목록을 CSV로 수집")
    parser.add_argument("--output", help="원시 CSV 수집 폴더. 기본: FDS_regression_model/data")
    parser.add_argument("--project-root", help="팀 저장소 최상위 폴더. 생략하면 코드 위치로 결정")
    parser.add_argument("--start", default=DATA_START)
    parser.add_argument("--end", help="생략 시 한국 시간 기준 최근 확정 일봉까지")
    parser.add_argument("--check-listing", action="store_true", help="현재 KRX 이름·시장 교차 확인")
    parser.add_argument("--calendar-csv", help="검증한 거래일 CSV를 사용하려는 경우 지정")
    args = parser.parse_args()
    calendar = validate_calendar(pd.read_csv(args.calendar_csv)) if args.calendar_csv else None
    download_inputs(args.output, args.start, args.end, args.check_listing, calendar,
                    project_root=args.project_root)


if __name__ == "__main__":
    main()
