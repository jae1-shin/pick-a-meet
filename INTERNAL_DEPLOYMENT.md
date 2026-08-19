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

## 처음 배포할 때 내가 실제로 할 일

아래 단계는 `kubectl` 대신 VMware K8s Console의 `Create from YAML`, `Import YAML`, `YAML로 생성` 같은 메뉴를 사용하는 기준입니다. Console 버전에 따라 메뉴 이름은 다르지만 생성할 Kubernetes 리소스 이름은 같습니다.

### 0단계: 다섯 가지 값을 메모한다

| 필요한 값 | 예시 | 어디서 받는가 |
|---|---|---|
| namespace | `pick-a-meet` | 직접 생성하거나 플랫폼 담당자에게 받음 |
| image 주소 | `registry.company/pick-a-meet/pick-a-meet:0.1.0` | 사내 registry에서 repository 생성 후 확인 |
| PostgreSQL | `10.0.0.20:5432`, DB `pick_a_meet` | DB 담당자 |
| 접속 주소 | `pick-a-meet.company.internal` | DNS/Gateway 담당자 |
| 노출 방식 | Gateway API 또는 Ingress | Console의 GatewayClass/IngressClass 목록 |

아직 모르는 값은 억지로 추측하지 말고 플랫폼 담당자에게 위 표 그대로 문의합니다.

### 1단계: container image를 만든다

Kubernetes는 GitHub 소스나 Dockerfile 자체를 실행하지 않습니다. Dockerfile로 먼저 container image를 만들고 사내 registry에 올려야 합니다.

사내 Console이나 CI에 `Build from Git`, `Build from Dockerfile`, `Container Build` 메뉴가 있으면 다음 값을 입력합니다.

```text
Repository: https://github.com/jae1-shin/pick-a-meet
Branch: main
Build context: .
Dockerfile: Dockerfile
Output image: 사내_REGISTRY/pick-a-meet/pick-a-meet:0.1.0
```

private GitHub 저장소이므로 build 도구에 GitHub credential을 연결해야 합니다. 그런 build 기능이 없다면 Docker가 설치된 사내 작업 PC나 CI에서 다음 세 명령을 실행합니다.

```bash
docker login 사내_REGISTRY
docker build -t 사내_REGISTRY/pick-a-meet/pick-a-meet:0.1.0 .
docker push 사내_REGISTRY/pick-a-meet/pick-a-meet:0.1.0
```

Dockerfile은 애플리케이션, Alembic migration, 최초 Admin 명령까지 image에 포함하도록 준비되어 있습니다. image가 registry 화면에 보이는 것을 확인한 뒤 다음 단계로 갑니다.

### 2단계: PostgreSQL을 한 번 준비한다

DB 담당자에게 다음처럼 요청해도 됩니다.

```text
pick_a_meet 전용 database와 pick_a_meet_app login role을 만들어 주세요.
pick_a_meet_app이 해당 database와 public schema의 owner가 되어
Alembic으로 table을 생성·변경할 수 있어야 합니다.
Kubernetes Pod 대역에서 PG_IP:5432 접근도 허용해 주세요.
```

직접 DBA 권한을 받았다면 [scripts/bootstrap_database.sql](scripts/bootstrap_database.sql)을 사용합니다. 완료 후 DB host, port, database, user, password를 메모합니다.

### 3단계: namespace를 만든다

Console에서 Cluster를 선택하고 `Namespaces`에서 `pick-a-meet`을 만듭니다. YAML 생성만 가능하면 [k8s/00-namespace.yaml](k8s/00-namespace.yaml)을 붙여넣습니다. 이미 지급된 namespace가 있다면 새로 만들지 말고 모든 YAML의 `namespace: pick-a-meet`을 지급된 이름으로 바꿉니다.

이후 작업 화면이 항상 이 namespace를 가리키는지 확인합니다. 다른 namespace에 Secret을 만들면 Pod가 읽지 못합니다.

### 4단계: ConfigMap을 만든다

[k8s/01-configmap.yaml](k8s/01-configmap.yaml)을 열고 다음 값만 수정합니다.

