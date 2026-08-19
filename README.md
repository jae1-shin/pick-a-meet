# Pick a Meet

사내 구성원이 모임의 일시·장소·동네·대표 메뉴·호스트의 한마디를 확인하고 선착순으로 신청하는 서비스입니다. FastAPI, Jinja2, 순수 CSS/JavaScript와 PostgreSQL로 구성되어 있습니다.

- 사내 PostgreSQL·VMware Kubernetes 배포: [INTERNAL_DEPLOYMENT.md](INTERNAL_DEPLOYMENT.md)
- 기능 검증 항목: [TEST_CHECKLIST.md](TEST_CHECKLIST.md)
- 구현 계획: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- 원본 요구사항: [meeting_service_plan.md](meeting_service_plan.md)

## 주요 기능

### 일반 사용자

- 전체·동네별·일시별 모임 보기
- 동네와 날짜 복수 필터
- 모임 신청·취소와 결과 toast
- 신청·잔여 인원 및 신청자 이름·ID·파트·모듈 확인
- 현재 필터와 스크롤을 유지한 5초 카드 현황 자동 갱신
- 신청 시작 전 모임 미리보기, 잔여 시간과 자동 입장

### Host

- 본인이 맡은 모임 목록과 신청자 명단 확인
- 신청자 명단 클립보드 복사
- 장소·동네·대표 메뉴·한마디·일시·정원 편집
- Admin과 동일한 공통 편집 폼과 실시간 카드 미리보기

### Admin

- 사용자 등록·수정과 권한 관리
- 모임 생성·수정, Host 배정과 상태 관리
- 신청 시작 시각 설정과 대기 화면 미리보기
- 사용자·모임 관리 테이블 정렬
- 추가 Admin console 비밀번호 확인

Host와 Admin 권한은 독립적이므로 한 사용자가 두 권한을 함께 가질 수 있습니다.

## 모임 신청 제약

- 전역 신청 시작 시각 전에는 누구도 신청하거나 취소할 수 없습니다. 일반 사용자는 대기 화면으로 이동하고, Admin과 Host는 모임을 미리 볼 수만 있습니다.
- 활성 상태이며 `모임 신청 가능` 권한이 있는 사용자만 신청할 수 있습니다.
- Host 사용자는 신청 권한을 동시에 가질 수 없으며, 실제 OPEN 모임의 Host에게는 신청 버튼도 표시하지 않습니다.
- Admin 권한만으로 신청이 제한되지는 않으며, 신청할 때는 일반 사용자와 같은 규칙을 적용받습니다.
- 사용자는 동시에 모임 하나만 신청할 수 있습니다. 취소한 뒤에는 다른 모임을 신청할 수 있습니다.
- 기본적으로 한 모임에는 같은 파트에서 1명만 신청할 수 있습니다.
- 해당 파트의 `활성 Y` 인원이 `OPEN + CLOSED` 모임 수보다 많을 때는 같은 파트 2명까지 허용합니다. 개인의 현재 신청 가능 여부는 파트원 수 계산에서 제외하지 않습니다.
- 한 모임에서 2명이 신청한 파트는 하나만 허용하며, 같은 파트의 3명째 신청은 항상 차단합니다.
- `OPEN` 모임에만 신청·취소할 수 있고 정원을 초과할 수 없습니다.
- `CLOSED`는 `신청 기간이 아닙니다.`, `CANCELLED`는 `취소되었습니다.`로 표시하고 `DRAFT`는 일반 화면에서 숨깁니다.
- 신청자가 있는 모임은 `CANCELLED`로 바꿀 수 없습니다.
- 화면에서 신청 가능으로 보였더라도 마지막 자리를 다른 사용자가 먼저 가져가면 서버가 다시 검사하여 거절하고, 최신 화면과 `방금 모집이 마감되었습니다.` toast를 보여줍니다.
- PostgreSQL row lock과 unique/check constraint로 동시 신청, 정원 초과와 한 사용자의 중복 신청을 서버에서 방지합니다.

### 사용자 상태 변경 제약

- `모임 신청 가능`을 N으로 바꾸려면 현재 신청한 모임이 없어야 합니다.
- Host를 Y로 바꾸면 모임 신청 권한은 N이어야 합니다.
- 사용자를 비활성화하려면 신청한 모임과 Host로 배정된 모임이 모두 없어야 합니다.
- 화면 제어와 별개로 모든 규칙을 서버에서 다시 검증합니다.

## 로컬 개발 시작

### 1. 준비물

- Python 3.12 이상
- Docker Engine
- Docker Compose plugin 또는 별도 PostgreSQL 17

```bash
docker version
python3 --version
```

### 2. 환경변수

```bash
cp .env.example .env
```

`.env`에서 최소 `DATABASE_PASSWORD`, `SESSION_SECRET_KEY`, `ADMIN_CONSOLE_PASSWORD`를 로컬 값으로 변경합니다. Session key는 32자 이상의 무작위 문자열을 사용합니다.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

`.env`는 Git에 포함되지 않습니다.

### 3. Python 환경

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

### 4. PostgreSQL

Docker Compose를 사용할 경우 PostgreSQL만 실행합니다.

```bash
docker compose up -d postgres
docker compose ps
```

이미 로컬 PostgreSQL이 `127.0.0.1:5432`에서 실행 중이면 `.env`의 접속 정보만 맞추고 이 단계는 생략합니다.

