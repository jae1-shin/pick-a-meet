# Pick a Meet 사내 배포 전략

이 문서는 이미 운영 중인 사내 PostgreSQL과 Kubernetes를 사용해 Pick a Meet을 처음 설치하는 순서를 정리합니다. 초기 운영은 애플리케이션 `replica: 1`을 전제로 합니다.

## VMware와 Photon OS 환경에서의 의미

Photon OS는 대개 VMware 기반 Kubernetes worker node의 운영체제입니다. Pick a Meet이 Photon OS에 직접 package를 설치하는 구조는 아닙니다. Kubernetes가 사내 registry의 OCI container image를 내려받아 실행하므로 다음 원칙을 따릅니다.

- Photon node에 SSH하여 Python이나 애플리케이션을 직접 설치하지 않음
- 일반 Kubernetes Deployment, Service, ConfigMap, Secret을 그대로 사용
- 현재 `python:3.12-slim` image도 기술적으로 실행 가능하지만, 사내 승인 base image나 mirror 사용 여부를 확인
- node OS 업데이트와 container runtime 관리는 플랫폼 운영팀의 영역으로 둠
- 애플리케이션 팀은 namespace 안의 workload와 외부 PostgreSQL 연결만 관리

`Photon`이라는 이름만으로 Tanzu 제품 종류나 외부 노출 방식을 확정할 수는 없습니다. 배포 권한을 받은 뒤 아래 결과를 플랫폼 담당자와 함께 확인합니다.

```bash
kubectl version
kubectl get nodes -o wide
kubectl get nodes \
  -o custom-columns='NAME:.metadata.name,OS:.status.nodeInfo.osImage,RUNTIME:.status.nodeInfo.containerRuntimeVersion,KUBELET:.status.nodeInfo.kubeletVersion'
kubectl get namespace
kubectl get ingressclass
kubectl get gatewayclass
kubectl api-resources
kubectl auth can-i create deployments -n PICK_A_MEET_NAMESPACE
kubectl auth can-i create httproutes.gateway.networking.k8s.io -n PICK_A_MEET_NAMESPACE
```

`GatewayClass`와 HTTPRoute API가 있으면 Gateway API 구성을 검토하고, 없고 `IngressClass`만 있으면 사내 표준 Ingress를 사용합니다. 공용 Gateway는 플랫폼 팀이 관리하고 애플리케이션 namespace에는 HTTPRoute만 허용하는 환경도 흔하므로 권한 결과를 기준으로 결정합니다.

## 1. 먼저 받아야 할 정보

다음 값이 정해져야 실제 manifest를 확정할 수 있습니다.

- Kubernetes namespace 이름과 생성 권한
- 사내 container registry 주소와 image 반입 방법
- 외부 PostgreSQL의 host, port, TLS 사용 여부
- PostgreSQL DBA 작업 요청 절차 또는 `CREATEROLE`, `CREATEDB` 권한이 있는 초기화 계정
- 애플리케이션 전용 DB 이름, 사용자 이름과 비밀번호
- 사내 Gateway 이름, namespace, Gateway API 사용 여부와 서비스 hostname
- TLS 인증서 발급·연결 방식
- Pod에서 PostgreSQL IP/port로 나가는 NetworkPolicy 또는 방화벽 허용 여부
- Secret 관리 방식과 CPU/memory quota

IP와 port에 접속할 수 있다는 사실만으로 DB를 만들 수 있는 것은 아닙니다. PostgreSQL의 `pg_hba.conf` 또는 사내 접근제어, DB 사용자 인증, DB/role 생성 권한까지 필요합니다.

## 2. 기존 PostgreSQL 준비

### 권장 구성

- 전용 database: `pick_a_meet`
- 전용 login role: `pick_a_meet_app`
- 애플리케이션 role이 해당 database와 `public` schema의 소유자
- superuser, role 생성, 다른 DB 생성 권한은 부여하지 않음

