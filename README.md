# Pick a Meet

사내 구성원 약 200명이 장소·시간·설명을 확인하고 모임 하나에 선착순으로 신청하는 서비스입니다. FastAPI, Jinja2, HTMX, Bootstrap, PostgreSQL을 하나의 애플리케이션으로 구성하고, 로컬 WSL에서 검증한 동일 소스를 사내 Kubernetes 환경으로 옮기는 것을 목표로 합니다.

GitHub repository 이름은 `pick-a-meet`을 사용합니다.

상세 설계와 단계별 구현 범위는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), 원본 요구사항은 [meeting_service_plan.md](meeting_service_plan.md)를 참고하세요.

## 현재 구현 상태

- 완료: 프로젝트 골격, 환경변수 설정, 비동기 PostgreSQL 연결, 서명 Cookie Session, Jinja2 화면
- 완료: DB 모델과 Alembic migration, 로그인/IP 변경 확인, Admin/Host 권한, 개발용 seed
- 완료: 모임 전체·동네별·일시별 보기, 동네/날짜 복수 필터, 신청자 tooltip, 신청·취소
- 완료: Host 본인 모임 조회·편집·신청자 명단, Admin 사용자·모임 CRUD와 테이블 헤더 정렬
- 완료: Gowun Dodum 글꼴과 SIL OFL 라이선스를 `app/static/fonts/`에 내장
- 완료: `/health/live`, `/health/ready`, PostgreSQL Docker Compose, Python 테스트 환경
- 진행 예정: HTMX polling, 동시성 부하 테스트, K8s manifest
- 아직 Bootstrap/HTMX 정적 파일은 포함하지 않았습니다. 최종 사내 반입 전에 버전을 고정해 `app/static/vendor/`에 저장해야 합니다.

## 현재 개발 서버 접속

개발 서버가 실행 중이면 Windows와 WSL의 브라우저에서 다음 주소로 접속합니다.

- 권장: <http://localhost:8000>
- WSL 직접 주소가 필요한 경우 `hostname -I`로 확인한 IP의 8000번 port
- 임시 글꼴 비교: <http://localhost:8000/style/font-preview>

현재 개발용 계정은 다음과 같습니다. 실제 사내 반입 전에 삭제하거나 정식 사용자 데이터로 교체해야 합니다.

| 역할 | ID | 사번 | 이름 | 파트 / 모듈 |
|---|---|---|---|---|
| 어드민 | `admin01` | `1` | 김관리 | 경영지원파트 / 서비스운영모듈 |
| 리더(Host) | `leader01`~`leader05` | `2`~`6` | 이리더 외 4명 | 5개 파트/모듈 |
| 일반 사용자 | `member01`~`member11` | `7`~`17` | 박일반 외 10명 | 여러 파트/모듈 |

개발용 관리자 콘솔 비밀번호는 `1234`입니다. 이 값은 로컬 `.env`에만 있으며 사내 환경에서는 반드시 Secret으로 교체합니다.

서버를 다시 실행할 때는 다음 명령을 사용합니다.

```bash
. .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

더미 데이터는 migration 적용 후 언제든 멱등하게 다시 준비할 수 있습니다.

```bash
alembic upgrade head
python -m scripts.seed_demo
```

Seed에는 서로 다른 시간·장소·정원을 가진 OPEN 모임 5개와 샘플 신청 6건이 포함됩니다. 기존 신청 데이터는 seed 재실행 시 삭제하지 않습니다.

## 핵심 업무 규칙

- 사용자는 동시에 한 모임만 신청할 수 있으며 취소 후 다시 신청할 수 있습니다.
- 실제 OPEN 모임의 Host는 다른 모임에도 신청할 수 없습니다. `host_enabled` 권한만 가진 사용자는 신청할 수 있습니다.
- Admin도 신청할 때는 일반 사용자와 같은 정원·Host·1인 1모임 규칙을 적용받습니다.
- 일반 사용자는 신청자의 이름·ID·파트·모듈을 볼 수 있지만 Host 정보와 신청자 사번은 볼 수 없습니다.
- Host는 본인이 맡은 모임의 장소·동네·메뉴·한마디·시작 일시·정원을 수정할 수 있습니다. 상태와 Host 배정은 Admin만 변경합니다.
- 신청 시 PostgreSQL row lock과 DB constraint를 함께 사용해 마지막 한 자리 경합과 동일 사용자의 동시 신청을 막습니다.

## 디렉터리

```text
app/                    FastAPI 애플리케이션
  config.py             환경변수 설정
  database.py           SQLAlchemy async engine/session
  main.py               앱 조립, 기본 화면, health endpoint
  models/               SQLAlchemy 모델
  routers/              HTTP route
  schemas/              요청/응답 schema
  services/             업무 규칙과 transaction
  templates/            Jinja2 화면
  static/               CSS, JS, 내부 반입용 vendor 파일
