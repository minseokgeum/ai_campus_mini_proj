# FDS 반도체 이상거래 탐지 모델

첨부 ZIP의 시장·섹터 2단계 OLS와 일반 Z 계산을 운영용 코드로 정리했습니다. 사전 데이터 수집과 모델 실행을 분리했으며, 모델 실행은 저장된 CSV만 읽습니다. 분석 대상은 삼성전자·SK하이닉스·DB하이텍·한미반도체·원익IPS·주성엔지니어링입니다.

## 1. 팀 저장소에 배치하고 실행

ZIP 안의 `FDS_regression_model` 폴더를 **팀 저장소 최상위**에 놓습니다. 이 폴더와 `stored_data`, `source_data`, `result`는 같은 높이에 있어야 합니다. ZIP의 `.github/workflows/fds-model-tests.yml`도 저장소 최상위 `.github/workflows/`에 병합합니다. 기존 팀 `.gitignore`는 유지합니다. 자세한 변경 목록과 추가할 규칙은 `INTEGRATION.md`에 있습니다.

VS Code에서 **팀 저장소 최상위 폴더**를 열고 터미널에서 실행합니다. Python 3.10 이상이 필요합니다.

```bash
conda activate aicam
python -m pip install -e "./FDS_regression_model[data]"
python -m semiconductor_model.download_data
python -m semiconductor_model
```

모델 폴더 안에서 설치한다면 설치 명령만 `python -m pip install -e ".[data]"`로 바꿉니다. 모델 폴더를 옮긴 뒤에는 새 위치에서 설치 명령을 다시 실행해 이전 설치 경로를 갱신하세요.

1. 설치: 계산 및 데이터 수집 라이브러리를 설치합니다.
2. 수집: **2024-01-01부터 최근 확정 거래일까지** 원시 CSV를 `FDS_regression_model/data/`에 저장합니다.
3. 분석: 준비 구간을 포함해 계산한 뒤 **2025-01-01 이후** 전체 결과를 `stored_data/daily_results.csv`에, 종목 OR 경보 JSON을 `source_data/anormaly_result/`에 저장합니다.

출력 경로는 터미널의 현재 위치가 아니라 **설치한 코드의 위치**로 결정합니다. 설치 후 저장소 최상위·모델 폴더·다른 작업 폴더에서 실행해도 같은 저장소에 저장됩니다. 다른 저장소를 명시하려면 수집·분석·삭제 명령에 `--project-root "팀 저장소 경로"`를 붙입니다. 루트와 출력 경로를 한 곳에서 관리하는 파일은 `semiconductor_model/paths.py`입니다.

수집에는 인터넷 연결이 필요합니다. 이미 받은 CSV 세트가 `FDS_regression_model/data/`에 있다면 수집은 생략하고 분석 명령만 실행할 수 있습니다. 다른 위치의 CSV는 `python -m semiconductor_model --data-dir "CSV 폴더 경로"`로 지정합니다. 명시적으로 전달한 상대 경로는 터미널 현재 위치 기준입니다.

종료일을 고정하려면 다음과 같이 실행합니다.

```bash
python -m semiconductor_model.download_data --end 2026-10-07
python -m semiconductor_model --end 2026-10-07
```

기본 수집 종료 상한은 **한국 시간 18시 전이면 전날, 18시 이후면 당일**입니다. 실제 마지막 날짜는 거래일 달력으로 정합니다. 18시는 수집용 보수적 대기 기준이며 공급자의 갱신 완료를 보증하는 시각은 아닙니다. 거래일 지수가 누락되면 중단하므로, 공급 자료를 확인하고 갱신 후 재실행하세요.

모델은 데이터 폴더에 있는 마지막 날짜까지만 분석합니다. 최신 날짜를 추가하려면 수집 명령을 먼저 다시 실행하세요. 현재 구현은 구간 전체를 다시 수집합니다. 분석·삭제 명령의 예전 `--output` 옵션은 제거했습니다. 수집 명령의 `--output`은 원시 데이터 저장 위치를 따로 지정할 때만 사용합니다.

