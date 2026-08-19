# 사내 모임 신청 서비스 구현 지시서

## 0. 문서 목적

본 문서는 사내 구성원 약 200명 규모가 사용하는 **모임 신청 서비스**를 로컬 WSL 환경에서 먼저 개발한 뒤, 사내 Kubernetes Cluster에 배포하기 위한 통합 구현 지시서이다.

이 문서를 Codex 등의 Plan Mode에 그대로 입력하여 다음 순서로 진행하는 것을 목표로 한다.

1. 로컬 WSL에서 개발 환경 구성
2. PostgreSQL 기반 기능 구현
3. 화면 및 신청/취소 기능 구현
4. 동시성 및 권한 테스트
5. Docker 이미지 생성
6. 사내 환경에 소스 반입
7. 사내 PostgreSQL 및 Kubernetes 환경에 맞게 설정 변경
8. 사내 K8s Cluster 배포

구현의 최우선 가치는 다음과 같다.

- 단순성
- 데이터 정합성
- 유지보수성
- 익숙한 UI
- 사내 반입 용이성
- 최소한의 외부 의존성

---

# 1. 서비스 개요

여러 개의 모임을 만들어 사내 구성원들이 장소/시간/설명을 보고 원하는 모임 하나에 선착순 신청하는 서비스이다.

일반 사용자는 모임의 실제 Host가 누구인지 알 수 없다.

사용자가 확인할 수 있는 정보는 다음과 같다.

- 모임 장소
- 시간
- 장소 바로가기 링크
- 대표 동네
- 대표 메뉴
- Host의 한마디
- 모집 정원
- 현재 신청 인원
- 잔여 인원
- 신청 가능 여부
- 본인의 신청 여부
- 신청자 이름
- 신청자 ID
- 신청자 파트/모듈

일반 사용자가 확인할 수 없는 정보:

- Host 이름
- Host ID
- Host 사번
- Host 파트/모듈
- 신청자 사번

---

# 2. 핵심 업무 규칙

## 2.1 1인 1모임

한 명의 사용자는 동시에 활성 상태의 모임을 최대 **1개**만 신청할 수 있다.

```text
활성 신청 없음
→ 모임 신청 가능

활성 신청 1개 있음
→ 다른 모임 신청 불가
```

기존 신청을 취소하면 다시 신청할 수 있다.

---

## 2.2 신청 취소

신청자는 본인이 신청한 모임을 직접 취소할 수 있다.

```text
모임 A 신청
→ 취소
→ 미신청 상태
```

취소 후:

- 동일 모임 재신청 가능
- 다른 모임 신청 가능

단, 재신청 시에도 새로운 신청으로 간주하여 다시 선착순 규칙을 적용한다.

이전에 신청했다는 이유로 자리를 보장하지 않는다.

---

## 2.3 정원

각 모임은 모집 정원을 가진다.

예:

```text
capacity = 10
```

정원 10명인 모임에는 활성 신청이 최대 10건만 존재해야 한다.

마지막 한 자리에 여러 사용자가 동시에 신청하더라도 **정확히 한 명만 성공**해야 한다.

---

## 2.4 Host 신청 제한

`host_enabled = true`라는 이유만으로 신청을 제한하지 않는다.

다음 두 개념을 반드시 구분한다.

```text
host_enabled = 모임을 개설할 수 있는 권한

MEETING_HOST = 실제 특정 모임의 Host
```

현재 유효한 모임의 실제 Host인 사용자는 다른 모임에 신청할 수 없다.

예:

```text
host_enabled = true
현재 유효한 모임의 Host 아님
→ 신청 가능
```

```text
현재 OPEN 모임의 실제 Host
→ 모든 모임 신청 불가
```

Admin도 동일한 신청 규칙을 적용한다.

---

## 2.5 관리자 신청

관리자는 관리 기능과 별개로 일반 신청자가 될 수 있다.

```text
admin_enabled = true
apply_enabled = true
현재 유효한 모임 Host 아님
```

이면 일반 사용자와 동일하게 모임 신청이 가능하다.

관리자라고 해서 다음 규칙을 우회하지 않는다.

- 1인 1모임
- 정원
- OPEN 여부
- Host 신청 제한
- 신청 가능 대상 여부

---

# 3. 기술 방향

## 3.1 기본 Stack

초기 구현은 다음 기술을 사용한다.

```text
Language
- Python

Web Framework
- FastAPI

Server-side Rendering
- Jinja2

Frontend Interaction
- HTMX
- 최소한의 Vanilla JavaScript

UI
- Bootstrap 5 계열
- System Font 우선

Database
- PostgreSQL

Migration
- Alembic

Container
- Docker

Deployment
- Kubernetes
```

---

# 4. Frontend / Backend 구조

Frontend SPA와 Backend API를 별도 프로젝트로 나누지 않는다.

다음과 같이 하나의 FastAPI 프로젝트 안에서 화면까지 관리한다.

```text
Browser
   │
   │ HTML / HTMX
   ▼
FastAPI
   │
   ├─ Jinja2 Rendering
   ├─ Login / Session
   ├─ Meeting
   ├─ Registration
   ├─ Admin
   ├─ Host
   └─ Image Upload
   │
   ▼
PostgreSQL
```

