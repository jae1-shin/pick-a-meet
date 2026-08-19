# Pick a Meet 검증 체크리스트

모든 항목을 매 변경마다 반복하지 않는다. 각 Phase에서는 변경 위험과 직접 관련된 `P0` 항목만 실행하고, Phase 종료나 배포 전에는 전체를 실행한다.

## P0 — 변경 시 우선 확인

- [x] 앱 liveness와 PostgreSQL readiness
- [x] 어드민/리더/일반 사용자 로그인
- [x] 일반 사용자 `/admin` 접근 403
- [x] 실제 Host의 `/host` 접근 200
- [x] Admin 콘솔 추가 비밀번호: 미인증 redirect, 오답 401, 정답 진입
- [x] 일반 사용자 신청·취소·재신청
- [ ] 한 사용자의 서로 다른 두 모임 동시 신청은 정확히 한 건만 성공
- [ ] 마지막 한 자리에 여러 사용자가 신청해도 capacity를 넘지 않음
- [ ] 실제 OPEN 모임 Host의 모든 신청 차단

## P1 — Phase 종료 전

- [ ] 잘못된 ID/사번과 inactive 사용자 로그인 실패
- [ ] 최초/동일/변경 IP 로그인 이력
- [ ] Host 권한만 있고 실제 Host가 아니면 신청 가능
- [ ] Admin도 일반 사용자 신청 규칙 적용
- [ ] CLOSED/CANCELLED/DRAFT 모임 신청 차단
- [ ] 일반 응답 HTML/API에 Host 및 다른 신청자 식별정보 없음
- [ ] 신청/취소 history가 같은 transaction에 기록
- [ ] HTMX polling과 신청 직후 fragment 갱신
- [ ] 이미지 MIME/크기/디코딩/HTML sanitization

## P2 — 사내 반입 전

- [ ] Alembic 빈 DB upgrade 및 downgrade 가능 범위 확인
- [ ] 200명 목록·5초 polling 부하
- [ ] 100명 동시 신청, 정원 10 → 정확히 10건
- [ ] Session/CSRF/Cookie/권한 보안 점검
- [ ] Container smoke test와 non-root 실행
- [ ] K8s probe, Secret/ConfigMap, PVC, Ingress client IP 확인
- [ ] Bootstrap/HTMX/Editor 정적 자산 및 license 오프라인 반입