## 2. 코드 파일

| 파일 | 역할 |
|---|---|
| `semiconductor_model/config.py` | 확정 설정·CSV 컬럼 순서 |
| `semiconductor_model/paths.py` | 코드 위치 기준 팀 저장소·CSV·JSON·사전 데이터 경로 |
| `semiconductor_model/universe.py` | 고정 35개 peer·6개 분석 대상과 종목 코드 |
| `semiconductor_model/download_data.py` | FinanceDataReader로 사전 데이터를 CSV로 수집 |
| `semiconductor_model/calendar.py` | KRX 거래일 달력과 한국 시간 기준 수집 종료일 |
| `semiconductor_model/data.py` | 원자료 검증·결측 처리·leave-one-out 섹터 평균 |
| `semiconductor_model/core.py` | 회귀·가격/거래량 Z·시장 Z·경보 판정 |
| `semiconductor_model/output.py` | 전체 CSV·경보별 JSON·실행 설정 저장 |
| `semiconductor_model/__main__.py` | CSV 읽기부터 결과 저장까지 실행 |
| `semiconductor_model/cleanup.py` | 생성 결과물 삭제 목록 확인·삭제 |
| `db_schema.sql` | daily_results용 MySQL 테이블 예시 |
| `tests/test_model.py` | 계산·전처리·CSV/JSON 계약 검사 |

연구 노트북, SOX 비교, 조합 탐색, 예제 시세·생성 결과물은 포함하지 않았습니다. 요구사항에 해당하는 위치에는 `[요구사항]` 주석을 붙였습니다. 테스트에서 생성한 CSV는 임시 폴더와 함께 자동 삭제됩니다.

## 3. 고정 설정과 계산식

| 항목 | 적용값 |
|---|---|
| 분석 기간 | 2025년부터 보관된 최근 확정 자료까지 |
| 수집 시작일 | 2024-01-01 |
| 회귀 구간 | 당일 제외 직전 **120거래일** |
| 가격·거래량 Z 구간 | 당일 제외 직전 **40거래일** |
| 가격 경보 | `abs(price_z) >= 2.5` |
| 거래량 경보 | `volume_z >= 2.5` — 증가 방향만 |
| 시장 Z 구간·경보 | 당일 제외 직전 **120거래일**, `abs(market_z) >= 3.0` |
| 표준편차 | 표본 표준편차, `ddof=1` |
| 30% 필터 | `abs(stock_return) > 0.30`이면 판정 불가 |
| 최종 종목 경보 | 가격·거래량 점수가 모두 유효할 때 가격 OR 거래량 |

모든 수익률과 설명분은 **소수 단위**입니다. `0.01`은 1%입니다. 일반 Z를 사용하며 SOX는 포함하지 않습니다. 계산 설정은 `ModelConfig`에서 위 조합으로 고정합니다.

**섹터 수익률:** 지정한 35개 기업의 유효 일간 수익률을 동일가중 평균합니다. KOSPI·KOSDAQ을 함께 사용하며, 분석 기업이 35개 안에 있을 때만 자신을 제외합니다. 삼성전자·원익IPS는 이 35개에 없으므로 최대 35개, 나머지 네 대상은 최대 34개입니다. 원본 코드의 90% 유효 peer 기준을 유지하여 각각 최소 32개·31개가 필요합니다. 실제 참여 수를 `peer_count`에 저장합니다.

**시장 수익률:** 해당 기업 상장시장의 KOSPI 또는 KOSDAQ 지수 수익률입니다. 대형주의 지수 내 자기 몫을 제외하는 조정은 적용하지 않습니다.

**회귀:** 날짜 t마다 t−120부터 t−1까지 두 단계를 다시 추정합니다.

1. 섹터 수익률을 시장 수익률에 회귀합니다. 이 식의 절편·시장 설명분을 뺀 값이 `sector_pure_return`입니다. 현재 날짜의 순섹터 값도 과거 120일로 추정한 동일 계수로 계산합니다.
2. 종목 수익률을 시장 수익률과 순섹터 수익률에 회귀합니다.

