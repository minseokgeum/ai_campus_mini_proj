"""사용자가 확정한 운영 설정. 날짜별 CSV에는 반복 저장하지 않는다."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelConfig:
    # [요구사항] 모두 달력일이 아닌 거래일. 당일 자료를 기준 창에 포함하지 않는다.
    train_window: int = 120
    z_window: int = 40
    price_threshold: float = 2.5
    volume_threshold: float = 2.5
    market_z_window: int = 120
    market_threshold: float = 3.0
    max_abs_stock_return: float = 0.30
    min_peer_coverage: float = 0.90
    std_ddof: int = 1
    scale_floor: float = 1e-12
    model_version: str = "market_sector_ols_v2"

    def __post_init__(self):
        # volume_ratio_40d 등의 출력 계약을 유지하기 위해 운영 설정을 고정한다.
        expected = (120, 40, 2.5, 2.5, 120, 3.0, 0.30, 0.90, 1, 1e-12)
        actual = (self.train_window, self.z_window, self.price_threshold,
                  self.volume_threshold, self.market_z_window, self.market_threshold,
                  self.max_abs_stock_return, self.min_peer_coverage,
                  self.std_ddof, self.scale_floor)
        if actual != expected:
            raise ValueError("운영 설정은 120/40, 가격·거래량 2.5/2.5, 시장 120/3.0으로 고정되어 있습니다.")

    def to_dict(self):
        return asdict(self)


CONFIG = ModelConfig()
DATA_START = "2024-01-01"  # 2025년 첫 분석을 위한 120일 회귀 + 40일 잔차 준비
ANALYSIS_START = "2025-01-01"
MARKET_SYMBOLS = {
    "KOSPI": "YAHOO:^KS11",
    "KOSDAQ": "YAHOO:^KQ11",
}

# [요구사항] 이름 그대로 DB 컬럼으로 쓸 수 있는 고정 출력 순서.
# decision_status만 추가: 판정 불가를 NO_ALERT/False와 구별하기 위해 필요하다.
DAILY_COLUMNS = [
    "date", "code", "name", "market", "alpha", "beta_market", "beta_sector",
    "stock_return", "market_return", "sector_return", "sector_pure_return",
    "market_part", "sector_part", "expected_return", "price_residual",
    "price_z", "volume_z", "volume_ratio_40d", "price_direction", "peer_count",
    "price_alert", "volume_alert", "both_alert", "alert_type",
    "market_z", "market_alert", "decision_status",
]
BOOLEAN_COLUMNS = ["price_alert", "volume_alert", "both_alert", "market_alert"]
