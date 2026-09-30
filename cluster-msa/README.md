# cluster-msa

Python 3.10+ / FastAPI / Docker / MSA 조건을 만족하는 "네트워킹 군집(클러스터) 제어" 백엔드 예시.

## 구조

```
cluster-msa/
├── gateway/            # 외부 진입점 (API Gateway) - 포트 8000
│   ├── app/main.py
│   ├── requirements.txt
│   └── Dockerfile
├── cluster-service/    # 클러스터 메타데이터 관리 - 포트 8001
│   ├── app/main.py
│   ├── requirements.txt
│   └── Dockerfile
├── node-service/       # 클러스터 소속 노드(인스턴스) 관리 - 포트 8002
│   ├── app/main.py
│   ├── requirements.txt
│   └── Dockerfile
└── docker-compose.yml
```

각 서비스는 독립된 FastAPI 앱 + 독립된 컨테이너로, 서로 HTTP(JSON)로만 통신한다.
gateway는 외부 요청을 받아 내부적으로 어떤 서비스가 몇 개 떠 있는지 몰라도 되게
cluster-service / node-service로 라우팅하거나, 둘의 응답을 조합해서 돌려준다.

## 로컬 실행

```bash
docker compose up --build
```

- gateway: http://localhost:8000/docs  (Swagger UI)
- cluster-service 단독: http://localhost:8001/docs
- node-service 단독: http://localhost:8002/docs

## 사용 흐름 예시

```bash
# 1. 클러스터 생성 (gateway를 통해)
curl -X POST http://localhost:8000/clusters \
  -H "Content-Type: application/json" \
  -d '{"name": "prod-web-cluster", "min_size": 1, "max_size": 5, "desired_capacity": 2}'
# → { "id": "xxxx-...", "status": "ACTIVE", ... }

# 2. 위에서 받은 cluster id로 노드 등록
curl -X POST http://localhost:8000/nodes \
  -H "Content-Type: application/json" \
  -d '{"cluster_id": "<위에서 받은 id>", "instance_type": "t3.micro"}'

# 3. 클러스터 스케일 조정 (desired_capacity 변경)
curl -X PATCH http://localhost:8000/clusters/<cluster_id>/scale \
  -H "Content-Type: application/json" \
  -d '{"desired_capacity": 4}'

# 4. 노드 정지 / 재시작
curl -X POST http://localhost:8000/nodes/<node_id>/stop
curl -X POST http://localhost:8000/nodes/<node_id>/start

# 5. 클러스터 + 소속 노드 상태를 한 번에 조회 (gateway가 두 서비스를 조합)
curl http://localhost:8000/clusters/<cluster_id>/summary
```

## 설계 포인트

- **서비스 분리 기준**: "클러스터 자체의 스펙(cluster-service)"과 "그 안에서 뜨고 내려가는
  개별 노드(node-service)"는 변경 빈도와 책임이 달라서 분리했다. 실제 AWS 환경이라면
  node-service 안에서 boto3로 EC2 / Auto Scaling Group API를 호출하는 자리다.
- **서비스 간 통신**: 지금은 단순 동기 HTTP(REST). 노드 수가 많아지고 이벤트가 잦아지면
  SQS/SNS나 EventBridge 같은 비동기 메시징으로 바꾸는 것도 고려할 만하다.
- **게이트웨이 조합 엔드포인트**: `/clusters/{id}/summary`처럼 화면 하나에 여러 서비스의
  데이터가 같이 필요한 경우, 프론트가 여러 번 호출하게 두지 않고 게이트웨이에서 한 번에
  조합해 내려준다 (BFF: Backend For Frontend 패턴의 축소판).
- **헬스체크**: 각 서비스에 `/health`를 두고 docker-compose의 `healthcheck`/`depends_on`으로
  기동 순서를 보장했다. AWS ECS에서도 동일한 개념(Target Group Health Check)을 쓴다.

## AWS에 올릴 때 매핑 아이디어

| 로컬 개념 | AWS 대응 |
|---|---|
| docker-compose service | ECS Service (Fargate) 또는 EKS Deployment |
| `cluster-net` 브리지 네트워크 | VPC 내부 서브넷 + 보안그룹 |
| gateway 컨테이너 | ALB 뒤의 ECS 서비스, 또는 API Gateway + ALB |
| 서비스 이름으로 통신 (`http://cluster-service:8000`) | ECS Service Discovery(Cloud Map) 또는 내부 ALB/DNS |
| `docker compose up` | `docker push` → ECR → ECS 서비스 업데이트(CI/CD) |

각 폴더(gateway / cluster-service / node-service)를 각각 ECR 리포지토리로 빌드·푸시하고,
서비스 3개를 ECS(Fargate)나 EKS에 개별 배포한 뒤 같은 VPC/네임스페이스로 묶으면
지금 구조를 거의 그대로 옮길 수 있다.

## 다음에 해볼 만한 것

- 인메모리 저장소 → RDS(PostgreSQL) 또는 DynamoDB로 교체 (재시작 시 상태 유지)
- node-service 안에서 boto3로 실제 EC2 인스턴스 start/stop 호출
- gateway에 인증(JWT) 미들웨어 추가
- pytest + httpx AsyncClient로 각 서비스 단위 테스트 추가