```text
sector_pure_return = sector_return − (섹터회귀 절편 + 섹터회귀 시장계수 × market_return)
market_part        = beta_market × market_return
sector_part        = beta_sector × sector_pure_return
expected_return    = alpha + market_part + sector_part
price_residual     = stock_return − expected_return
```

`expected_return`은 당일 시장·섹터 움직임을 반영한 조건부 기대 수익률입니다. 전날 시점에서 다음 날 종목 수익률을 예측한 값으로 해석하지 않습니다.

**Z 점수와 거래량 배율:**

```text
price_z = (오늘 잔차 − 직전 40거래일 잔차 평균) / 해당 잔차 표준편차
volume_z = (log(1+오늘 거래량) − 직전 40거래일 log(1+거래량) 평균) / 해당 로그 거래량 표준편차
volume_ratio_40d = 오늘 거래량 / 직전 40거래일 원거래량 산술평균
market_z = (오늘 시장 수익률 − 직전 120거래일 시장 수익률 평균) / 해당 시장 수익률 표준편차
```

가격 Z의 과거 잔차는 **각 과거 날짜에 그때의 과거 120일로 계산한 잔차**입니다. 오늘 계수로 과거 잔차를 일괄 재계산하지 않습니다. 거래량은 회귀식이 아닙니다.

`market_z`는 **하루 시장 수익률이 최근 분포에서 얼마나 벗어났는지** 나타내며, 표준편차 자체의 변화율은 아닙니다. 부호를 보관하고 경보 판정에만 절댓값을 씁니다. `market_alert=True`는 시장 급변 참고 정보이며, 개별 종목 경보가 시장 때문에 발생했다는 인과 판정이나 자동 경보 해제 조건이 아닙니다.

## 4. 사전 데이터와 전처리

수집 폴더에는 다음 파일이 생성됩니다.

| 파일 | 내용 |
|---|---|
| `stocks.csv` | `date, code, close, volume`: peer·대상 합집합 37개 기업 |
| `markets.csv` | `date, market, close`: KOSPI·KOSDAQ 지수 |
| `calendar.csv` | `date, market_close`: 거래일과 UTC로 표시한 장 마감 시각 |
| `universe.csv` | `code, name, market, is_peer, is_target` |
| `data_manifest.json` | 수집 범위·출처·패키지 버전·CSV 해시 |

`date`는 한국 거래일의 `YYYY-MM-DD` 라벨입니다. UTC 날짜로 변환해서 기업 시세와 붙이지 않습니다. `market_close`는 달력 기록용이고 모델은 `date`로 결합합니다.

2024년 자료는 2025년 초 회귀와 Z를 계산하기 위한 준비 자료입니다. 120일 회귀, 40일 잔차, 최초 일간 수익률용 전일 종가가 필요하므로 준비 자료를 **분석 전에 잘라내지 않습니다**. 현재 코드가 이를 처리하므로 팀원이 수작업으로 준비 패널을 만들 필요가 없습니다.

전처리는 다음과 같습니다.

- **휴장일:** 달력에 없으므로 분석 행을 만들지 않습니다. XKRX와 원본 ZIP에 있던 2026-06-03·2026-07-17 휴장일 보정을 유지했습니다. 보정 휴장일에 공급 시세가 있으면 충돌 오류로 중단합니다. 향후 달력과 시세가 충돌하면 실제 거래일을 확인해 달력을 갱신하거나 `--calendar-csv`로 검증한 달력을 지정하세요.
- **거래일의 시장 지수 누락:** 휴장일로 오인하거나 행을 제거하지 않고 입력 오류로 중단합니다.
- **개별 기업의 가격 결측, 거래량 결측·0:** 그 날짜를 남기고 종목 판정을 불가로 처리합니다. 앞 값이나 0으로 채우지 않습니다.
- **거래 재개일:** 직전 거래일에 유효한 시세가 없으면 여러 날 누적 수익률을 하루 수익률처럼 사용하지 않습니다. 재개 당일 수익률도 결측입니다.
- **절대 수익률 30% 초과:** 원래 관측 수익률은 CSV에 남기고, 해당 날짜의 종목 판정·학습용 수익률·peer 평균에서 제외합니다. 거래량 기준 자료에서도 해당 날짜를 제외합니다. 정확히 ±30%는 이 조건으로 제외하지 않습니다.
- **창 안의 결측:** 유효한 날짜만 골라 120개/40개를 채우지 않습니다. 해당 직전 거래일 창이 완전해야 계산합니다. 결측이나 30% 초과 값 하나가 이후 회귀와 Z 기준 구간에도 영향을 주므로 판정 불가가 여러 달 이어질 수 있습니다.
- **표준편차 0 또는 회귀식 추정 불가:** 임의의 0점이나 정상 판정을 만들지 않습니다.

