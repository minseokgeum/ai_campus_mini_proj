# 팀 저장소 연동 변경 사항

## 파일 배치와 실제 저장 경로

ZIP 안의 `FDS_regression_model/` 폴더를 팀 저장소 최상위에 복사합니다. 기존 코드에 덮어쓴 경우 아래에서 제거했다고 적은 `.gitignore`와 중첩 `.github/workflows/tests.yml`은 따로 삭제하세요. ZIP에 파일이 없는 것만으로 기존 파일이 자동 삭제되지는 않습니다. 기존 원시 데이터는 보존하세요.

| 저장소 기준 경로 | 용도 |
|---|---|
| `FDS_regression_model/` | 모델 소스 코드 |
| `FDS_regression_model/data/` | 회귀에 필요한 원시 시세 CSV. 기존 위치 유지 |
| **`stored_data/daily_results.csv`** | 모든 분석 날짜의 판정 결과 |
| **`source_data/anormaly_result/날짜_기업명.json`** | 종목 가격 OR 거래량 경보의 LLM 입력 |
| `FDS_regression_model/run_config.json` | 모델 공통 설정·입력 해시·생성 파일 목록. 삭제 기능에서 사용 |
| `.github/workflows/fds-model-tests.yml` | 저장소 최상위에서 실행되는 모델 테스트 워크플로 |

`stored_data/dart/`, `stored_data/news/`, `source_data/source_news/`, `result/`는 이 모델의 저장·삭제 대상에 포함하지 않습니다.

## 수정한 코드

| 파일 | 변경 사항 |
|---|---|
| `semiconductor_model/paths.py` | 추가. `Path(__file__).resolve().parents[2]`로 기본 저장소 경로를 계산하고 모든 경로를 정의 |
| `semiconductor_model/output.py` | 전체 CSV·경보 JSON을 각각 요청 경로에 저장. 이전 경보 JSON 정리도 해당 위치에서만 수행 |
| `semiconductor_model/__main__.py` | `outputs` 기본값을 없애고 공통 경로를 사용. 분석 명령은 `--output` 대신 필요할 때 `--project-root` 사용 |
| `semiconductor_model/download_data.py` | 기본 원시 데이터 위치를 `FDS_regression_model/data/`로 고정. 터미널 위치에 따른 폴더 생성 차이 제거 |
| `semiconductor_model/cleanup.py` | 두 위치에 나뉜 생성 파일과 실행 기록만 삭제. 팀 폴더 자체와 다른 자료는 보존 |
| `semiconductor_model/__init__.py` | 서비스에서도 `get_project_paths()`를 가져올 수 있게 공개 |
| `tests/test_model.py` | 다른 터미널 위치에서 동일 경로 사용·팀 자료 보존 검사 추가 |
| `pyproject.toml` | 패키지 버전 0.2.1로 갱신 |
| `README.md` | 새 실행 명령과 저장 위치로 갱신 |

회귀 수식·계수 계산·Z·임계값·분석 기간·출력 컬럼과 JSON 내부 형식은 변경하지 않았습니다.

## 경로를 이렇게 계산하는 이유

단순히 `../stored_data`를 쓰면 터미널을 어느 폴더에서 열었는지에 따라 다른 곳에 저장될 수 있습니다. 새 코드는 **설치된 모델 소스의 위치**를 기준으로 저장소를 찾습니다.

```python
# FDS_regression_model/semiconductor_model/paths.py 기준
root = Path(__file__).resolve().parents[2]
daily_csv = root / "stored_data" / "daily_results.csv"
anomaly_dir = root / "source_data" / "anormaly_result"
```

`pip install -e`로 현재 저장소의 모델을 설치해야 합니다. 다운로드 폴더의 예전 모델이 설치되어 있다면 새 위치에서 다시 설치하여 참조 경로를 갱신하세요. 일반 설치나 다른 서비스 폴더 배치가 필요하면 `--project-root`로 저장소 경로를 명시할 수 있습니다.

`anormaly_result`는 표준 철자 `anomaly_result`와 다르지만, **이미 지정된 팀 경로와 호환되도록 이번 수정에서는 요청한 `anormaly_result`를 유지**했습니다. 나중에 팀 전체가 이름을 바꾸기로 하면 실제 폴더명, `paths.py`의 폴더명, 이를 읽는 LLM 코드 경로를 함께 바꿔야 합니다.

## 기존 .gitignore 적용

