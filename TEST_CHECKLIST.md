# Pick a Meet 검증 체크리스트

모든 항목을 매 변경마다 반복하지 않는다. 각 Phase에서는 변경 위험과 직접 관련된 `P0` 항목만 실행하고, Phase 종료나 배포 전에는 전체를 실행한다.

## P0 — 변경 시 우선 확인

- [x] 앱 liveness와 PostgreSQL readiness
- [x] 어드민/리더/일반 사용자 로그인
- [x] 일반 사용자 `/admin` 접근 403
- [x] 실제 Host의 `/host` 접근 200
- [x] Admin 콘솔 추가 비밀번호: 미인증 redirect, 오답 401, 정답 진입
- [x] Admin 사용자 전환 세션 구분, 대상 권한 적용, 활성 Admin 재검증 후 복귀
- [x] 일반 사용자 신청·취소·재신청
- [x] 전체·동네별·일시별 보기와 동네/날짜 복수 필터, 개인별 신청 상태 필터
- [x] 실제 Host 일반 화면의 신청 버튼 비노출
- [x] 신청 시작 전 일반 사용자는 카드·복수 필터가 있는 대기 화면으로 이동
- [x] Admin/Host는 시작 전 화면 접근, 신청·취소는 DB transaction 전에 차단
- [x] Admin 즉시 허용 후 대기 화면이 10초 보정 주기 안에 자동 이동
- [x] 사용자 권한 조합과 신청/Host 배정 상태 서버 검증
- [ ] 한 사용자의 서로 다른 두 모임 동시 신청은 정확히 한 건만 성공
- [ ] 마지막 한 자리에 여러 사용자가 신청해도 capacity를 넘지 않음
- [x] 같은 파트 기본 1명, 초과 파트 2명 허용, 한 모임 내 중복 파트 하나 제한
- [ ] 실제 OPEN 모임 Host의 모든 신청 차단

## P1 — Phase 종료 전

- [x] 잘못된 ID/사번은 401, inactive 사용자는 별도 안내와 403
- [x] 로그인 실패 후 ID/사번 입력값 유지
- [ ] 최초/동일/변경 IP 로그인 이력
- [ ] Host 권한만 있고 실제 Host가 아니면 신청 가능
- [ ] Admin도 일반 사용자 신청 규칙 적용
- [x] DRAFT 숨김, CLOSED/CANCELLED 변경 차단과 상태별 버튼 문구
- [x] 일반 화면에 신청자 이름·ID·파트·모듈 표시, 설정에 따른 Host 이름·ID·파트·모듈 표시, 신청자 사번 비노출
- [x] Host는 본인 모임 신청자의 이름·ID·파트·모듈만 조회 가능
- [ ] Host가 다른 Host 모임 신청자 URL에 접근하면 403
- [x] Host 본인 모임 편집 화면 접근 및 현재 신청 인원 미만 정원 방지
- [x] Host/Admin 공통 모임 편집 폼, 10분 단위 시간, 실시간 카드 미리보기
- [x] 신청자 명단 클립보드 복사와 공통 toast 표시
- [x] Admin 사용자·모임 테이블 헤더 오름차순/내림차순 정렬
- [ ] 신청/취소 history가 같은 transaction에 기록
- [x] 5초 polling으로 현재 필터를 유지한 카드 현황 갱신, 툴팁 사용 중 DOM 교체 보류, 상태 chip 즉시 재조회
- [x] 신청 시각 설정과 Host 정보 공개 설정의 독립 저장
- [ ] 이미지 MIME/크기/디코딩/HTML sanitization

## P2 — 사내 반입 전

- [ ] Alembic 빈 DB upgrade 및 downgrade 가능 범위 확인
- [ ] 200명 목록·5초 polling 부하
- [ ] 100명 동시 신청, 정원 10 → 정확히 10건
- [ ] Session/CSRF/Cookie/권한 보안 점검
- [ ] Container smoke test와 non-root 실행
- [ ] K8s probe, Secret/ConfigMap, PVC, Ingress client IP 확인
- [ ] 내장 글꼴 등 정적 자산과 license 오프라인 반입