### 5. Migration과 개발 데이터

```bash
. .venv/bin/activate
alembic upgrade head
python -m scripts.seed_demo
```

`seed_demo`는 사용자·모임을 멱등하게 준비하며 기존 신청을 임의로 삭제하지 않습니다. 운영 DB에서는 실행하지 않습니다.

### 6. 개발 서버

```bash
. .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- 애플리케이션: <http://localhost:8000>
- API 문서: <http://localhost:8000/docs>
- liveness: <http://localhost:8000/health/live>
- readiness: <http://localhost:8000/health/ready>
- 글꼴 비교 페이지: <http://localhost:8000/style/font-preview>

`live`는 프로세스 생존 여부를, `ready`는 PostgreSQL 연결까지 확인합니다.

## 개발용 계정

| 역할 | ID | 사번 | 비고 |
|---|---|---|---|
| Admin 전용 | `admin01` | `1` | 사용자·모임 관리 |
| Admin + Host | `leader01` | `2` | 겸임 권한 확인 |
| Host 전용 | `leader02`~`leader05` | `3`~`6` | 서로 다른 모임 담당 |
| 일반 사용자 | `member01`~`member11` | `7`~`17` | 여러 파트·모듈 |

- `member06 / 12`는 비활성 로그인 안내 확인용입니다.
- 로컬 Admin console 비밀번호는 현재 `1234`입니다.
- 운영 환경에서는 개발 계정 대신 최초 Admin bootstrap과 정식 사용자 데이터를 사용합니다.

## 테스트

```bash
. .venv/bin/activate
pytest -q
```

매 변경에서는 관련된 중요 항목만 확인하고, 단계 종료나 배포 전에는 [TEST_CHECKLIST.md](TEST_CHECKLIST.md)를 기준으로 전체 검증합니다. 운영 DB를 자동화 테스트 대상으로 사용하지 않습니다.

## Docker 이미지 로컬 확인

이미지를 빌드합니다.

```bash
docker build -t pick-a-meet:local .
docker images pick-a-meet
```

WSL의 `127.0.0.1:5432` PostgreSQL을 사용하고 기존 개발 서버가 8000번에서 실행 중이라면, host network와 8001번으로 컨테이너를 실행합니다.

```bash
docker run -d \
  --name pick-a-meet-smoke \
  --network host \
  --env-file .env \
  pick-a-meet:local \
  uvicorn app.main:app --host 0.0.0.0 --port 8001
```

```bash
docker ps
docker logs -f pick-a-meet-smoke
curl http://localhost:8001/health/live
curl http://localhost:8001/health/ready
```

종료와 재실행:

```bash
docker stop pick-a-meet-smoke
docker start pick-a-meet-smoke
```

완전히 지울 때만 정지 후 다음을 실행합니다.

```bash
docker rm pick-a-meet-smoke
```

이 `--network host` 설정은 WSL 로컬 smoke test용입니다. 사내 Kubernetes에서는 ConfigMap의 실제 PostgreSQL IP로 연결합니다.

## 주요 환경변수

| 변수 | 로컬 용도 |
|---|---|
| `DATABASE_HOST`, `DATABASE_PORT` | PostgreSQL 주소와 port |
| `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD` | DB 접속 정보 |
| `SESSION_SECRET_KEY` | Cookie 서명 key, 최소 32자 |
| `ADMIN_CONSOLE_PASSWORD` | Admin 메뉴 추가 비밀번호 |
| `SESSION_TIMEOUT_SECONDS` | Session 만료 시간 |
| `SESSION_COOKIE_SECURE` | 로컬 HTTP에서는 `false` |
| `POLLING_INTERVAL_SECONDS` | 카드 현황 갱신 주기, 기본 5초 |
| `TRUSTED_PROXY` | 로컬에서는 `false` |

전체 예시는 [.env.example](.env.example)을 참고합니다.

## 디렉터리

```text
app/                    FastAPI 애플리케이션
  models/               SQLAlchemy 모델
  policies/             Admin·Host·소유권 접근 정책
  routers/              일반·Admin·Host HTTP route
  services/             업무 검증, 조회 표현, 신청 transaction
  templates/            Jinja2 화면과 공통 partial
  static/               CSS, JavaScript, 내장 글꼴
migrations/             Alembic schema migration
scripts/                개발 seed, DB·최초 Admin bootstrap
tests/                  자동화 테스트
k8s/                    사내 Kubernetes manifest 예시
Dockerfile              운영 container image 정의
docker-compose.yml      로컬 PostgreSQL
```

## 구현 메모

- DB schema 변경은 반드시 Alembic revision으로 남기며 `create_all()`과 수동 DDL을 섞지 않습니다.
- 신청 시작 시각은 DB에 저장하고 서버 시작 시 메모리에 적재합니다. 이후 화면과 신청 검증은 메모리 값을 사용합니다.
- 현재 신청 시간 캐시는 단일 프로세스 기준이므로 로컬과 사내 모두 worker/replica 1개를 사용합니다. 다중 replica는 공유 캐시 도입 후 진행합니다.
- 신청·취소 POST는 화면 상태를 신뢰하지 않고 transaction 안에서 사용자, Host, 기존 신청, 모임 상태와 정원을 다시 검사합니다.
- ID·사번은 query string이나 application log에 남기지 않고, 실제 Secret과 개인정보 파일을 Git에 commit하지 않습니다.