tests/                  unit/integration/concurrency 테스트
data/uploads/           로컬 이미지 저장소(파일은 Git 제외)
migrations/             Alembic migration (Phase 2에서 추가)
k8s/                    Kubernetes manifest (배포 단계에서 추가)
```

## 로컬 WSL에서 시작하기

### 1. 준비물

- Python 3.12 이상
- Docker Engine과 Docker Compose plugin
- PostgreSQL client는 선택 사항입니다.

### 2. 환경 설정

```bash
cp .env.example .env
```

`.env`에서 최소 `DATABASE_PASSWORD`와 `SESSION_SECRET_KEY`를 변경하세요. Secret key는 32자 이상의 예측하기 어려운 값이어야 합니다.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

`.env`는 Git에 포함되지 않습니다. 실제 사내 DB 비밀번호나 Session Secret을 `.env.example`, 문서, 소스에 기록하지 마세요.

### 3. Python 환경 설치

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

### 4. PostgreSQL 실행

```bash
docker compose up -d postgres
docker compose ps
```

DB 로그가 필요하면 다음 명령을 사용합니다.

```bash
docker compose logs postgres
```

### 5. 애플리케이션 실행

```bash
. .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 초기 화면: <http://localhost:8000>
- API 문서(개발용): <http://localhost:8000/docs>
- liveness: <http://localhost:8000/health/live>
- readiness: <http://localhost:8000/health/ready>

`live`는 프로세스 생존 여부만, `ready`는 PostgreSQL 연결까지 확인합니다. PostgreSQL이 꺼져 있으면 `ready`가 HTTP 503을 반환하는 것이 정상입니다.

### 6. 테스트

```bash
. .venv/bin/activate
pytest -q
```

DB 모델이 추가된 이후 integration/concurrency 테스트는 전용 PostgreSQL DB를 사용하게 됩니다. 운영 DB를 테스트 대상으로 지정하지 마세요.

## 환경변수

| 변수 | 용도 | 로컬 기본값/주의사항 |
|---|---|---|
| `APP_ENV` | 실행 환경 이름 | `local` |
| `APP_HOST`, `APP_PORT` | bind 주소와 port | `0.0.0.0`, `8000` |
| `DATABASE_HOST`, `DATABASE_PORT` | PostgreSQL 주소 | `localhost`, `5432` |
| `DATABASE_NAME` | DB 이름 | `meeting_service` |
| `DATABASE_USER` | DB 계정 | `meeting_app` |
| `DATABASE_PASSWORD` | DB 비밀번호 | Secret으로 관리 |
| `SESSION_SECRET_KEY` | Cookie 서명 key | 32자 이상, 환경별 별도 값 |
| `ADMIN_CONSOLE_PASSWORD` | Admin 진입 추가 비밀번호 | 로컬만 `1234`, 운영 Secret으로 교체 |
| `SESSION_TIMEOUT_SECONDS` | Session 만료 | 기본 8시간 |
| `SESSION_COOKIE_SECURE` | HTTPS cookie 강제 | 로컬 `false`, 사내 HTTPS `true` |
| `POLLING_INTERVAL_SECONDS` | 화면 갱신 주기 | 기본 5초 |
| `IMAGE_STORAGE_PATH` | 이미지 저장 경로 | 로컬 `./data/uploads` |
| `IMAGE_MAX_SIZE_BYTES` | 업로드 최대 크기 | 기본 5 MiB |
| `TRUSTED_PROXY` | 신뢰 proxy header 처리 | Ingress 확인 전 `false` |

## 개발 진행 순서

기능을 한꺼번에 추가하지 않고 아래 순서로 구현·검증합니다.

1. 실행 골격과 health endpoint
2. SQLAlchemy 모델과 최초 Alembic migration
3. ID/사번 로그인, IP 변경 확인, Session, CSRF
4. Admin 사용자/모임 관리
5. Rich Text Editor와 안전한 이미지 업로드
6. 일반 모임 목록, eligibility, 신청/취소 transaction
7. HTMX 5초 polling과 Host 조회 화면
8. PostgreSQL 동시성, 권한, 브라우저, load/security 테스트
9. Docker image와 Kubernetes manifest

DB 변경은 반드시 Alembic revision으로 남깁니다. 운영 DB에서 ORM의 `create_all()`로 schema를 임의 생성하거나 변경하지 않습니다.

## 사내로 옮길 때: 어디서부터 시작할까