수집은 FinanceDataReader의 `NAVER:종목코드`, `KS11`, `KQ11`을 사용합니다. 종목 코드는 고정하여 HPSP의 `KOSDAQ GLOBAL` 표기 때문에 기본 수집이 실패하지 않게 했습니다. 필요하면 `--check-listing`으로 현재 상장 목록을 추가 대조할 수 있으며, 이때 `KOSDAQ GLOBAL`은 `KOSDAQ`으로 정규화합니다.

공급자가 반환한 종가·거래량을 사용합니다. 기업행사 전후의 가격 기준이나 나중에 수정된 과거 데이터가 실제 관측 시점과 동일한지는 이 코드만으로 보증하지 않습니다. 현재 고정 35개 peer를 과거 구간에도 적용하는 프로젝트 설정입니다. 입력 CSV와 메타데이터를 함께 보관하면 같은 스냅샷으로 재현할 수 있습니다.

## 5. 결과물과 판정 불가 표현

출력은 아래처럼 팀 저장소 최상위를 기준으로 나누어 저장합니다.

| 경로 | 내용 |
|---|---|
| `stored_data/daily_results.csv` | 분석 대상 6개 기업의 모든 거래일 행 |
| `source_data/anormaly_result/YYYY-MM-DD_기업명.json` | 유효한 종목 가격 OR 거래량 경보에만 생성 |
| `FDS_regression_model/run_config.json` | 공통 모델 설정·입력 해시·생성 파일 목록을 실행당 한 번 저장 |

시장 경보만 있는 날은 CSV에 남고 JSON은 만들지 않습니다. 동일 저장소에서 재실행하면 새 CSV를 저장하고, 이전 실행에서 생성됐지만 이번에는 경보가 아닌 날짜의 JSON을 정리합니다. 두 프로세스가 같은 저장소의 결과에 동시에 쓰지 않도록 실행하세요.

CSV는 요청한 26개 컬럼과 **`decision_status` 1개**로 구성됩니다. 공통 구간·임계값은 날짜별로 반복하지 않고 `run_config.json`에 저장합니다.

```text
date, code, name, market,
alpha, beta_market, beta_sector,
stock_return, market_return, sector_return, sector_pure_return,
market_part, sector_part, expected_return, price_residual,
price_z, volume_z, volume_ratio_40d, price_direction, peer_count,
price_alert, volume_alert, both_alert, alert_type,
market_z, market_alert, decision_status
```

| 상황 | price_alert | volume_alert | both_alert | alert_type |
|---|---|---|---|---|
| 둘 다 경보 | True | True | True | PRICE_AND_VOLUME |
| 가격만 경보 | True | False | False | PRICE_ONLY |
| 거래량만 경보 | False | True | False | VOLUME_ONLY |
| 정상 판정 | False | False | False | NO_ALERT |
| 종목 판정 불가 | 빈값 | 빈값 | 빈값 | 빈값 |