초기 버전에서는 다음을 사용하지 않는다.

- React
- Vue
- Angular
- WebSocket
- Redis
- Kafka
- Message Queue
- Microservice

---

# 5. 화면 디자인 원칙

UI는 **심플하고 가장 익숙한 일반 업무용 웹서비스 스타일**로 구현한다.

별도의 독특한 디자인 시스템을 만들지 않는다.

기본 UI는 Bootstrap 5 계열을 사용한다.

주요 디자인 원칙:

- 밝은 배경
- 흰색 Card
- 얇은 Border
- 적당한 여백
- Bootstrap 기본 Form
- Bootstrap 기본 Button
- Bootstrap Badge
- Bootstrap Table
- Bootstrap Modal은 꼭 필요한 경우에만 사용
- 과도한 Animation 금지
- 과도한 Color 사용 금지
- 아이콘은 꼭 필요한 곳에만 사용
- Desktop 우선이지만 Mobile에서도 깨지지 않는 Responsive Layout

기본 화면 폭:

```text
container / container-lg
```

를 사용한다.

---

# 6. 외부 CDN 의존 금지

로컬 개발 중 CDN 사용 여부는 자유롭게 검토할 수 있으나, 최종 사내 배포 시 외부 Internet 접근을 전제로 하지 않는다.

다음 Frontend Library는 최종적으로 프로젝트 내부 Static Resource로 제공하는 것을 우선한다.

```text
Bootstrap CSS
Bootstrap JS
HTMX
```

예:

```text
app/static/vendor/bootstrap/
app/static/vendor/htmx/
app/static/vendor/tui-editor/
```

사내 환경에서 승인된 공통 CDN이 있다면 그 정책을 우선한다.

---

# 7. WSL 로컬 개발 환경

초기 개발은 사용자 로컬 WSL에서 진행한다.

권장 구조:

```text
Windows
└─ WSL
   └─ project/
      ├─ app/
      ├─ migrations/
      ├─ tests/
      ├─ docker/
      ├─ k8s/
      ├─ requirements.txt 또는 pyproject.toml
      ├─ .env.example
      └─ README.md
```

WSL 내부에서 다음을 실행할 수 있어야 한다.

```text
Python
FastAPI
PostgreSQL
Docker
pytest
```

---

# 8. 로컬 PostgreSQL

로컬 개발 시 PostgreSQL은 다음 중 가장 단순한 방식을 사용한다.

우선안:

```text
Docker Compose PostgreSQL
```

예상 로컬 구성:

```text
FastAPI
    ↓
localhost PostgreSQL Container
```

사내 반입 후에는 DB Connection 설정만 사내 PostgreSQL로 변경할 수 있어야 한다.

DB 주소나 계정정보를 코드에 하드코딩하지 않는다.

---

# 9. 설정 관리

환경별 설정은 환경변수로 관리한다.

예:

```text
APP_ENV
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
DATABASE_USER
DATABASE_PASSWORD

SESSION_SECRET_KEY
SESSION_TIMEOUT

POLLING_INTERVAL_SECONDS

IMAGE_STORAGE_PATH
IMAGE_MAX_SIZE

TRUSTED_PROXY
```

로컬:

```text
.env
```

사내 K8s:

```text
ConfigMap
Secret
```

을 사용한다.

`.env` 실제 값은 Git Commit 대상에서 제외한다.

`.env.example`만 저장한다.

---

# 10. 사용자 및 조직정보

사용자 정보는 외부 인증 시스템에서 조회하지 않는다.

관리자가 사전에 DB에 등록한다.

조직 구조:

```text
PART
 └─ MODULE
      └─ MEMBER
```

PART는 MODULE보다 큰 단위이다.

한 MODULE은 하나의 PART에 속한다.

---

# 11. MEMBER

예상 구조:

```text
MEMBER

member_id PK

login_id UNIQUE
employee_no UNIQUE
name

module_id FK

host_enabled BOOLEAN
apply_enabled BOOLEAN
admin_enabled BOOLEAN
active BOOLEAN

last_login_ip
last_login_at

created_at
updated_at
```

---

# 12. 사용자 정보

관리자가 관리하는 사용자 정보:

- ID
- 사번
- 이름
- 파트
- 모듈
- 신청 가능 여부
- Host 가능 여부
- 관리자 여부
- 사용 여부

예:

```text
ID            honggd
사번          12345678
이름          홍길동
파트          A파트
모듈          A-1모듈
신청 가능     Y
Host 가능     Y
관리자        N
사용          Y
```

---

# 13. 로그인

로그인은 매우 단순하게 다음 두 값으로 한다.

```text
ID
사번
```

화면:

```text
ID     [                 ]
사번   [                 ]

       [ 로그인 ]
```

Backend는 다음 조건을 확인한다.

```text
login_id 일치
AND
employee_no 일치
AND
active = true
```

---

# 14. 로그인 실패

ID와 사번 중 어느 값이 잘못되었는지는 알려주지 않는다.

통합 메시지:

```text
ID 또는 사번을 확인해주세요.
```

