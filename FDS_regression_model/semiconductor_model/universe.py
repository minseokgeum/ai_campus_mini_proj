"""프로젝트에서 지정한 고정 35 peer와 6개 분석 기업. 두 시장을 합쳐 평균한다."""
import pandas as pd

# code, name, market, is_peer, is_target
UNIVERSE_ROWS = [
    ('000660', 'SK하이닉스', 'KOSPI', True, True),
    ('000990', 'DB하이텍', 'KOSPI', True, True),
    ('108320', 'LX세미콘', 'KOSPI', True, False),
    ('080220', '제주반도체', 'KOSDAQ', True, False),
    ('102120', '어보브반도체', 'KOSDAQ', True, False),
    ('054450', '텔레칩스', 'KOSDAQ', True, False),
    ('403870', 'HPSP', 'KOSDAQ', True, False),
    ('036930', '주성엔지니어링', 'KOSDAQ', True, True),
    ('084370', '유진테크', 'KOSDAQ', True, False),
    ('095610', '테스', 'KOSDAQ', True, False),
    ('319660', '피에스케이', 'KOSDAQ', True, False),
    ('281820', '케이씨텍', 'KOSPI', True, False),
    ('322310', '오로스테크놀로지', 'KOSDAQ', True, False),
    ('348210', '넥스틴', 'KOSDAQ', True, False),
    ('042700', '한미반도체', 'KOSPI', True, True),
    ('089030', '테크윙', 'KOSDAQ', True, False),
    ('003160', '디아이', 'KOSPI', True, False),
    ('232140', '와이씨', 'KOSDAQ', True, False),
    ('092870', '엑시콘', 'KOSDAQ', True, False),
    ('058470', '리노공업', 'KOSDAQ', True, False),
    ('095340', 'ISC', 'KOSDAQ', True, False),
    ('064760', '티씨케이', 'KOSDAQ', True, False),
    ('166090', '하나머티리얼즈', 'KOSDAQ', True, False),
    ('357780', '솔브레인', 'KOSDAQ', True, False),
    ('067310', '하나마이크론', 'KOSDAQ', True, False),
    ('036540', 'SFA반도체', 'KOSDAQ', True, False),
    ('131970', '두산테스나', 'KOSDAQ', True, False),
    ('061970', 'LB세미콘', 'KOSDAQ', True, False),
    ('033640', '네패스', 'KOSDAQ', True, False),
    ('222800', '심텍', 'KOSDAQ', True, False),
    ('353200', '대덕전자', 'KOSPI', True, False),
    ('195870', '해성디에스', 'KOSPI', True, False),
    ('399720', '가온칩스', 'KOSDAQ', True, False),
    ('394280', '오픈엣지테크놀로지', 'KOSDAQ', True, False),
    ('094360', '칩스앤미디어', 'KOSDAQ', True, False),
    ('005930', '삼성전자', 'KOSPI', False, True),
    ('240810', '원익IPS', 'KOSDAQ', False, True),
]


def get_universe():
    """삼성전자·원익IPS를 포함해 중복 없는 수집 대상 37개를 반환한다."""
    return pd.DataFrame(UNIVERSE_ROWS, columns=["code", "name", "market", "is_peer", "is_target"])