- `decision_status="OK"`는 정상·경보를 **판정할 수 있음**을 뜻합니다. `NO_ALERT`와는 다른 개념입니다.
- 가격·거래량 점수가 모두 유효해야 최종 판정합니다. 한 점수만 유효한 날에도 다른 점수를 정상으로 간주하지 않습니다. 유효하게 계산된 수치 자체는 CSV에 남을 수 있습니다.
- `price_direction`은 **가격 경보가 있을 때** 잔차가 양수면 `UP`, 음수면 `DOWN`입니다. 거래량 단독 경보·미경보·판정 불가·잔차 0이면 빈값/`null`입니다. 이는 실제 주가의 상승·하락 방향과 다를 수 있습니다. 원본의 Z 부호 기반 방향을 요청한 “예상 대비” 의미에 맞춰 잔차 부호 기준으로 명확히 했습니다.
- `market_alert`는 종목 판정과 독립적입니다. 시장 Z가 계산되면 True/False, 계산 불가면 빈값입니다.
- 종목 코드는 문자열입니다. CSV를 다시 읽을 때 `dtype={"code": str}`을 지정해야 `005930`의 앞자리 0을 보존합니다.

`decision_status`의 주요 값:

| 값 | 뜻 |
|---|---|
| `OK` | 종목 경보 판정 가능 |
| `INSUFFICIENT_REGRESSION_HISTORY` | 직전 120거래일 자체가 부족 |
| `INCOMPLETE_REGRESSION_WINDOW` | 직전 120거래일 창에 결측·제외값 포함 |
| `MISSING_CURRENT_INPUT` | 당일 수익률·시장·섹터 등 회귀 입력 부족 |
| `MISSING_PRICE` | 당일 유효 가격 없음 |
| `MISSING_OR_ZERO_VOLUME` | 당일 거래량이 없거나 0 이하 |
| `MISSING_PREVIOUS_QUOTE` | 전일 유효 시세가 없어 일간 수익률 계산 불가 |
| `RETURN_EXCEEDS_30PCT` | 절대 일간 수익률 30% 초과 |
| `RANK_DEFICIENT_REGRESSION` | 회귀 계수를 유일하게 추정할 수 없음 |
| `INCOMPLETE_PRICE_Z_WINDOW` | 유효한 직전 40거래일 가격 잔차 부족 |
| `INCOMPLETE_VOLUME_Z_WINDOW` | 유효한 직전 40거래일 거래량 기준 부족 |
| `ZERO_PRICE_SCALE` / `ZERO_VOLUME_SCALE` | 기준 표준편차가 0이거나 너무 작음 |

여러 원인이 겹치면 대표 이유 한 개만 저장합니다. 일별 컬럼을 늘리지 않기 위한 설계입니다.

JSON에는 요청한 구조 외에 식별용 `date, code, name, market`만 최상위에 추가합니다. 아래는 **형식 예시**이며 실제 탐지 사례가 아닙니다.

```json
{
  "date": "2025-01-02",
  "code": "000660",
  "name": "SK하이닉스",
  "market": "KOSPI",
  "anomaly": {
    "alert_type": "PRICE_AND_VOLUME",
    "direction": "UP",
    "actual_return": 0.072,
    "expected_return": 0.018,
    "abnormal_return": 0.054,
    "price_zscore": 3.21,
    "volume_zscore": 2.84,
    "volume_ratio": 3.7,
    "regression": {
      "market_beta": 0.85,
      "sector_beta": 1.14,
      "market_contribution": -0.012,
      "sector_contribution": 0.025
    },
    "market_z": 4.2,
    "market_alert": true
  }
}
```

시장·섹터 설명분 합계에는 절편이 포함되지 않습니다. CSV의 `alpha`까지 더해야 `expected_return`이 됩니다. 결측 수치는 CSV에서는 빈값, JSON에서는 `null`이며 `NaN` 문자열을 쓰지 않습니다.

## 6. 로컬 서비스·DB 연결

이미 CSV를 수집했다면 서비스 코드에서 직접 호출할 수 있습니다.

```python
from semiconductor_model.__main__ import run_analysis
from semiconductor_model import db_records

daily = run_analysis()  # 코드 위치로 팀 저장소와 입력·출력 경로 결정
records = db_records(daily)
# records: 종목 코드 str, 불리언 bool, 결측 None, 날짜 YYYY-MM-DD인 dict 목록
# DB 연결 계층에서 (date, code)를 키로 upsert하세요.
```