---

# 15. Login IP

MEMBER에 다음 정보를 저장한다.

```text
last_login_ip
last_login_at
```

최초 로그인:

```text
last_login_ip IS NULL
→ 추가 확인 없이 로그인
→ 현재 IP 저장
```

동일 IP:

```text
현재 IP = last_login_ip
→ 정상 로그인
```

다른 IP:

```text
현재 IP != last_login_ip
→ 재확인 화면 표시
```

---

# 16. 다른 IP 로그인 확인

예:

```text
이전에 접속한 환경과 다른 환경에서 로그인하고 있습니다.

마지막 로그인
2026-08-19 18:32

현재 접속이 본인의 접속이 맞습니까?

[취소] [계속 로그인]
```

사용자가 계속 로그인을 선택하면:

```text
last_login_ip = 현재 IP
last_login_at = 현재 시각
```

으로 갱신한다.

IP 변경은 로그인 차단이 아니라 **추가 확인 Trigger**이다.

IP는 강한 본인인증 수단으로 간주하지 않는다.

---

# 17. LOGIN_HISTORY

최근 로그인 상태와 별개로 접속 기록을 남긴다.

```text
LOGIN_HISTORY

login_history_id PK
member_id FK
login_at
login_ip
ip_changed
login_result
```

예:

```text
SUCCESS
SUCCESS_AFTER_IP_CONFIRM
FAILED
```

사번 전체 등 민감정보는 Application Log에 남기지 않는다.

---

# 18. Session

로그인 성공 후에는 ID와 사번을 매 Request마다 보내지 않는다.

Session에는 최소:

```text
member_id
```

를 저장한다.

신청/취소 요청에서 Frontend가 전달하는 `member_id`를 신뢰하지 않는다.

현재 로그인 사용자는 항상 Session으로 판단한다.

---

# 19. K8s를 고려한 Session

특정 FastAPI Pod Memory에만 저장되는 Session은 사용하지 않는다.

초기에는 Signed Cookie 기반 Session을 우선 검토한다.

Cookie 보안:

```text
HttpOnly
Secure
SameSite
```

Session Secret은:

```text
Kubernetes Secret
```

으로 관리한다.

중요한 권한 및 업무 Rule은 매 Request 시 DB 최신값으로 다시 확인한다.

---

# 20. 서비스 진입 경로

## 일반 사용자

```text
/login
/meetings
```

일반 사용자는 `/meetings`에서 서비스의 대부분을 이용한다.

---

## Host

필요 시 Host 전용 기능은:

```text
/host
/host/meetings
```

에서 제공한다.

Host는 본인이 실제 Host로 등록된 모임에 대해서만 상세 신청자 정보 등을 확인할 수 있다.

---

## 관리자

관리 화면은 완전히 별도 Path로 분리한다.

```text
/admin
```

하위:

```text
/admin/members
/admin/meetings
/admin/meetings/{meeting_id}
/admin/meetings/{meeting_id}/edit
/admin/meetings/{meeting_id}/registrations
```

일반 사용자 화면에 Admin 메뉴를 반드시 노출할 필요는 없다.

단, Path를 숨기는 것은 보안이 아니다.

모든 `/admin/**` 요청에서 Backend가:

```text
admin_enabled = true
```

인지 검사한다.

---

# 21. 일반 사용자 화면

사용자 화면은 최대한 단순하게 한 화면 중심으로 구성한다.

예:

```text
[모임 신청]

내 신청
──────────────────────────
9월 13일 19:00
○○ 레스토랑

[신청 취소]
──────────────────────────


모임 목록

┌─────────────────────────┐
  9월 13일 19:00 ~ 21:00

  ○○ 레스토랑

  대표 메뉴: 파스타
  Host의 한마디: 편하게 이야기 나눠요!

  신청 7 / 10
  잔여 3명

  [신청하기]
└─────────────────────────┘
```

---

# 22. 일반 사용자 기능

일반 사용자는 다음 기능만 필요하다.

- 모임 목록 조회
- 모임 일시/장소/장소 링크 확인
- 대표 동네/대표 메뉴/Host의 한마디 확인
- 각 모임 신청현황 숫자 확인
- 모임 신청
- 본인의 현재 신청 확인
- 신청 취소
- 취소 후 재신청

---

# 23. 일반 사용자 신청현황

일반 사용자는 모든 공개 모임에 대해 다음 숫자를 확인할 수 있다.

```text
현재 신청인원
모집 정원
잔여 인원
```

예:

```text
모임 A     7 / 10     잔여 3
모임 B     8 / 8      마감
모임 C     2 / 6      잔여 4
```

각 모임의 신청자는 다음 정보까지 볼 수 있다.

```text
이름
ID
파트
모듈
```

신청자의 사번은 일반 사용자에게 노출하지 않는다.

---

# 24. Host 비공개

일반 사용자용 화면/API/HTML Fragment에는 Host 관련 정보를 포함하지 않는다.

노출 금지:

```text
host member_id
host login_id
host employee_no
host name
host part
host module
```

CSS로 단순히 숨기는 방식이 아니라 Backend 결과 자체에서 제외한다.

