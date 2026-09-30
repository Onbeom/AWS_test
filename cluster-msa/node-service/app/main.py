"""
node-service
------------
클러스터에 속한 개별 노드(인스턴스)의 상태를 관리하는 마이크로서비스.
- 노드 등록(register) / 조회 / 시작 / 정지 / 종료
실제 AWS 환경이라면 boto3로 EC2 API를 호출하는 자리지만,
예시에서는 상태 전이만 시뮬레이션한다.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from enum import Enum

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="node-service",
    description="클러스터에 속한 노드(인스턴스)의 상태 관리",
    version="1.0.0",
)


class NodeState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    TERMINATED = "TERMINATED"


class NodeCreate(BaseModel):
    cluster_id: str = Field(..., description="이 노드가 속한 클러스터의 id")
    instance_type: str = Field(default="t3.micro")


class Node(BaseModel):
    id: str
    cluster_id: str
    instance_type: str
    state: NodeState
    private_ip: str
    created_at: datetime


_nodes: dict[str, Node] = {}


def _fake_private_ip() -> str:
    return f"10.0.{random.randint(0, 255)}.{random.randint(1, 254)}"


@app.get("/health")
def health() -> dict:
    return {"service": "node-service", "status": "ok"}


@app.post("/nodes", response_model=Node, status_code=201)
def register_node(payload: NodeCreate) -> Node:
    node = Node(
        id=str(uuid.uuid4()),
        cluster_id=payload.cluster_id,
        instance_type=payload.instance_type,
        state=NodeState.RUNNING,
        private_ip=_fake_private_ip(),
        created_at=datetime.now(timezone.utc),
    )
    _nodes[node.id] = node
    return node


@app.get("/nodes", response_model=list[Node])
def list_nodes(cluster_id: str | None = Query(default=None)) -> list[Node]:
    nodes = list(_nodes.values())
    if cluster_id:
        nodes = [n for n in nodes if n.cluster_id == cluster_id]
    return nodes


@app.get("/nodes/{node_id}", response_model=Node)
def get_node(node_id: str) -> Node:
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, "노드를 찾을 수 없습니다.")
    return node


@app.post("/nodes/{node_id}/start", response_model=Node)
def start_node(node_id: str) -> Node:
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, "노드를 찾을 수 없습니다.")
    if node.state == NodeState.TERMINATED:
        raise HTTPException(400, "종료된 노드는 다시 시작할 수 없습니다.")
    node.state = NodeState.RUNNING
    _nodes[node_id] = node
    return node


@app.post("/nodes/{node_id}/stop", response_model=Node)
def stop_node(node_id: str) -> Node:
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, "노드를 찾을 수 없습니다.")
    if node.state == NodeState.TERMINATED:
        raise HTTPException(400, "종료된 노드는 정지할 수 없습니다.")
    node.state = NodeState.STOPPED
    _nodes[node_id] = node
    return node


@app.delete("/nodes/{node_id}", response_model=Node)
def terminate_node(node_id: str) -> Node:
    node = _nodes.get(node_id)
    if not node:
        raise HTTPException(404, "노드를 찾을 수 없습니다.")
    node.state = NodeState.TERMINATED
    _nodes[node_id] = node
    return node
