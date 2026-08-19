# 사내 모임 신청 서비스 구현 계획

## 1. Architecture

- 로컬: Browser → FastAPI(Uvicorn, Jinja2/순수 JavaScript) → Docker Compose PostgreSQL.
- 사내: Browser → Ingress → ClusterIP Service → stateless FastAPI Deployment → 사내 PostgreSQL + 공유 스토리지/PVC.
- 세션은 서명 쿠키에 최소 `member_id`만 저장하고, 권한과 신청 가능 여부는 요청마다 DB에서 다시 읽는다.
- 하나의 배포 단위와 하나의 DB를 유지하며 Redis, 메시지 큐, SPA, WebSocket은 도입하지 않는다.

## 2. Dependencies

- Runtime: FastAPI, Uvicorn, SQLAlchemy 2, asyncpg, Alembic, Jinja2, python-multipart, pydantic-settings, itsdangerous, bleach, Pillow.
- Test: pytest, pytest-asyncio, HTTPX.
- Frontend: 순수 CSS/JavaScript와 서버 렌더링을 사용하며 글꼴을 포함한 정적 자산은 앱 내부에 보관한다. 외부 CDN은 사용하지 않는다.

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
- `meeting(id, place_name, place_url, neighborhood, representative_menu, host_message TEXT, start_at, capacity CHECK > 0, status CHECK, timestamps)`.
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
- Admin 사용자 전환은 Admin console 재인증과 CSRF를 통과한 POST로만 시작한다. 세션에 `login`/`impersonation` 종류와 원래 Admin ID를 구분해 저장하고, 복귀 시 원래 계정의 활성·Admin 권한을 다시 검사한다.
- 신청자 이름·ID·파트·모듈은 공개하고 신청자 사번은 포함하지 않는다. Host 이름·ID·파트·모듈은 Admin의 전역 공개 설정이 켜진 경우에만 일반 모임 카드에 포함한다.
- 상태 변경 POST에는 세션 사용자만 사용하고 CSRF 토큰을 검증한다.

## 7. Meeting

- 생성과 상태·Host 배정은 Admin이 담당한다. Host는 본인 모임의 정보·일시·정원을 수정하고 신청자 목록을 조회한다.
- 모임 콘텐츠는 구조화된 일반 Text 필드로 관리하며 Rich Text와 이미지 업로드는 현재 범위에서 제외한다.

## 8. Registration

- 신청 트랜잭션의 잠금 순서는 `member FOR UPDATE` → `meeting FOR UPDATE`로 고정한다. 이를 통해 동일 사용자의 서로 다른 모임 동시 요청도 직렬화한다.
- 잠금 후 member 활성/신청권한, 유효 OPEN 모임 Host 여부, 기존 registration, meeting OPEN, 최신 count와 capacity를 재검증한다.
- 기본적으로 모임별 같은 파트는 1명으로 제한한다. 활성 파트원이 `OPEN + CLOSED` 모임 수보다 많을 때만 2명까지 허용하며, 한 모임에서 2명이 된 파트는 하나만 허용한다. 신청 가능 여부는 파트원 수 계산에 사용하지 않는다.
- registration과 APPLY history를 같은 트랜잭션에서 기록한다. `UNIQUE(member_id)` 충돌은 `ALREADY_REGISTERED` 업무 충돌로 변환한다.
- 취소도 member 잠금 후 세션 사용자의 registration만 삭제하고 CANCEL history를 같은 트랜잭션에 기록한다.
- 모든 코드 경로에서 잠금 순서를 동일하게 유지해 교착 가능성을 줄인다.

## 9. Frontend

- Bootstrap Navbar/Container/Card/Table/Form/Alert 중심의 반응형 서버 렌더링을 사용한다.
- Backend view model과 신청 transaction이 공통 registration policy를 사용해 `can_apply`, 거절 사유와 count를 계산하고 템플릿은 표현만 담당한다.
- 신청/취소 버튼은 요청 중 비활성화하고 응답 fragment에 즉시 최신 상태와 메시지를 포함한다.

## 10. Polling

- `/meetings/status-fragment`를 순수 JavaScript로 설정 주기마다 갱신한다.
- 동네·날짜와 개인별 신청 상태 필터를 유지하며, 상태 chip 클릭은 서버 최신 상태를 즉시 조회한다.
- hover·focus·클릭 고정된 신청자 툴팁이 있으면 DOM 교체를 미뤄 polling으로 닫히지 않게 한다.

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
4. Admin member 및 meeting CRUD와 공통 모임 편집 폼.
5. 일반 목록, eligibility, 신청/취소 transaction, polling.
6. Host 읽기 화면과 전체 권한 테스트.
7. 동시성/load/security 검증.
8. Docker/Kubernetes 패키징과 사내 환경 체크리스트.

각 단계는 독립적으로 테스트가 통과한 뒤 다음 단계로 진행한다.