파일 저장 없이 계산과 DB 저장을 연결할 수도 있습니다.

```python
import pandas as pd
from semiconductor_model import read_inputs, build_panel, detect, db_records, get_project_paths

stocks, markets, calendar, universe = read_inputs(get_project_paths().data_dir)
daily = detect(build_panel(stocks, markets, calendar, universe))
daily = daily.loc[daily.date >= pd.Timestamp("2025-01-01")]
records = db_records(daily)
```

DB 종류·접속 정보를 강제하지 않습니다. MySQL용 테이블 예시는 `db_schema.sql`에 있습니다. 데이터베이스 드라이버에는 매개변수 바인딩으로 `records`를 전달하고, 빈값/`None`은 SQL `NULL`로 저장하세요. CSV의 `"False"` 문자열을 Python `bool("False")`로 변환하면 True가 되므로 이런 변환을 사용하지 마세요. CSV 직접 적재보다 `db_records` 이용을 권장합니다.

현재 테이블 예시는 고정 모델 결과 한 벌을 저장합니다. 여러 모델 버전을 동시에 보관할 경우 DB 계층에서 실행 ID와 키를 확장해야 합니다.

## 7. 생성 결과물 정리

삭제 대상 확인:

```bash
python -m semiconductor_model.cleanup
```

실제 삭제:

```bash
python -m semiconductor_model.cleanup --apply
```

`FDS_regression_model/run_config.json`에 기록된 CSV·경보 JSON·설정 파일만 지웁니다. 사전 데이터, 뉴스, 공시, LLM 결과와 `.gitkeep` 등 사용자가 추가한 파일을 보존합니다. 공유 폴더도 삭제하지 않습니다. 생성 목록을 잃으면 임의로 폴더 전체를 삭제하지 않습니다. 사전 데이터는 재사용하므로 자동 정리 대상에서 제외했습니다.

## 8. 검증과 GitHub 업로드

```bash
python -m unittest discover -s FDS_regression_model/tests -v
```

검사는 수식·과거 구간·미래정보 비사용·양방향 30% 제외·거래일 결측·peer 자기 제외·시장 Z·파일 형식·삭제 범위를 확인합니다. 외부 공급자의 연결 상태와 실제 이상거래 탐지 정확도를 평가하는 검사는 아닙니다. 테스트 실행에는 `.[data]` 설치가 필요하며 테스트 자체는 인터넷에 접속하지 않습니다.

이번 팀 폴더 연동 버전은 **25개 자동 검사를 통과**했습니다. 실행 위치에 따른 경로 일관성과 삭제 시 팀 자료 보존을 포함합니다. `.gitignore` 추가 규칙도 실제 Git 명령으로 확인했습니다. 모델 계산·전처리·설정 파일은 첨부 ZIP과 동일합니다.

최초 패키지 제작 시 유효한 동일 입력으로 원본 ZIP과 비교했을 때 회귀·잔차·Z 관련 10개 수치 컬럼도 일치했습니다. 당시 실제 공급처 접속 시험에서는 NAVER 종목 조회가 시간 초과되고 두 지수 조회가 빈 응답을 반환하여, **37개 기업의 실제 시세 전체 수집은 검증하지 못했습니다**. 이번 경로 수정에서는 외부 시세를 다시 수집하지 않았습니다. 빈 응답이나 지수 누락을 성공으로 처리하지 않도록 코드는 중단합니다.

GitHub에는 `FDS_regression_model/`의 코드·문서·테스트·설정 파일과 최상위 `.github/workflows/fds-model-tests.yml`을 올립니다. 모델 폴더의 중복 `.gitignore`는 제거했습니다. 팀의 최상위 `.gitignore`에 추가할 규칙은 `INTEGRATION.md`를 참고하세요. GitHub Actions는 저장소 최상위 워크플로에서 모델 폴더로 이동하여 Python 3.10·3.12 검사를 실행합니다.

라이브러리 안내: [FinanceDataReader](https://github.com/FinanceData/FinanceDataReader), [pandas_market_calendars](https://pandas-market-calendars.readthedocs.io/en/latest/usage.html).
