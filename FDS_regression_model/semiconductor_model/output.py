"""daily_results.csv와 날짜_기업명.json 저장. 생성 파일 목록으로 재실행 잔여 파일을 정리한다."""
import json
import re
import shutil
import tempfile
from pathlib import Path
from .config import CONFIG, DAILY_COLUMNS
from .core import db_records
from .paths import get_project_paths

OWNER = "semiconductor_model.team_results.v1"


def alert_payload(row):
    """[요구사항] LLM에 종목별 True/False 대신 alert_type을 전달한다."""
    return {
        "date": row["date"], "code": row["code"], "name": row["name"], "market": row["market"],
        "anomaly": {
            "alert_type": row["alert_type"], "direction": row["price_direction"],
            "actual_return": row["stock_return"], "expected_return": row["expected_return"],
            "abnormal_return": row["price_residual"], "price_zscore": row["price_z"],
            "volume_zscore": row["volume_z"], "volume_ratio": row["volume_ratio_40d"],
            "regression": {"market_beta": row["beta_market"], "sector_beta": row["beta_sector"],
                           "market_contribution": row["market_part"], "sector_contribution": row["sector_part"]},
            "market_z": row["market_z"], "market_alert": row["market_alert"],
        },
    }


def _safe_path(root, target):
    """공유 폴더의 중간 경로까지 확인해 심볼릭 링크를 통한 외부 접근을 막는다."""
    relative = target.relative_to(root)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"결과 파일 경로에 심볼릭 링크가 있습니다: {current}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("결과 파일 경로가 프로젝트 밖을 가리킵니다.")


def owned_files(project_root=None):
    """우리 생성 목록의 CSV·종목 경보 JSON만 반환한다. 뉴스/공시/LLM 결과는 대상이 아니다."""
    paths = get_project_paths(project_root)
    root, manifest = paths.project_root, paths.manifest
    _safe_path(root, manifest)
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("generated_by") != OWNER:
        raise ValueError("다른 형식의 실행 기록입니다. 새 코드의 run_config.json인지 확인하세요.")
    files = []
    csv_relative = paths.daily_csv.relative_to(root).as_posix()
    json_relative = paths.anomaly_dir.relative_to(root)
    for value in data.get("generated_files", []):
        rel = Path(value)
        allowed = value == csv_relative or (
            rel.parent == json_relative and re.fullmatch(r"\d{4}-\d{2}-\d{2}_.+\.json", rel.name))
        target = root / rel
        if not allowed or rel.is_absolute() or ".." in rel.parts:
            raise ValueError("결과 파일 목록에 허용되지 않은 경로가 있습니다.")
        _safe_path(root, target)
        if target.exists() and not target.is_file():
            raise ValueError("결과 파일 대신 디렉터리가 있습니다.")
        files.append(target)
    return files + [manifest]


def write_results(frame, project_root=None, config=CONFIG, provenance=None):
    """[요구사항] CSV는 전 행, JSON은 유효한 가격 OR 거래량 경보만 생성한다.

    시장 경보만 있는 날은 CSV에 기록하지만 JSON 생성 조건에는 넣지 않는다.
    재실행 후 더 이상 경보가 아닌 날짜의 이전 JSON은 생성 목록을 따라 제거한다.
    """
    paths = get_project_paths(project_root)
    root = paths.project_root
    for target in (paths.daily_csv, paths.anomaly_dir, paths.manifest):
        _safe_path(root, target)
    previous = owned_files(root)
    paths.model_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".fds_stage_", dir=paths.model_dir))
    try:
        csv_relative = paths.daily_csv.relative_to(root).as_posix()
        json_relative = paths.anomaly_dir.relative_to(root).as_posix()
        (stage / csv_relative).parent.mkdir(parents=True)
        (stage / json_relative).mkdir(parents=True)
        export = frame[DAILY_COLUMNS].copy()
        export["date"] = export.date.dt.strftime("%Y-%m-%d")
        export.to_csv(stage / csv_relative, index=False, encoding="utf-8-sig", na_rep="")
        files = [csv_relative]
        rows = db_records(frame)
        for row in rows:
            if row["decision_status"] != "OK" or not (row["price_alert"] or row["volume_alert"]):
                continue
            # 고정 기업명도 Windows에서 안전한 파일명인지 확인한다.
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", row["name"]).rstrip(" .")
            filename = f"{json_relative}/{row['date']}_{name}.json"
            if filename in files:
                raise ValueError(f"JSON 파일명 충돌: {filename}")
            (stage / filename).write_text(json.dumps(alert_payload(row), ensure_ascii=False, indent=2,
                                                     allow_nan=False) + "\n", encoding="utf-8")
            files.append(filename)
        manifest = {
            "generated_by": OWNER, "model": config.to_dict(), "return_unit": "decimal (0.01 = 1%)",
            "timezone": "Asia/Seoul", "analysis_start": rows[0]["date"] if rows else None,
            "analysis_end": rows[-1]["date"] if rows else None,
            "rows": len(rows), "stock_alert_json_count": len(files)-1,
            "generated_files": files, "inputs": provenance or {},
        }
        (stage / "run_config.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                                          allow_nan=False) + "\n", encoding="utf-8")
        previous_set = {path.resolve() for path in previous}
        for filename in files:
            target = root / filename
            _safe_path(root, target)
            if target.exists() and target.resolve() not in previous_set:
                raise ValueError(f"이 프로그램이 생성하지 않은 파일은 덮어쓰지 않습니다: {target}")
        for filename in files:
            target = root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            (stage / filename).replace(target)
        new_files = {root / filename for filename in files}
        for old in previous:
            if old.name != "run_config.json" and old not in new_files and old.exists():
                old.unlink()
        (stage / "run_config.json").replace(paths.manifest)
        paths.anomaly_dir.mkdir(parents=True, exist_ok=True)
    finally:
        shutil.rmtree(stage)
    return manifest