사내 반입은 아래 순서로 진행하면 됩니다. 먼저 대상 환경 정보를 확정하고, 그다음 소스와 artifact를 옮기세요.

### 1. 사내 환경 정보를 먼저 확인

사내 담당자에게 다음 정보를 받습니다.

- Kubernetes namespace, Ingress class/host/TLS 정책
- Container registry 주소, 로그인 및 image 반입 절차
- PostgreSQL host/port/DB/user, TLS 요구사항, migration 실행 권한
- 공유 파일 스토리지 또는 PVC의 storage class와 access mode
- ConfigMap/Secret 관리 방식과 승인 절차
- Ingress가 전달하는 실제 client IP header와 신뢰 가능한 proxy 범위
- 외부 오픈소스와 Python package, frontend asset 반입 승인 절차
- 로그 수집 방식, resource quota, 운영 health probe 기준

이 정보가 없으면 특히 DB 연결, 이미지 영속성, client IP 판단을 확정할 수 없습니다.

### 2. 로컬 완료 기준을 통과

반입 전에 WSL에서 다음을 확인합니다.

- 전체 자동화 테스트 통과
- 로그인, IP 변경 확인, Admin 사용자/모임 생성
- 이미지 업로드와 재조회
- 일반 사용자의 신청, 중복 차단, 취소, 재신청
- 마지막 한 자리에 동시 신청 시 정확히 한 명만 성공
- 한 사용자의 두 모임 동시 신청 시 한 건만 성공
- 일반 사용자에게 Host 정보·신청자 사번이 비노출되고 Admin/Host 권한이 403인지 확인
- 5초 polling 및 신청/취소 직후 즉시 갱신
- Docker image로도 동일 smoke test 통과

### 3. 반입 묶음을 만든다

권장 반입 대상은 다음과 같습니다.

- Git 추적 소스와 Alembic migration
- `pyproject.toml` 및 승인된 dependency 목록/lock 또는 wheelhouse
- Bootstrap, HTMX, TOAST UI Editor의 고정된 내부 정적 파일과 license
- Dockerfile과 사내 base image로 바꿀 항목
- Kubernetes manifest 또는 사내 표준 template
- image digest, SBOM, 보안 스캔 결과가 요구되면 해당 산출물
- 이 README와 배포 변경사항 문서

다음은 반입하면 안 됩니다.

- `.env`, 실제 Secret, DB dump의 개인정보
- `.venv`, `__pycache__`, 로컬 PostgreSQL volume
- `data/uploads`의 개발용 이미지
- 사번이나 사용자 정보가 포함된 test/log 파일

망분리 환경이 인터넷 package registry에 접근할 수 없다면, 승인된 외부 환경에서 Linux/Python 버전을 사내 build 환경과 맞춰 wheelhouse를 준비하거나 사내 package mirror를 사용합니다. 개발자의 `.venv` 디렉터리를 복사하는 방식은 사용하지 않습니다.

### 4. 사내 PostgreSQL을 준비

애플리케이션 전용 DB 계정을 만들고 최소 권한을 부여합니다. 일반 실행 계정과 migration 계정을 분리하는 것이 사내 표준이면 그 정책을 따릅니다.

배포 전 migration job 또는 승인된 작업 환경에서 다음을 실행합니다.

```bash
alembic upgrade head
```

적용 전 현재 revision과 backup/복구 방법을 확인하고, 운영 트래픽이 있는 schema 변경은 migration별 rollback 가능 여부를 검토합니다. 애플리케이션 pod 여러 개가 동시에 migration을 실행하도록 설정하지 않습니다.

### 5. 이미지 저장소를 결정

`IMAGE_STORAGE_PATH`는 pod local filesystem이 아니라 다음 중 하나를 가리켜야 합니다.

- 여러 pod가 공유하는 사내 file/object storage
- 재시작 후에도 유지되는 PVC

replica가 2개 이상이면 모든 pod가 같은 파일을 읽어야 합니다. PVC를 쓸 경우 access mode와 multi-attach 가능 여부를 먼저 확인하세요.

### 6. 사내에서 Container image를 빌드

사내 승인 base image와 package mirror를 사용해 빌드하고 registry에 push합니다. 운영 배포에는 `latest` 대신 변경되지 않는 version tag와 가능하면 digest를 사용합니다.

```bash
docker build -t REGISTRY/pick-a-meet:VERSION .
docker push REGISTRY/pick-a-meet:VERSION
```

망분리 반입 도구가 image archive를 요구하면 사내 절차에 따라 export/import하고, 최종 registry의 digest를 기록합니다.

### 7. ConfigMap과 Secret을 채운다

