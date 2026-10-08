"""[팀 폴더 반영] 실행 위치와 무관하게 모델 폴더의 상위 저장소를 기준으로 경로를 정한다."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    project_root: Path
    model_dir: Path
    data_dir: Path
    daily_csv: Path
    anomaly_dir: Path
    manifest: Path


def get_project_paths(project_root=None):
    """기본: 저장소/FDS_regression_model/semiconductor_model/paths.py -> 저장소.

    editable 설치(pip install -e)를 전제로 한다. 별도 설치 위치에서 사용하려면
    --project-root 또는 함수 인자로 저장소 경로를 명시한다.
    """
    root = (Path(__file__).resolve().parents[2] if project_root is None
            else Path(project_root).expanduser().resolve())
    model = root / "FDS_regression_model"
    return ProjectPaths(
        project_root=root,
        model_dir=model,
        data_dir=model / "data",
        daily_csv=root / "stored_data" / "daily_results.csv",
        # 팀에서 이미 지정한 폴더명 유지. 표준 철자는 anomaly_result지만 임의로 바꾸지 않는다.
        anomaly_dir=root / "source_data" / "anormaly_result",
        # 실행 설정·삭제 대상 목록은 모델 폴더에만 저장한다. LLM 입력에 섞지 않는다.
        manifest=model / "run_config.json",
    )
