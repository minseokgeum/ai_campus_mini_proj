"""저장된 사전 데이터 CSV로 2025년~현재 결과를 생성하는 실행 명령."""
import argparse
import hashlib
from pathlib import Path
import pandas as pd
from .calendar import default_request_end
from .config import CONFIG, ANALYSIS_START
from .core import detect
from .data import build_panel, read_inputs
from .output import write_results
from .paths import get_project_paths


def run_analysis(data_dir=None, project_root=None, start=ANALYSIS_START, end=None):
    """팀 서비스에서 직접 호출 가능하다. 반환 DataFrame은 DB 저장에도 사용할 수 있다."""
    safe_end = default_request_end()
    requested_end = safe_end if end is None else pd.Timestamp(end)
    if requested_end > safe_end:
        raise ValueError("아직 확정되지 않은 일봉 또는 미래 날짜를 분석할 수 없습니다.")
    if pd.Timestamp(start) < pd.Timestamp(ANALYSIS_START) or pd.Timestamp(start) > requested_end:
        raise ValueError("분석 시작은 2025-01-01 이후이고 종료일 이하여야 합니다.")
    paths = get_project_paths(project_root)
    root = paths.data_dir if data_dir is None else Path(data_dir).expanduser().resolve()
    stocks, markets, calendar, universe = read_inputs(root, requested_end)
    if end is not None and requested_end > calendar.date.max():
        print(f"요청 종료일: {requested_end.date()} / 보관된 마지막 거래일: {calendar.date.max().date()}")
    panel = build_panel(stocks, markets, calendar, universe)
    # 준비 자료를 먼저 제거하면 2025년 초 회귀/Z를 계산할 수 없다. 계산 후 출력만 자른다.
    result = detect(panel, CONFIG)
    result = result.loc[result.date.between(pd.Timestamp(start), requested_end)].reset_index(drop=True)
    if result.empty:
        raise ValueError("분석 기간에 데이터가 없습니다. data 폴더를 먼저 수집/갱신하세요.")
    names = ["stocks.csv", "markets.csv", "calendar.csv", "universe.csv"]
    provenance = {"sha256": {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names},
                  "data_first_session": str(calendar.date.min().date()),
                  "data_last_session": str(calendar.date.max().date()),
                  "requested_analysis_start": str(pd.Timestamp(start).date()),
                  "requested_analysis_end": str(requested_end.date())}
    manifest = write_results(result, paths.project_root, CONFIG, provenance)
    print(f"분석: {result.date.min().date()} ~ {result.date.max().date()} / {len(result):,}행")
    print(f"판정 불가 {result.decision_status.ne('OK').sum():,}행 / 종목 경보 JSON {manifest['stock_alert_json_count']:,}개")
    print(f"전체 결과 CSV: {paths.daily_csv}")
    print(f"경보 JSON 폴더: {paths.anomaly_dir}")
    return result


def main():
    parser = argparse.ArgumentParser(description="120일 회귀·40일 Z, 가격/거래량 2.5 고정 모델")
    parser.add_argument("--data-dir", help="수집한 CSV 폴더. 기본: FDS_regression_model/data")
    parser.add_argument("--project-root", help="팀 저장소 최상위 폴더. 생략하면 코드 위치로 결정")
    parser.add_argument("--start", default=ANALYSIS_START, help="계산 후 출력 시작일")
    parser.add_argument("--end", help="계산/출력 종료 상한. 생략 시 보관된 최근 확정 자료까지")
    args = parser.parse_args()
    try:
        run_analysis(args.data_dir, args.project_root, args.start, args.end)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, f"입력/설정 오류: {exc}\n")


if __name__ == "__main__":
    main()