```yaml
DATABASE_HOST: 실제_PG_IP_또는_DNS
DATABASE_PORT: "실제_PORT"
DATABASE_NAME: 실제_DB_이름
```

Console의 `ConfigMaps`에서 YAML로 생성합니다. 여기에는 비밀번호를 넣지 않습니다.

### 5단계: 앱 Secret을 만든다

Console의 `Secrets`에서 Opaque/Generic Secret을 만들고 이름을 `pick-a-meet-secret`로 지정합니다. 다음 네 key를 추가합니다.

| key | 값 |
|---|---|
| `DATABASE_USER` | DB 앱 계정 |
| `DATABASE_PASSWORD` | DB 앱 계정 비밀번호 |
| `SESSION_SECRET_KEY` | 32자 이상의 긴 무작위 문자열 |
| `ADMIN_CONSOLE_PASSWORD` | 운영 Admin 메뉴 추가 비밀번호 |

YAML 방식이면 [k8s/02-app-secret.example.yaml](k8s/02-app-secret.example.yaml)의 `CHANGE_ME`를 바꿔 붙여넣습니다. 수정한 실제 Secret YAML 파일은 저장하거나 Git에 commit하지 않습니다.

사내 registry가 인증을 요구하면 Console의 `Registry Secret` 또는 `Image Pull Secret` 메뉴에서도 별도 credential을 만듭니다. `03`, `05`, `06` YAML의 `imagePullSecrets` 주석을 풀고 그 Secret 이름을 입력합니다. 정확한 registry Secret 종류와 credential은 사내 안내를 따릅니다.

### 6단계: DB migration Job을 실행한다

[k8s/03-migration-job.yaml](k8s/03-migration-job.yaml)의 image를 1단계에서 만든 실제 image 주소로 바꾸고 Console의 `Jobs`에서 YAML로 생성합니다.

```yaml
image: 사내_REGISTRY/pick-a-meet/pick-a-meet:0.1.0
```

Job 상태가 `Complete` 또는 `Succeeded`가 되어야 합니다. 실패하면 다음 단계로 가지 말고 Job의 `Logs`와 `Events`를 확인합니다.

```text
connection refused / timeout → DB IP·port·방화벽 확인
password authentication failed → Secret의 DB 계정 확인
permission denied for schema → DB owner/권한 확인
ImagePullBackOff → image 주소나 registry credential 확인
```

### 7단계: 최초 Admin 한 명을 만든다

[k8s/04-bootstrap-admin-secret.example.yaml](k8s/04-bootstrap-admin-secret.example.yaml)의 `CHANGE_ME` 값을 본인의 Knox ID, 사번, 이름, 파트, 모듈로 바꿔 Secret을 생성합니다. 이어서 [k8s/05-bootstrap-admin-job.yaml](k8s/05-bootstrap-admin-job.yaml)의 image를 실제 주소로 바꿔 Job을 생성합니다.

Job log에 `Bootstrap Admin is ready`가 나오고 상태가 `Complete`인지 확인합니다. 완료 후 개인정보가 들어 있는 `pick-a-meet-bootstrap-admin` Secret과 bootstrap Job은 Console에서 삭제해도 됩니다. 생성된 Admin 사용자는 DB에 남습니다.

### 8단계: 애플리케이션과 내부 Service를 만든다

[k8s/06-deployment.yaml](k8s/06-deployment.yaml)의 image를 실제 주소로 바꿔 Deployment를 생성하고, 이어서 [k8s/07-service.yaml](k8s/07-service.yaml)을 생성합니다.

Console에서 아래 상태를 확인합니다.

```text
Deployment desired 1 / ready 1
Pod Running / Ready 1/1
Service type ClusterIP, port 8000
```

Pod가 `Running`이어도 `Ready 0/1`이면 Pod의 Logs와 `/health/ready` probe event를 확인합니다. DB 연결이 안 되는 경우가 가장 흔합니다.

현재 캐시 구조에 맞춰 Deployment는 `replicas: 1`이고 업데이트 방식은 `Recreate`입니다. 운영 중 잠깐의 배포 중단을 허용하는 대신 동시에 두 Pod가 뜨지 않게 합니다.

