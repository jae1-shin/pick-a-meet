# 사내 모임 신청 서비스 구현 계획

## 1. Architecture

- 로컬: Browser → FastAPI(Uvicorn, Jinja2/HTMX) → Docker Compose PostgreSQL, 이미지 파일은 `./data/uploads`.
- 사내: Browser → Ingress → ClusterIP Service → stateless FastAPI Deployment → 사내 PostgreSQL + 공유 스토리지/PVC.
- 세션은 서명 쿠키에 최소 `member_id`만 저장하고, 권한과 신청 가능 여부는 요청마다 DB에서 다시 읽는다.
- 하나의 배포 단위와 하나의 DB를 유지하며 Redis, 메시지 큐, SPA, WebSocket은 도입하지 않는다.

## 2. Dependencies

- Runtime: FastAPI, Uvicorn, SQLAlchemy 2, asyncpg, Alembic, Jinja2, python-multipart, pydantic-settings, itsdangerous, bleach, Pillow.
- Test: pytest, pytest-asyncio, HTTPX.
- Frontend: Bootstrap 5, HTMX, TOAST UI Editor를 버전 고정하여 `app/static/vendor`에 보관한다. 외부 CDN은 사용하지 않는다.

## 3. File Structure

```text
app/
  main.py config.py database.py
  models/ schemas/ services/ routers/
  templates/{meetings,admin,host}/
  static/{css,js,vendor}/
migrations/ tests/{unit,integration,concurrency}/
docker/ k8s/ data/uploads/
pyproject.toml docker-compose.yml Dockerfile .env.example README.md
```

## 4. Database

- `part(id, name UNIQUE)`, `module(id, part_id FK, name, UNIQUE(part_id,name))`.
- `member(id, login_id UNIQUE, employee_no UNIQUE, name, module_id FK, host_enabled, apply_enabled, admin_enabled, active, last_login_ip, last_login_at, timestamps)`.
- `login_history(id, member_id FK, login_at, login_ip, ip_changed, login_result CHECK)`.
- `meeting(id, place_name, start_at, end_at, description_content TEXT, capacity CHECK > 0, status CHECK, timestamps)`와 `CHECK(end_at > start_at)`.
- `meeting_host(meeting_id UNIQUE/FK, member_id FK)`.
- `registration(id, member_id UNIQUE/FK, meeting_id FK, registered_at)`.
- `registration_history(id, member_id FK, meeting_id FK, action CHECK, created_at)`.
- FK 삭제 정책은 운영 데이터 유실 방지를 위해 기본 `RESTRICT`; 이력은 원본 ID를 유지한다. 상태·Host·신청 조회용 최소 인덱스만 둔다.

## 5. Authentication

- `ID + 사번 + active`를 한 번에 검증하고 실패 원인은 통합 메시지로 반환한다.
- 최초/동일 IP는 즉시 로그인, 변경 IP는 짧은 수명의 pending 값을 서명 세션에 두고 확인 후 완료한다.
- 성공·실패·IP 재확인을 `login_history`에 기록하며 사번은 로그에 남기지 않는다.
- 쿠키는 HttpOnly/SameSite=Lax, 운영에서 Secure=true, 유휴 만료를 적용한다. 프록시 헤더는 설정된 trusted proxy에서만 해석한다.

## 6. Authorization

- 일반 route는 활성 로그인 사용자, `/admin/**`는 최신 `admin_enabled`, `/host/**`는 대상 모임의 실제 Host 관계를 검사한다.
- 일반 응답 DTO/쿼리에는 Host와 신청자 식별 필드를 포함하지 않는다.
- 상태 변경 POST에는 세션 사용자만 사용하고 CSRF 토큰을 검증한다.

## 7. Meeting

- 생성/수정은 Admin에 집중한다. Host는 본인 모임 및 신청자 목록을 읽기만 한다.
- HTML은 bleach allowlist로 정제하고 업로드는 크기, 실제 이미지 디코딩, 허용 포맷을 검사한 뒤 난수 파일명으로 저장한다.
- Storage protocol을 두어 로컬 경로와 공유/PVC 경로를 설정으로 교체한다.

