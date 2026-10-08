# ai_campus_mini_proj

1. stored_data :  적재해놓아야하는 데이터들을 저장하는 디렉토리
 - stored_data/daily_results.csv : 모든 날의 이상 여부 판단 결과 저장
 - stored_data/dart/ : 공시자료 저장
 - stored_data/news/ : 미리 크롤링한 뉴스들 저장(본 프로젝트에서의 검색 결과에 해당할 자료)

2. source_data : LLM에게 넘겨줄 source_items에 해당하는 데이터를 저장하는 디렉토리
 - source_data/anormaly_result : daily_results.csv에서 이상으로 탐지된 경우에 생성하는 json 파일 저장
 - source_data/source_news : 검색 결과로 나온 뉴스들 중 LLM에게 넘겨줄 정재된 뉴스 정보
 
3. result : LLM을 거쳐 생성된 결과 저장
 - result/evidences.json : LLM이 어떤 자료를 배경분석에 채택하였는지와 그 채택 근거를 저장한 중간 확인 파일
 - result/results.txt : LLM이 생성한 응답