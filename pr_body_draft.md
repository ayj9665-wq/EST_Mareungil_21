## 작업 개요
박윤후 담당 경로 모듈 DesignatedPointRouteProvider를 구현했습니다.
현재 구현은 완결된 보행 경로를 생성하거나 안전성을 보장하는 길찾기 엔진이 아닙니다. 지정 목적지 또는 대피시설 후보를 공식 통제정보, 하수 센서의 상대 위험 신호, 직선거리 기준으로 비교하는 MVP Provider입니다.

## 주요 구현
### MOVE
- 사용자가 선택한 지정 목적지 1곳을 검증
- 공식 통제 또는 확인된 침수정보에 목적지 ID가 명시된 경우 DESTINATION_BLOCKED 반환

### EVACUATE
- 안전거점 7곳을 비교
- 공식 차단 대상 제외
- 최근접 유효 센서의 30분 고수위 확률과 사용자 위치 기준 직선거리로 결정론적 정렬
- 후보가 없으면 NO_SAFE_POINT 반환

### WAIT, EMERGENCY, UNAVAILABLE
- Provider 호출이 필요하지 않으며 NOT_REQUIRED 반환

- 유효 센서가 없으면 DATA_UNAVAILABLE 반환
- LIVE 버전은 실제 완결 보행경로를 탐색하지 않으므로 NO_SAFE_ROUTE를 생성하지 않음
- route_verified=false
- eta_sec=null
- profile_applied=[]
- 안전거점에 가짜 route_id를 부여하지 않으며 candidates는 생략

## 실제 데이터 검증
사용 픽스처:
- contracts/fixtures/risk_S3_peak.json
- official_0808.json

재생 시각: 2022-08-08T21:40:00+09:00

센서:
- 전체 센서: 31개
- 유효 센서: 30개
- 제외 센서: 23-0007 — 좌표 누락
- 30분 확률 누락 센서: 없음

EVACUATE 결과:
- 선택 후보: SP-006 서초4동주민센터
- 사용자 위치와의 직선거리: 709.96m
- 상대 비교에 사용된 최근접 센서: 22-0009
- 센서와 시설 간 거리: 167.41m
- 비교 확률: 0.9988
주의: 0.9988은 대피시설의 침수 확률이 아니라 최근접 하수 센서의 30분 고수위 확률입니다.

MOVE 결과:
- 목적지: GN-002 신논현역
- 사용자 위치와의 직선거리: 768.89m

공식정보 적용 결과:
- 활성 통제정보 6건
- blocks_destination_ids에 목적지 또는 안전거점 ID가 명시된 항목이 없어 실제 제외 후보는 0건
- 좌표 거리만으로 통제 대상을 추정하지 않음

## 테스트
- 전체 테스트: 252개 통과
- skip/xfail: 0건
- make.ps1 check: 전체 PASS
- Provider 원본 반환값을 SafeRoute JSON Schema로 직접 검증
- 동일 입력에 동일 결과가 반환되는 결정론 검증

## 변경 파일
PR에는 다음 6개 파일만 포함되어야 합니다.
- services/route/interface.py
- services/route/provider.py
- services/route/distance.py
- tests/test_route_provider.py
- tests/test_route_provider_real_data.py
- docs/route_integration_handoff.md

## 제한 사항 및 계약 부채
- 현재 결과는 실제 보행 경로가 아니라 점대점 후보 비교 결과
- 안전·최적·검증 완료 경로로 표현하면 안 됨
- 공식 대피경로 30개를 연결한 실제 경로 탐색은 이번 LIVE 범위에서 제외
- FALLBACK_CANDIDATE + route_attempted=true는 현재 계약 준수를 위해 유지하지만 실제 경로 탐색 의미와 차이가 있음
- API·Decision Engine·UI E2E 연결은 통합 담당자의 후속 작업

## 통합 시 주의사항
- API가 사용자 출발 위치, 해당 재생 시각의 RF 센서, 공식정보를 Provider에 주입해야 함
- Provider는 MOVE, EVACUATE에서만 사용
- UI에서는 결과를 “상대적으로 비교된 후보”로 표시
- 센서 확률을 목적지나 대피시설의 침수 확률로 표시하지 않기