## 8. Registration

- 신청 트랜잭션의 잠금 순서는 `member FOR UPDATE` → `meeting FOR UPDATE`로 고정한다. 이를 통해 동일 사용자의 서로 다른 모임 동시 요청도 직렬화한다.
- 잠금 후 member 활성/신청권한, 유효 OPEN 모임 Host 여부, 기존 registration, meeting OPEN, 최신 count와 capacity를 재검증한다.
- registration과 APPLY history를 같은 트랜잭션에서 기록한다. `UNIQUE(member_id)` 충돌은 `ALREADY_REGISTERED` 업무 충돌로 변환한다.
- 취소도 member 잠금 후 세션 사용자의 registration만 삭제하고 CANCEL history를 같은 트랜잭션에 기록한다.
- 모든 코드 경로에서 잠금 순서를 동일하게 유지해 교착 가능성을 줄인다.

## 9. Frontend

- Bootstrap Navbar/Container/Card/Table/Form/Alert 중심의 반응형 서버 렌더링을 사용한다.
- Backend view model이 `can_apply`, `cannot_apply_reason`, count를 계산하고 템플릿은 표현만 담당한다.
- 신청/취소 버튼은 요청 중 비활성화하고 응답 fragment에 즉시 최신 상태와 메시지를 포함한다.

## 10. Polling

- `/meetings/status-fragment`를 HTMX `every {설정값}s`로 갱신한다.
- 목록 전체가 아닌 내 신청과 카드 상태 영역만 반환한다. 신청/취소 응답도 동일 fragment를 반환해 즉시 동기화한다.

## 11. Image

- `ImageStorage.save/delete/url` 인터페이스와 local filesystem 구현을 둔다.
- DB/HTML에는 URL만 저장한다. K8s에서는 모든 replica가 보는 공유 스토리지/PVC를 mount한다.

## 12. Tests

- Unit: eligibility reason 우선순위, IP 처리, HTML/이미지 검증.
- Integration(PostgreSQL): 로그인, 권한, CRUD, 신청/취소/이력/constraints.
- Concurrency: 마지막 1자리 다중 신청, 한 사용자 2개 모임, 100명/정원 10, 신청-취소 경합.
- Browser: 로그인부터 신청/취소 및 Admin 권한까지 Playwright로 검증한다.
- Load: 200명 목록/5초 polling과 100명 동시 신청을 별도 스크립트로 측정한다.

## 13. Docker

- multi-stage가 필요 없는 작은 Python slim 이미지, non-root 사용자, 고정 dependency 설치, `data/uploads` volume을 사용한다.
- Compose는 app과 PostgreSQL healthcheck를 제공하며 `.env`로만 접속 정보를 받는다.

## 14. Kubernetes

- Deployment(초기 1 replica, 무상태), Service, Ingress, ConfigMap, Secret 예시, 필요 시 PVC를 제공한다.
- `/health/live`, `/health/ready` probe와 CPU/memory requests/limits를 둔다.
- 실제 Secret 값과 Ingress class/host/TLS, storageClass는 사내 배포 단계에서 주입한다.

## 15. Migration and phases

1. 실행 골격, 설정, DB 연결, 기본 템플릿, health endpoint.
2. SQLAlchemy 모델과 최초 Alembic migration.
3. 로그인/IP 확인/서명 세션/CSRF.
4. Admin member 및 meeting CRUD, editor와 이미지.
5. 일반 목록, eligibility, 신청/취소 transaction, polling.
6. Host 읽기 화면과 전체 권한 테스트.
7. 동시성/load/security 검증.
8. Docker/Kubernetes 패키징과 사내 환경 체크리스트.

각 단계는 독립적으로 테스트가 통과한 뒤 다음 단계로 진행한다.