작은 사내 서비스의 첫 배포에서는 앱 계정을 migration 계정과 함께 사용해도 됩니다. 사내 정책상 권한 분리가 필수라면 migration 전용 owner와 제한된 runtime role을 별도로 설계해야 합니다.

DBA 계정으로 다음 명령을 실행합니다. 앱 계정 비밀번호는 명령행에 남기지 않고 script가 대화식으로 입력받습니다.

```bash
psql "host=PG_IP port=PG_PORT dbname=postgres user=DBA_USER sslmode=prefer" \
  -v app_database=pick_a_meet \
  -v app_user=pick_a_meet_app \
  -f scripts/bootstrap_database.sql
```

사내 DB가 TLS를 강제한다면 `sslmode=require`와 사내 CA 설정을 사용합니다. DBA 권한을 받을 수 없다면 같은 SQL 작업을 DBA에게 요청하면 됩니다.

그다음 애플리케이션 환경변수로 연결하여 schema migration을 한 번 실행합니다.

```bash
export DATABASE_HOST=PG_IP
export DATABASE_PORT=PG_PORT
export DATABASE_NAME=pick_a_meet
export DATABASE_USER=pick_a_meet_app
export DATABASE_PASSWORD='ISSUED_SECRET'
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Alembic이 모든 테이블과 제약조건을 생성하므로 운영에서 `Base.metadata.create_all()`이나 수동 DDL을 섞지 않습니다. `scripts/seed_demo.py`는 개발용 계정과 신청 데이터를 만들기 때문에 운영 DB에서는 실행하지 않습니다.

현재는 운영 최초 Admin을 생성하는 별도 import/bootstrap 명령이 없습니다. 배포 전 다음 중 하나를 확정해야 합니다.

1. 승인된 사용자 명단 파일을 한 번 import하는 명령 추가
2. 최소 최초 Admin 한 명만 만드는 일회성 명령 추가 후 Admin 화면에서 나머지 등록

## 3. Kubernetes 리소스 구성

```text
사내 Gateway
  → HTTPRoute (또는 사내 표준 Ingress)
    → Service: pick-a-meet, ClusterIP:8000
      → Deployment: pick-a-meet, replica 1
        → Pod
          ├─ ConfigMap: 비밀이 아닌 설정
          ├─ Secret: DB 계정·세션 key·Admin 비밀번호
          └─ 외부 PostgreSQL IP:port