팀 저장소 최상위 `.gitignore`를 그대로 사용합니다. 모델 내부 `.gitignore`는 중복이므로 이번 ZIP에서 제거했습니다. 최상위 규칙은 하위 모델 폴더에도 적용됩니다.

사용자가 제시한 규칙에서 `*.csv`, `*.json`은 모델 결과를 이미 제외합니다. 추가할 이유는 다음과 같습니다.

- `pip install -e`가 생성하는 `*.egg-info/` 제외 규칙이 필요합니다.
- `result/results.txt`는 기존 `*.json`, `*.csv` 규칙에 걸리지 않습니다. 뉴스·공시의 XML/TXT 등도 함께 제외하도록 데이터/결과 폴더를 지정합니다.
- Git은 빈 폴더를 저장하지 않으므로 팀에서 쓰는 `.gitkeep`은 예외로 남깁니다.
- `db_schema.sql`을 팀과 공유하려면 기존 `*.sql` 규칙에 예외가 필요합니다.

**팀 저장소 최상위 `.gitignore` 맨 아래에 아래 내용을 추가합니다.** 기존 파일 전체를 바꾸지 않습니다.

```gitignore
# FDS 모델 설치 정보와 원시 데이터
*.egg-info/
/FDS_regression_model/data/
/FDS_regression_model/outputs/

# 생성 자료 제외. 하위 폴더의 .gitkeep은 공유 가능
/stored_data/**
!/stored_data/**/
!/stored_data/**/.gitkeep
/source_data/**
!/source_data/**/
!/source_data/**/.gitkeep
/result/**
!/result/**/
!/result/**/.gitkeep

# 팀에서 공유하는 DB 스키마
!/FDS_regression_model/db_schema.sql
```

`.gitignore`는 이미 Git에서 추적 중인 파일을 자동으로 추적 해제하지 않습니다. 이미 커밋한 결과 파일이 있다면 해당 파일만 지정해서 `git rm --cached "파일 경로"`로 추적 해제합니다. 이 옵션은 로컬 파일을 보존합니다. 폴더 전체를 무작정 삭제하거나 전체 저장소를 추적 해제할 필요는 없습니다.

이미 데이터 폴더에서 JSON/CSV 이외의 템플릿을 팀과 공유하고 있다면 필요한 정확한 파일에만 예외를 추가하세요. 이 ZIP은 팀 저장소의 `.gitignore`와 기존 추적 상태를 직접 변경하지 않습니다.

## 실행 순서

VS Code에서 팀 저장소 최상위 폴더를 열고 실행합니다.

```bash
conda activate aicam
python -m pip install -e "./FDS_regression_model[data]"
python -m semiconductor_model.download_data
python -m semiconductor_model
```

이전 실행의 원시 CSV 세트가 `FDS_regression_model/data/`에 있으면 데이터 수집 명령은 생략할 수 있습니다. 다른 위치에 있다면 다음처럼 지정합니다.

```bash
python -m semiconductor_model --data-dir "기존 CSV 폴더 경로"
```

결과는 재실행 시 새 저장 위치에 생성합니다. 예전 `outputs/` 결과는 자동으로 이동하거나 삭제하지 않습니다. 새 위치에 이미 있는 파일인데 현재 실행 기록에 없는 경우에도 임의로 덮어쓰지 않고 오류로 알려줍니다. 기존 파일을 확인·백업한 뒤 적용하세요.

생성 결과 목록 확인 / 실제 삭제:

```bash
python -m semiconductor_model.cleanup
python -m semiconductor_model.cleanup --apply
```

모델 폴더 안의 `run_config.json`이 정리할 파일 목록을 관리합니다. 팀 자료가 있는 `stored_data/`나 `source_data/` 전체를 삭제하지 않습니다.

## GitHub 검사 설정

예전 ZIP의 `.github/workflows/tests.yml`을 모델 하위 폴더에 넣으면 저장소 최상위 워크플로 위치와 맞지 않습니다. 이번 ZIP에서는 **저장소 최상위 `.github/workflows/fds-model-tests.yml`로 이동**하고 작업 위치를 `FDS_regression_model`로 설정했습니다. 기존 팀 워크플로 파일은 그대로 두고 이 파일만 병합합니다.

로컬 검사는 저장소 최상위에서 다음 명령으로 실행합니다.

```bash
python -m unittest discover -s FDS_regression_model/tests -v
```