ConfigMap에는 환경명, DB host/port/name, polling 주기, upload 경로처럼 비밀이 아닌 값을 둡니다. Secret에는 최소 다음 값을 둡니다.

- `DATABASE_USER`
- `DATABASE_PASSWORD`
- `SESSION_SECRET_KEY`

HTTPS Ingress에서는 `SESSION_COOKIE_SECURE=true`로 설정합니다. Secret 실제 값은 Git의 manifest에 적지 않고 사내 Secret 관리 도구로 주입합니다.

### 8. Kubernetes에 순서대로 배포

권장 순서는 다음과 같습니다.

1. namespace와 Secret/ConfigMap 준비
2. PVC 또는 공유 스토리지 mount 준비
3. PostgreSQL 연결 확인
4. Alembic migration을 한 번 실행
5. Deployment와 ClusterIP Service 배포
6. `/health/live`, `/health/ready` probe 확인
7. Ingress/TLS 연결
8. 사내 test 사용자로 smoke test
9. 정상 확인 후 replica 또는 트래픽 확대

초기에는 replica 1개로 기능을 확인하고, 사내 HA 기준에 따라 2개 이상으로 확장합니다. Session은 서명 Cookie이므로 pod affinity/sticky session에 의존하지 않아야 합니다.

### 9. Ingress 뒤 client IP를 검증

브라우저가 보낸 임의의 `X-Forwarded-For`를 그대로 신뢰하면 안 됩니다. Ingress controller가 기존 header를 어떻게 제거/추가하는지 확인하고, 신뢰 proxy에서 온 요청에 한해서만 실제 client IP를 해석합니다.

검증이 끝나기 전에는 `TRUSTED_PROXY=false`를 유지하세요. IP 변경 확인은 보조 경고 수단이지 강한 본인인증 수단이 아닙니다.

### 10. 배포 직후 smoke test

```text
GET /health/live   → 200
GET /health/ready  → 200
```

그 뒤 UI에서 다음을 확인합니다.

- 최초 로그인, 동일 IP 로그인, 다른 IP 확인 흐름
- 일반 사용자 `/admin` 접근 시 403
- Admin 사용자/모임 관리
- 이미지 업로드 후 pod 재시작에도 이미지 유지
- 신청/취소/재신청과 정원 차단
- 두 브라우저에서 마지막 한 자리 동시 신청
- 5초 polling과 신청 직후 즉시 반영
- 일반 사용자 HTML/API에 Host 정보·신청자 사번이 없는지 확인

### 11. 운영 전 마지막 점검

- Secret과 사번이 application log에 출력되지 않는지 확인
- HTTPS, Secure/HttpOnly/SameSite cookie 확인
- DB backup, migration 실패, image rollback 절차 확인
- readiness 실패 시 pod가 트래픽에서 제외되는지 확인
- upload volume 용량과 권한, backup 정책 확인
- CPU/memory request/limit와 200명 polling 부하 결과 확인
- 최초 Admin을 만드는 승인된 bootstrap 절차를 수행하고 임시 수단은 제거

## 배포 실패 시 확인 순서

- `/health/live` 실패: process start command, port, image log 확인
- `live` 성공/`ready` 실패: DB DNS, port, credential, TLS, migration 상태 확인
- 로그인 후 Session 유지 실패: pod별 `SESSION_SECRET_KEY` 일치 여부, HTTPS와 Secure cookie 확인
- 이미지가 사라짐: `IMAGE_STORAGE_PATH` mount와 PVC/shared storage 확인
- 실제 client IP가 모두 동일: Ingress forwarded header와 trusted proxy 설정 확인
- 신청 정합성 오류: PostgreSQL을 사용 중인지, 최신 migration/constraint가 적용됐는지 확인

## 중지 및 정리

로컬 앱은 실행 terminal에서 `Ctrl+C`로 중지합니다. PostgreSQL container만 내리되 data를 보존하려면:

```bash
docker compose down
```

PostgreSQL volume 삭제는 모든 로컬 DB 데이터를 지우므로 일반적인 중지 절차에 포함하지 않습니다.

## 보안 메모

- ID/사번은 query string으로 보내지 않고 사번 전체를 log에 남기지 않습니다.
- UI에서 버튼을 숨기는 것과 별개로 모든 Admin/Host 권한을 backend에서 검사합니다.
- Rich Text HTML은 allowlist로 정제하고 업로드 파일은 확장자만이 아니라 실제 image 형식과 크기를 검사합니다.
- 신청 가능 여부는 화면 표시와 무관하게 transaction 안에서 최신 값으로 다시 검증합니다.
- 운영 Secret과 개인정보가 포함된 파일을 issue, chat, Git commit에 첨부하지 않습니다.