---

# 25. 관리자 화면

Admin은 `/admin`으로 직접 진입한다.

관리자 Dashboard는 전형적인 Bootstrap Admin 화면 형태로 구현한다.

예:

```text
Admin

[사용자 관리] [모임 관리]
```

복잡한 Sidebar Admin Template은 사용하지 않아도 된다.

Bootstrap Navbar + Container + Table 중심으로 구성한다.

---

# 26. 관리자 사용자 관리

```text
/admin/members
```

표시 예:

| 이름 | ID | 사번 | 파트 | 모듈 | 신청 | Host | Admin | 활성 |
|---|---|---|---|---|---|---|---|---|

기능:

- 사용자 등록
- 사용자 수정
- `apply_enabled` 변경
- `host_enabled` 변경
- `admin_enabled` 변경
- `active` 변경

---

# 27. 관리자 모임 관리

```text
/admin/meetings
```

관리자는 모든 모임을 볼 수 있다.

표시 예:

| 모임 | 시간 | Host | 신청 | 정원 | 상태 | 관리 |
|---|---|---|---:|---:|---|---|

관리자는 모든 모임을 편집할 수 있다.

즉 일반 사용자 화면과 달리 `/admin`에서:

- 모임 생성
- 장소 수정
- 시간 수정
- 설명 수정
- 이미지 수정
- 정원 수정
- 상태 수정
- Host 확인
- 신청자 명단 확인

을 할 수 있다.

---

# 28. Host 화면

Host 화면을 유지할 경우 다음 기능만 제공한다.

```text
/host/meetings
```

Host가 본인이 맡은 모임에 대해:

- 상세 정보 조회
- 신청 인원 확인
- 잔여 인원 확인
- 신청자 명단 확인

을 할 수 있다.

모임 편집 기능은 최종 정책에 따라:

```text
A안: Host도 본인 모임 수정 가능
B안: 수정은 Admin만 가능
```

중 하나를 선택할 수 있다.

**현재 단순화 우선 기본안은 모임 편집을 `/admin`에 집중시키는 것이다.**

Host에게 직접 편집이 꼭 필요한 경우에만 `/host/.../edit`를 추가한다.

---

# 29. MEETING

예상 구조:

```text
MEETING

meeting_id PK

place_name
place_url
neighborhood
representative_menu
host_message TEXT
start_at
end_at

capacity INTEGER
status

created_at
updated_at
```

---

# 30. 모임 상태

```text
DRAFT
OPEN
CLOSED
CANCELLED
```

신청 가능:

```text
OPEN
```

---

# 31. MEETING_HOST

```text
MEETING_HOST

meeting_id FK
member_id FK
```

한 모임당 Host 한 명으로 운영하면:

```text
UNIQUE(meeting_id)
```

를 사용한다.

---

# 32. 모임 콘텐츠

모임 콘텐츠는 Rich Text Editor나 이미지 없이 다음 구조화 필드로 관리한다.

```text
일시
장소
장소 바로가기 링크
대표 동네
대표 메뉴
Host의 한마디
```

`host_message`는 PostgreSQL `TEXT`로 저장한다. 이미지 업로드와 별도 Storage는 현재 범위에서 제외한다.

---

# 37. REGISTRATION

현재 활성 신청:

```text
REGISTRATION

registration_id PK
member_id FK
meeting_id FK
registered_at
```

핵심 Constraint:

```text
UNIQUE(member_id)
```

이를 통해 한 사람이 동시에 두 개 모임에 등록되지 못하도록 한다.

---

# 38. REGISTRATION_HISTORY

신청/취소 이력:

```text
REGISTRATION_HISTORY

history_id PK
member_id FK
meeting_id FK
action
created_at
```

action:

```text
APPLY
CANCEL
```

---

# 39. 신청 가능 Rule

다음 모든 조건을 만족해야 한다.

```text
member.active = true
AND
member.apply_enabled = true
AND
현재 유효 모임 Host가 아님
AND
현재 활성 Registration 없음
AND
대상 Meeting.status = OPEN
AND
현재 신청인원 < capacity
```

---

# 40. Frontend Rule

Frontend에서도 현재 상태에 맞게 버튼과 메시지를 정확하게 표현한다.

예:

### 신청 가능

```text
잔여 3명
[신청하기]
```

### 다른 모임 신청 중

```text
이미 다른 모임을 신청했습니다.
[신청 불가]
```

### Host

```text
현재 유효한 모임의 Host는 신청할 수 없습니다.
[신청 불가]
```

### 정원 마감

```text
모집이 마감되었습니다.
[마감]
```

---

# 41. Backend 중심 Rule 계산

Frontend에서 업무 Rule을 전부 JavaScript로 다시 구현하지 않는다.

Backend가 각 모임에 대해 현재 사용자 기준 상태를 계산한다.

예:

```text
meeting_id
capacity
applied_count
remaining_count
status

is_registered
can_apply
cannot_apply_reason
```

예:

```json
{
  "meetingId": 101,
  "capacity": 10,
  "appliedCount": 8,
  "remainingCount": 2,
  "isRegistered": false,
  "canApply": false,
  "cannotApplyReason": "ALREADY_REGISTERED"
}
```