배포 전에 migration Job → 외부 PostgreSQL에 alembic upgrade head
```

### Namespace

Pick a Meet 리소스의 범위와 권한·quota를 분리합니다. 사내에서 namespace가 이미 지급된다면 새로 만들지 않고 그 값을 사용합니다.

### ConfigMap

비밀이 아닌 다음 값을 둡니다.

- `APP_ENV=production`
- `APP_HOST=0.0.0.0`, `APP_PORT=8000`
- `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_NAME`
- `SESSION_TIMEOUT_SECONDS`
- `SESSION_COOKIE_SECURE=true`
- `POLLING_INTERVAL_SECONDS=5`
- 검증 완료 후의 `TRUSTED_PROXY` 값

### Secret

Git에 실제 값을 저장하지 않고 사내 Secret 관리 도구로 다음 값을 주입합니다.

- `DATABASE_USER`, `DATABASE_PASSWORD`
- 32자 이상 무작위 `SESSION_SECRET_KEY`
- 운영용 `ADMIN_CONSOLE_PASSWORD`

모든 Pod가 동일한 `SESSION_SECRET_KEY`를 사용해야 재시작이나 Pod 교체 후에도 Cookie 검증이 일관됩니다.

### Migration Job

Deployment보다 먼저 동일 release image로 `alembic upgrade head`를 한 번만 실행합니다. 여러 앱 Pod가 시작할 때 동시에 migration을 수행하게 만들지 않습니다. 현재 Dockerfile은 migration 파일을 image에 복사하지 않으므로 실제 manifest 작성 전에 `alembic.ini`와 `migrations/`를 포함하도록 보완해야 합니다.

### Deployment와 Pod

- Deployment가 Pod를 관리하므로 Pod manifest는 직접 만들지 않습니다.
- 초기값은 `replicas: 1`로 고정합니다.
- container port는 `8000`입니다.
- `/health/live`를 liveness, `/health/ready`를 readiness probe로 사용합니다.
- ConfigMap과 Secret을 환경변수로 주입합니다.
- CPU/memory requests와 limits는 사내 quota에 맞춰 지정합니다.
- image는 `latest` 대신 release tag 또는 digest로 고정합니다.

신청 시작 시각은 DB에 저장되고 프로세스 시작 시 메모리에 캐시됩니다. 따라서 현재 구조에서는 Uvicorn worker도 1개로 실행합니다. replica나 worker를 늘리는 작업은 공유 캐시 도입과 함께 진행합니다.

### Service

`ClusterIP` Service가 Deployment Pod의 8000번 port를 내부에 노출합니다. 외부 PostgreSQL은 Kubernetes에 배포하지 않으므로 PostgreSQL용 StatefulSet이나 Pod는 만들지 않습니다.

### Gateway와 HTTPRoute

사내 공용 Gateway가 이미 있다면 애플리케이션이 Gateway 자체를 만들기보다 `HTTPRoute`만 만들고 `parentRefs`로 연결하는 구성이 일반적입니다. hostname과 TLS는 사내 플랫폼 담당자가 제공한 값을 사용합니다. 사내 표준이 Ingress라면 HTTPRoute와 Ingress를 동시에 만들지 말고 Ingress 하나만 사용합니다.

### NetworkPolicy와 방화벽

다음 통신을 허용해야 합니다.

- Gateway/Ingress → Service의 TCP 8000
- 애플리케이션 Pod → PostgreSQL IP와 port
- DNS가 필요한 경우 kube-dns

인터넷 egress는 애플리케이션 실행에 필요하지 않도록 dependency와 글꼴을 image에 포함합니다.

## 4. 권장 배포 순서

1. DB IP/port 접근과 TLS를 임시 Pod 또는 승인된 작업 서버에서 확인
2. DBA가 전용 DB와 role 생성
3. namespace, ConfigMap, Secret 준비
4. release image를 사내 registry에 push
5. migration Job 실행 후 성공과 Alembic revision 확인
6. Deployment를 `replica: 1`, worker 1로 배포
7. Service와 HTTPRoute 또는 Ingress 연결
8. liveness/readiness와 Pod log 확인
9. 최초 Admin을 준비하고 로그인·Admin unlock 확인
10. 일반 사용자 신청·취소와 두 브라우저 자동 갱신 smoke test

## 5. 역할별 소유 관계

| 대상 | 역할 |
|---|---|
| Namespace | 모든 앱 리소스의 범위와 권한 분리 |
| ConfigMap | 공개 가능한 실행 설정 |
| Secret | DB credential, Cookie 서명 key, Admin 비밀번호 |
| Migration Job | release마다 DB schema를 한 번 업그레이드 |
| Deployment | replica 수, image, 환경변수, probe 선언 |
| Pod | Deployment가 실제로 생성하는 실행 단위 |
| Service | Pod를 안정적인 내부 주소로 묶음 |
| Gateway | 사내 외부 트래픽과 TLS의 진입점 |
| HTTPRoute | hostname/path를 Pick a Meet Service에 연결 |
| 외부 PostgreSQL | 영구 데이터 저장; Kubernetes 안에 새로 만들지 않음 |

## 6. 아직 만들어야 할 배포 산출물

- 사내 registry/base image에 맞춘 Dockerfile 보완
- ConfigMap, Secret key 목록, Deployment, Service manifest
- 사내 Gateway 정보가 반영된 HTTPRoute 또는 Ingress
- migration Job manifest
- 운영 최초 Admin 또는 사용자 일괄 import 명령
- DB TLS와 trusted proxy 실제 환경 검증

이 값들은 사내 namespace, Gateway, registry, PostgreSQL 정책을 받은 뒤 확정하는 것이 안전합니다.