### 9단계: 사내 접속 주소를 연결한다

Console에서 `GatewayClass`가 보이고 Gateway API를 사용할 수 있으면 다음 중 하나를 선택합니다.

- 플랫폼 팀의 공용 Gateway가 있음: [k8s/08-httproute.example.yaml](k8s/08-httproute.example.yaml)만 수정하여 생성
- 이 cluster에서 Gateway도 직접 생성: TLS Secret을 먼저 준비한 뒤 [k8s/08-gateway.example.yaml](k8s/08-gateway.example.yaml)과 HTTPRoute를 생성
- Gateway API가 없고 IngressClass가 있음: [k8s/08-ingress.example.yaml](k8s/08-ingress.example.yaml)을 수정하여 생성

세 방법을 동시에 적용하지 않습니다. `CHANGE_ME` 값은 GatewayClass/IngressClass, hostname, TLS Secret 정보로 교체합니다. `SESSION_COOKIE_SECURE=true`이므로 실제 사용자 접속은 HTTPS로 구성합니다.

### 10단계: 처음 접속해서 확인한다

브라우저에서 사내 hostname으로 접속해 7단계의 Knox ID와 사번으로 로그인합니다. Admin 메뉴를 누르고 5단계에서 정한 `ADMIN_CONSOLE_PASSWORD`를 입력합니다.

처음에는 다음만 확인하면 됩니다.

1. 로그인과 Admin unlock
2. 사용자 한 명 등록
3. 모임 하나 등록
4. 일반 사용자로 신청·취소
5. 두 브라우저에서 신청 인원이 5초 안에 자동 반영

여기까지 되면 기본 배포가 완료된 것입니다.

### 다음 버전을 배포할 때

1. 새 tag로 image를 build/push합니다. 예: `0.1.1`
2. 새 image가 migration을 포함하면 Job 이름도 `pick-a-meet-migration-v2`처럼 바꿔 실행합니다.
3. migration 성공 후 Deployment의 image tag를 새 버전으로 수정합니다.
4. 새 Pod가 Ready인지 확인합니다.
5. 문제가 있으면 이전 image tag로 되돌립니다. DB migration의 downgrade 가능 여부는 별도로 확인합니다.

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

Deployment보다 먼저 동일 release image로 `alembic upgrade head`를 한 번만 실행합니다. 여러 앱 Pod가 시작할 때 동시에 migration을 수행하게 만들지 않습니다. 현재 Dockerfile에는 `alembic.ini`와 `migrations/`가 포함되어 있습니다.

### Deployment와 Pod

- Deployment가 Pod를 관리하므로 Pod manifest는 직접 만들지 않습니다.
- 초기값은 `replicas: 1`로 고정합니다.
- container port는 `8000`입니다.
- `/health/live`를 liveness, `/health/ready`를 readiness probe로 사용합니다.
- ConfigMap과 Secret을 환경변수로 주입합니다.
- CPU/memory requests와 limits는 사내 quota에 맞춰 지정합니다.
- image는 `latest` 대신 release tag 또는 digest로 고정합니다.

신청 시작 시각과 Host 정보 공개 여부는 DB에 저장되고 프로세스 시작 시 메모리에 캐시됩니다. 따라서 현재 구조에서는 Uvicorn worker도 1개로 실행합니다. replica나 worker를 늘리는 작업은 공유 캐시 도입과 함께 진행합니다.

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

## 6. 사내 값을 받은 뒤 확정할 항목

- 사내 registry와 승인 base image
- 실제 namespace와 PostgreSQL 접속 정보
- GatewayClass/IngressClass, hostname, TLS Secret
- registry image pull credential 연결 방식
- DB TLS와 trusted proxy 실제 환경 검증

기본 Dockerfile, migration과 최초 Admin Job, ConfigMap/Secret/Deployment/Service 및 외부 연결 예시는 `k8s/`에 준비되어 있습니다. 위 값들을 받은 뒤 `CHANGE_ME`만 교체합니다.