Jinja2/HTMX는 이 결과를 그대로 표현한다.

---

# 42. Backend 최종 검증

Frontend가 `canApply = true`를 보여주고 있어도 실제 신청 시 Backend에서 최신 데이터로 모든 Rule을 다시 검사한다.

```text
신청 Request
 ↓
로그인 사용자 확인
 ↓
active 확인
 ↓
apply_enabled 확인
 ↓
유효 Host 여부
 ↓
현재 Registration 여부
 ↓
Meeting Lock
 ↓
OPEN 여부
 ↓
정원 확인
 ↓
Registration INSERT
 ↓
History INSERT
 ↓
COMMIT
```

Frontend 상태는 절대 최종 판정이 아니다.

---

# 43. 정원 동시성

다음 상황을 안전하게 처리해야 한다.

```text
정원 10
현재 9명

100명이 동시에 신청
```

결과:

```text
정확히 1명 추가 성공
최종 Registration = 10
```

---

# 44. PostgreSQL Lock

신청 시 Meeting Row Lock을 우선 사용한다.

예:

```sql
SELECT *
FROM meeting
WHERE meeting_id = :meeting_id
FOR UPDATE;
```

그 후 같은 Transaction에서:

1. 최신 활성 신청 수 확인
2. 정원 확인
3. Registration 생성

을 처리한다.

---

# 45. 동일 사용자 동시 신청

사용자가 서로 다른 두 모임을 거의 동시에 신청할 수 있다.

예:

```text
A 사용자가
모임 1 신청
모임 2 신청
동시에 요청
```

결과는:

```text
활성 Registration 정확히 1건
```

이어야 한다.

DB의:

```text
UNIQUE(member_id)
```

Constraint를 최종 방어선으로 사용한다.

Unique Conflict는 Application 오류가 아니라 정상적인 업무 Conflict로 처리한다.

---

# 46. 신청 실패 Code

Backend Reason Code 예:

```text
NOT_ELIGIBLE
HOST_NOT_ALLOWED
ALREADY_REGISTERED
MEETING_NOT_OPEN
MEETING_FULL
```

Frontend는 코드에 맞는 사용자 메시지를 표시한다.

---

# 47. 신청 취소

사용자는 자신의 활성 신청만 취소할 수 있다.

취소 Transaction:

```text
현재 Session 사용자
 ↓
본인 Registration 조회
 ↓
Registration DELETE
 ↓
REGISTRATION_HISTORY CANCEL INSERT
 ↓
COMMIT
```

다른 사용자의 Registration ID를 임의로 전달하여 취소할 수 없어야 한다.

---

# 48. Polling

WebSocket은 사용하지 않는다.

신청 화면에 머무르는 동안:

```text
5초 Polling
```

을 기본으로 한다.

최대 동시접속 200명 기준:

```text
200 / 5초
≈ 평균 40 Request/sec
```

수준이다.

본 서비스에서는 충분히 단순하게 처리 가능한 수준을 목표로 한다.

---

# 49. Polling 대상

Polling으로 갱신:

- 모임 상태
- 현재 신청인원
- 잔여 인원
- 본인의 신청 여부
- `can_apply`
- `cannot_apply_reason`

---

# 50. HTMX Polling

예:

```html
<div
    hx-get="/meetings/status-fragment"
    hx-trigger="every 5s"
    hx-swap="innerHTML">
</div>
```

화면 전체를 매번 Reload하지 않는다.

필요한 Fragment만 갱신한다.

---

# 51. 신청/취소 직후

5초를 기다리지 않는다.

신청 성공:

```text
신청
→ Backend 성공
→ 즉시 최신 상태 Refresh
→ Polling 계속
```

신청 실패:

```text
신청
→ Backend 실패
→ 실패 메시지
→ 즉시 최신 상태 Refresh
```

취소:

```text
취소
→ Backend 성공
→ 즉시 최신 상태 Refresh
→ 다른 모임 신청 가능
```

---

# 52. Polling과 최종 판정

다음 상황은 정상이다.

```text
화면:
잔여 1명

사용자가 신청 클릭

그 사이 다른 사용자가 먼저 신청

Backend:
잔여 0
```

결과:

```text
MEETING_FULL
```

을 반환하고 화면을 최신 상태로 갱신한다.

Polling의 목적은 사용자에게 최대한 최신 상태를 보여주는 것이며, 정합성 보장은 Backend와 DB의 책임이다.

---

# 53. 프로젝트 구조

초기 구조 예:

```text
meeting-app/
│
├─ app/
│   ├─ main.py
│   ├─ config.py
│   ├─ database.py
│   │
│   ├─ models/
│   │   ├─ organization.py
│   │   ├─ member.py
│   │   ├─ meeting.py
│   │   └─ registration.py
│   │
│   ├─ schemas/
│   │   ├─ meeting.py
│   │   └─ registration.py
│   │
│   ├─ services/
│   │   ├─ auth_service.py
│   │   ├─ eligibility_service.py
│   │   ├─ meeting_service.py
│   │   ├─ registration_service.py
│   │   └─ image_service.py
│   │
│   ├─ routers/
│   │   ├─ auth.py
│   │   ├─ meetings.py
│   │   ├─ host.py
│   │   ├─ admin.py
│   │   └─ images.py
│   │
│   ├─ templates/
│   │   ├─ base.html
│   │   ├─ login.html
│   │   ├─ meetings/
│   │   ├─ host/
│   │   └─ admin/
│   │
│   └─ static/
│       ├─ css/
│       ├─ js/
│       └─ vendor/
│
├─ migrations/
├─ tests/
├─ docker/
├─ k8s/
├─ data/
│   └─ uploads/        # local development only
│
├─ .env.example
├─ .gitignore
├─ pyproject.toml 또는 requirements.txt
├─ docker-compose.yml
├─ Dockerfile
└─ README.md
```

구조를 필요 이상으로 세분화하지 않는다.

---

# 54. EligibilityService

신청 가능 여부 관련 Rule은 여러 Endpoint에 복붙하지 않는다.

예:

```python
evaluate_apply_eligibility(member, meeting, db)
```

결과:

```text
allowed
reason
```

조회 화면에서도 같은 정책을 사용한다.

실제 신청 시에는 Transaction 안에서 **최신 데이터 기준으로 다시 호출/검증**한다.

---

# 55. API / Route 개념

## 인증

```text
GET  /login
POST /login
POST /login/confirm-ip
POST /logout
```

## 일반 사용자

```text
GET  /meetings
GET  /meetings/status-fragment
POST /meetings/{meeting_id}/apply
POST /registrations/cancel
```

## 이미지

```text
POST /api/images
```

## Host

```text
GET /host/meetings
GET /host/meetings/{meeting_id}/registrations
```

Host 편집 기능이 필요할 경우:

```text
GET  /host/meetings/{meeting_id}/edit
POST /host/meetings/{meeting_id}/edit
```

## Admin

```text
GET  /admin
GET  /admin/members
GET  /admin/members/new
POST /admin/members/new
GET  /admin/members/{member_id}/edit
POST /admin/members/{member_id}/edit

GET  /admin/meetings
GET  /admin/meetings/new
POST /admin/meetings/new
GET  /admin/meetings/{meeting_id}/edit
POST /admin/meetings/{meeting_id}/edit
GET  /admin/meetings/{meeting_id}/registrations
```

---

# 56. 권한 검사

URL이 분리되어 있어도 Backend 검사는 반드시 수행한다.

## `/admin/**`

```text
admin_enabled = true
```

필수.

아니면:

```text
403
```

## `/host/**`

Host 권한 또는 실제 Host 관계를 확인한다.

다른 Host의 신청자 목록은 조회할 수 없다.

---

# 57. Bootstrap UI 상세

## 일반 화면

Bootstrap Components:

```text
Navbar
Container
Card
Badge
Button
Alert
Form
Spinner
```

모임 하나당 `card` 한 개를 기본으로 한다.

신청현황:

```text
Badge
```

예:

```text
신청 7/10
잔여 3
```

마감:

```text
마감
```

Badge를 표시한다.

---

# 58. Admin UI 상세

관리 화면은 Table 중심으로 구성한다.

사용자 목록:

```text
table
table-striped
table-hover
```

모임 목록도 Table 중심.

편집 화면:

```text
form-control
form-select
btn-primary
btn-secondary
```

과도한 Dashboard Chart는 만들지 않는다.

---

# 59. 사용자 Feedback

신청 버튼 클릭 중:

```text
button disabled
spinner 표시
```

하여 중복 클릭을 줄인다.

신청 성공:

```text
신청이 완료되었습니다.
```

신청 실패:

```text
방금 모집이 마감되었습니다.
```

등 Backend Reason에 맞는 Bootstrap Alert 또는 Toast를 표시한다.

취소 시에는 실수를 줄이기 위해 간단한 확인 Dialog를 둘 수 있다.

---

# 60. 보안 기본사항

- HTTPS
- HttpOnly Session Cookie
- Secure Cookie
- SameSite
- CSRF 보호 검토 및 적용
- ID/사번을 URL Query String으로 보내지 않음
- 사번 Log 출력 금지
- Session Secret Git 저장 금지
- SQL 문자열 직접 조합 금지
- ORM / Parameter Binding 사용
- Rich Text HTML Sanitization
- 이미지 MIME Type 검증
- 이미지 Size 제한
- 실행 가능 파일 Upload 금지
- Admin/Host 권한 Backend 검사

---

# 61. K8s Architecture

사내 배포:

```text
Browser
   │
   ▼
Ingress
   │
   ▼
ClusterIP Service
   │
   ▼
FastAPI Deployment
   │
   ├─ PostgreSQL
   │
   └─ Shared Image Storage / PVC
```

---

# 62. Kubernetes Resource

최소:

```text
Deployment
Service
Ingress
ConfigMap
Secret
```

이미지 Persistent Storage 사용 시:

```text
PersistentVolumeClaim
```

추가.

---

# 63. Deployment

초기에는:

```text
replicas: 1
```

로 충분할 수 있다.

사내 운영 표준에서 HA를 요구하면:

```text
replicas: 2
```

를 적용한다.

Application이 특정 Pod에 종속되는 State를 가지지 않도록 설계한다.

---

# 64. K8s Secret

다음 값을 Secret으로 관리한다.

```text
DATABASE_USER
DATABASE_PASSWORD
SESSION_SECRET_KEY
```

Git에 실제 값을 넣지 않는다.

---

# 65. ConfigMap

예:

```text
APP_ENV
APP_PORT
DATABASE_HOST
DATABASE_PORT
DATABASE_NAME
POLLING_INTERVAL_SECONDS
SESSION_TIMEOUT
IMAGE_STORAGE_PATH
```

---

# 66. Health Check

Endpoint:

```text
/health/live
/health/ready
```

Kubernetes Probe에서 사용한다.

---

# 67. Logging

Application Log는:

```text
STDOUT / STDERR
```

로 출력한다.

K8s Log Collector에서 수집 가능하도록 한다.

최소 Audit Event:

- Login 성공
- Login 실패
- IP 변경 로그인
- 신청
- 취소
- 모임 생성
- 모임 수정
- 사용자 권한 변경

---

# 68. Client IP

K8s Ingress 뒤에서는 FastAPI Request IP가 실제 사용자의 IP가 아닐 수 있다.

사내 환경 반입 후 반드시 확인:

- Ingress Controller
- `X-Forwarded-For`
- `X-Real-IP`
- 신뢰 Proxy 설정

임의 Client가 보낸 Forwarded Header를 그대로 신뢰하지 않는다.

---

# 69. Alembic Migration

DB Schema 변경은 Alembic으로 관리한다.

Git에:

```text
migrations/
```

을 포함한다.

사내 반입 후 새 PostgreSQL에 동일 Schema를 생성할 수 있어야 한다.

---

# 70. Index

우선 검토:

```text
MEMBER.login_id
MEMBER.employee_no

MEETING.status

MEETING_HOST.member_id
MEETING_HOST.meeting_id

REGISTRATION.member_id
REGISTRATION.meeting_id
```

과도한 Index는 만들지 않는다.

---

# 71. 필수 Test

## Login

- 올바른 ID + 사번 성공
- 잘못된 조합 실패
- inactive 사용자 실패
- 최초 IP 성공
- 동일 IP 성공
- 다른 IP 추가확인
- 추가확인 후 last_login_ip 변경

## 신청

- 일반 사용자 신청 성공
- 1인 1모임
- 신청 취소
- 동일 모임 재신청
- 다른 모임 재신청
- Host 신청 제한
- Host 권한만 있고 실제 Host가 아니면 신청 가능
- Admin 신청 가능

## 정원

- 정원만큼 성공
- 정원 초과 실패
- 마지막 한 자리에 동시 요청 시 정확히 한 명 성공

## 동시성

- 동일 사용자 두 모임 동시 신청 → 하나만 성공
- 정원 10, 100명 동시 신청 → 정확히 10건
- 신청/취소 동시 발생에도 capacity 초과 없음

## 권한

- 일반 사용자 `/admin` → 403
- Host A가 Host B 신청자 조회 → 403
- Admin은 전체 모임 관리 가능

## Polling

- 다른 사용자 신청 후 5초 이내 숫자 반영
- 신청/취소 직후 즉시 갱신
- 화면 잔여정보가 오래된 경우 Backend 최종 검증

---

# 72. 로컬 Load Test

최대 동접 목표:

```text
약 200명
```

특히 다음 시나리오를 테스트한다.

```text
200명 모임 목록 조회
200명 5초 Polling
100명 동일 모임 동시 신청
```

목표는 극단적인 고성능이 아니라:

```text
오류 없음
정원 초과 없음
1인 1모임 위반 없음
화면 응답이 업무용으로 충분히 빠름
```

이다.

---

# 73. 개발 순서

## Phase 1

WSL 프로젝트 Skeleton 생성.

- FastAPI
- Jinja2
- Bootstrap
- HTMX
- Local PostgreSQL
- Alembic

## Phase 2

DB Model.

- PART
- MODULE
- MEMBER
- LOGIN_HISTORY
- MEETING
- MEETING_HOST
- REGISTRATION
- REGISTRATION_HISTORY

## Phase 3

Login / Session.

- ID + 사번
- IP 변경 확인
- Session
- Login History

## Phase 4

Admin 사용자 관리.

## Phase 5

Admin 모임 관리.

- Rich Text Editor
- Image Upload
- Meeting Host
- Capacity
- Status

## Phase 6

일반 사용자 모임 화면.

## Phase 7

신청 / 취소 Transaction.

## Phase 8

5초 Polling.

## Phase 9

Host 신청현황 화면.

## Phase 10

동시성 / Load / Security Test.

## Phase 11

Docker.

## Phase 12

사내 K8s Manifest 작성 및 환경별 설정 분리.

---

# 74. WSL 개발 완료 기준

사내 반입 전 WSL에서 최소 다음이 작동해야 한다.

