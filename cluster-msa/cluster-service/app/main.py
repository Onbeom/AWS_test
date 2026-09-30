"""
cluster-service
---------------
클러스터(군집) 자체의 생명주기를 관리하는 마이크로서비스.
- 클러스터 생성/조회/삭제
- desired_capacity(원하는 노드 수) 스케일 조정
실제 서비스에서는 DB(RDS/DynamoDB)를 쓰지만, 예시에서는 인메모리 딕셔너리를 사용한다.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(
    title="cluster-service",
    description="클러스터(군집) 메타데이터 및 스케일링 상태 관리",
    version="1.0.0",
)


class ClusterStatus(str, Enum):
    PROVISIONING = "PROVISIONING"
    ACTIVE = "ACTIVE"
    SCALING = "SCALING"
    DELETING = "DELETING"


class ClusterCreate(BaseModel):
    name: str = Field(..., examples=["prod-web-cluster"])
    region: str = Field(default="ap-northeast-2")
    min_size: int = Field(default=1, ge=0)
    max_size: int = Field(default=5, ge=1)
    desired_capacity: int = Field(default=1, ge=0)


class ScaleRequest(BaseModel):
    desired_capacity: int = Field(..., ge=0)


class Cluster(BaseModel):
    id: str
    name: str
    region: str
    min_size: int
    max_size: int
    desired_capacity: int
    status: ClusterStatus
    created_at: datetime


# 인메모리 저장소 (실서비스에서는 RDS/DynamoDB 등으로 교체)
_clusters: dict[str, Cluster] = {}


@app.get("/health")
def health() -> dict:
    return {"service": "cluster-service", "status": "ok"}


@app.post("/clusters", response_model=Cluster, status_code=201)
def create_cluster(payload: ClusterCreate) -> Cluster:
    if payload.min_size > payload.max_size:
        raise HTTPException(400, "min_size는 max_size보다 클 수 없습니다.")
    if not (payload.min_size <= payload.desired_capacity <= payload.max_size):
        raise HTTPException(400, "desired_capacity는 min_size와 max_size 사이여야 합니다.")

    cluster = Cluster(
        id=str(uuid.uuid4()),
        name=payload.name,
        region=payload.region,
        min_size=payload.min_size,
        max_size=payload.max_size,
        desired_capacity=payload.desired_capacity,
        status=ClusterStatus.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    _clusters[cluster.id] = cluster
    return cluster


@app.get("/clusters", response_model=list[Cluster])
def list_clusters() -> list[Cluster]:
    return list(_clusters.values())


@app.get("/clusters/{cluster_id}", response_model=Cluster)
def get_cluster(cluster_id: str) -> Cluster:
    cluster = _clusters.get(cluster_id)
    if not cluster:
        raise HTTPException(404, "클러스터를 찾을 수 없습니다.")
    return cluster


@app.patch("/clusters/{cluster_id}/scale", response_model=Cluster)
def scale_cluster(cluster_id: str, payload: ScaleRequest) -> Cluster:
    cluster = _clusters.get(cluster_id)
    if not cluster:
        raise HTTPException(404, "클러스터를 찾을 수 없습니다.")
    if not (cluster.min_size <= payload.desired_capacity <= cluster.max_size):
        raise HTTPException(
            400,
            f"desired_capacity는 {cluster.min_size}~{cluster.max_size} 범위여야 합니다.",
        )
    cluster.desired_capacity = payload.desired_capacity
    cluster.status = ClusterStatus.SCALING
    _clusters[cluster_id] = cluster
    return cluster


@app.delete("/clusters/{cluster_id}", status_code=204, response_model=None)
def delete_cluster(cluster_id: str):
    if cluster_id not in _clusters:
        raise HTTPException(404, "클러스터를 찾을 수 없습니다.")
    del _clusters[cluster_id]
