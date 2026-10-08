-- MySQL 예시: daily_results.csv의 27개 컬럼과 일치한다.
-- 코드 앞자리 0 보존: code를 숫자형으로 바꾸지 않는다.
-- 판정 불가: nullable 경보/점수/alert_type에 NULL을 저장한다.
-- 수익률과 설명분: 0.01 = 1%. date는 한국 거래일 라벨이다.
CREATE TABLE IF NOT EXISTS daily_results (
    date DATE NOT NULL,
    code CHAR(6) NOT NULL,
    name VARCHAR(64) NOT NULL,
    market VARCHAR(10) NOT NULL,
    alpha DOUBLE NULL,
    beta_market DOUBLE NULL,
    beta_sector DOUBLE NULL,
    stock_return DOUBLE NULL,
    market_return DOUBLE NULL,
    sector_return DOUBLE NULL,
    sector_pure_return DOUBLE NULL,
    market_part DOUBLE NULL,
    sector_part DOUBLE NULL,
    expected_return DOUBLE NULL,
    price_residual DOUBLE NULL,
    price_z DOUBLE NULL,
    volume_z DOUBLE NULL,
    volume_ratio_40d DOUBLE NULL,
    price_direction VARCHAR(4) NULL,
    peer_count INT NOT NULL,
    price_alert BOOLEAN NULL,
    volume_alert BOOLEAN NULL,
    both_alert BOOLEAN NULL,
    alert_type VARCHAR(20) NULL,
    market_z DOUBLE NULL,
    market_alert BOOLEAN NULL,
    decision_status VARCHAR(64) NOT NULL,
    PRIMARY KEY (date, code)
) DEFAULT CHARACTER SET utf8mb4;