```text
docker compose up PostgreSQL

FastAPI 실행

/login 접속

ID + 사번 Login

/admin 사용자 등록

/admin 모임 생성

Editor 이미지 Upload

일반 사용자 Login

모임 목록 조회

모임 신청

다른 모임 신청 차단

취소

재신청

5초 Polling

동시 신청 Test
```

---

# 75. 사내 반입 시 변경되어야 하는 부분

소스 자체를 크게 고치지 않고 설정만 교체하는 것을 목표로 한다.

주요 변경:

```text
Local PostgreSQL
→ 사내 PostgreSQL

Local Upload Directory
→ 사내 Shared Storage / PVC

Local Host
→ 사내 Ingress

.env
→ ConfigMap + Secret

개발 Client IP
→ 사내 Ingress 실제 Client IP 처리
```

업무 Logic은 변경하지 않는다.

---

# 76. Codex Plan Mode 지시사항

이 문서를 읽고 **바로 전체 코드를 생성하지 않는다.**

먼저 현재 작업 Directory와 환경을 조사한 뒤 구체적인 구현 Plan을 작성한다.

Plan에서 다음을 반드시 제시한다.

## 1. Architecture

최종 로컬 개발 Architecture 및 K8s 배포 Architecture.

## 2. Dependency

사용할 Python Package와 Frontend 오픈소스 Library.

불필요한 Dependency를 추가하지 않는다.

## 3. File Structure

생성할 전체 Directory/File 목록.

## 4. DB

실제 PostgreSQL Table / FK / UNIQUE / INDEX / CHECK Constraint 계획.

## 5. Authentication

ID + 사번 로그인, IP 변경 확인, Session 구현 방식.

## 6. Authorization

Admin / Host / 일반 사용자의 Route별 권한.

## 7. Meeting

모임 생성/수정/상태 관리.

## 8. Registration

신청/취소 Transaction과 Lock 순서.

특히 다음 두 상황을 정확하게 처리하는 계획을 작성한다.

```text
한 명이 두 모임에 동시에 신청
```

```text
마지막 한 자리에 여러 사용자가 동시에 신청
```

## 9. Frontend

Bootstrap 5 + Jinja2 + HTMX 기반 화면 구조.

Custom UI Framework를 추가하지 않는다.

## 10. Polling

5초 Polling Fragment 설계.

## 11. Image

로컬 Storage와 K8s Storage를 설정으로 교체할 수 있는 구조.

## 12. Tests

Unit / Integration / Concurrency / Load Test 계획.

## 13. Docker

로컬 및 사내 반입용 Container Build 계획.

## 14. Kubernetes

다음을 포함한다.

```text
Deployment
Service
Ingress
ConfigMap
Secret
PersistentVolumeClaim 필요 여부
Health Probe
Resource Request/Limit
```

## 15. Migration

Alembic 적용 계획.

Plan을 먼저 제시하고, 구현 시 작은 Phase 단위로 진행한다.

---

# 77. 절대 과설계하지 않을 것

현재 요구사항을 만족하기 위해 다음 기술을 새로 도입하지 않는다.

```text
React
Vue
Angular

WebSocket
Redis
Kafka
RabbitMQ

Celery

Microservice

별도 API Gateway

복잡한 CQRS/Event Sourcing

복잡한 Frontend State Management
```

필요성이 명확해지기 전에는 사용하지 않는다.

---

# 78. 최종 핵심 원칙

1. FastAPI + Jinja2 + HTMX + Bootstrap + PostgreSQL로 단순하게 구현한다.
2. WSL에서 먼저 완성하고 사내 K8s로 가져갈 수 있게 환경설정을 분리한다.
3. 일반 사용자는 일시/장소/동네/대표 메뉴/Host의 한마디, 신청현황과 신청자 이름/ID/파트/모듈을 확인한다.
4. 일반 사용자에게 Host 정보와 신청자 사번은 노출하지 않는다.
5. 사용자는 신청 및 취소가 가능하다.
6. 한 사람은 동시에 한 모임만 신청할 수 있다.
7. 취소 후 다시 신청할 수 있다.
8. 현재 유효한 모임의 실제 Host는 신청할 수 없다.
9. Admin은 별도 `/admin` 화면에서 사용자와 전체 모임을 관리한다.
10. Admin도 신청할 때는 일반 사용자와 동일한 Rule을 적용한다.
11. Frontend는 Backend가 계산한 `can_apply` 상태를 정확히 표현한다.
12. 실제 신청 시 Backend가 모든 Rule을 최신 데이터로 다시 검증한다.
13. PostgreSQL Transaction/Lock/Constraint가 최종 정합성을 보장한다.
14. WebSocket 대신 5초 Polling을 사용한다.
15. 신청/취소 직후에는 Polling을 기다리지 않고 즉시 화면을 갱신한다.
16. 최대 동접 약 200명을 기준으로 한다.
17. UI는 Bootstrap 기반의 가장 익숙한 업무용 웹 디자인을 사용한다.
18. 최종 사내 배포에서는 외부 CDN에 의존하지 않는다.
19. Kubernetes Pod Local State에 영구 데이터를 저장하지 않는다.
20. 구현의 최우선 가치는 단순성, 정확성, 사내 반입 용이성이다.
