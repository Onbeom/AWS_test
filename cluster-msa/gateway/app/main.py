"""
gateway
-------
외부에서 들어오는 요청의 단일 진입점(API Gateway).
- /clusters/*  요청은 cluster-service로 라우팅
- /nodes/*     요청은 node-service로 라우팅
- /clusters/{id}/summary 는 두 서비스의 응답을 조합(aggregation)해서 반환
  → MSA에서 게이트웨이가 여러 서비스를 합쳐 하나의 응답으로 만드는 전형적인 패턴.
"""
from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException, Request, Response

app = FastAPI(
    title="gateway",
    description="클러스터 제어 API의 단일 진입점",
    version="1.0.0",
)

# docker-compose 내부에서는 서비스 이름으로 접근한다 (예: http://cluster-service:8000)
CLUSTER_SERVICE_URL = os.getenv("CLUSTER_SERVICE_URL", "http://localhost:8001")
NODE_SERVICE_URL = os.getenv("NODE_SERVICE_URL", "http://localhost:8002")

_client = httpx.AsyncClient(timeout=5.0)


@app.get("/health")
async def health() -> dict:
    return {"service": "gateway", "status": "ok"}


async def _proxy(method: str, base_url: str, path: str, request: Request) -> Response:
    url = f"{base_url}{path}"
    body = await request.body()
    try:
        upstream = await _client.request(
            method,
            url,
            params=request.query_params,
            content=body,
            headers={"content-type": "application/json"} if body else None,
        )
    except httpx.ConnectError as exc:
        raise HTTPException(503, f"업스트림 서비스에 연결할 수 없습니다: {url}") from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/json"),
    )


# ---------- cluster-service 라우팅 ----------

@app.api_route("/clusters", methods=["GET", "POST"])
async def clusters_root(request: Request) -> Response:
    return await _proxy(request.method, CLUSTER_SERVICE_URL, "/clusters", request)


@app.api_route("/clusters/{cluster_id}", methods=["GET", "DELETE"])
async def clusters_item(cluster_id: str, request: Request) -> Response:
    return await _proxy(request.method, CLUSTER_SERVICE_URL, f"/clusters/{cluster_id}", request)


@app.api_route("/clusters/{cluster_id}/scale", methods=["PATCH"])
async def clusters_scale(cluster_id: str, request: Request) -> Response:
    return await _proxy(request.method, CLUSTER_SERVICE_URL, f"/clusters/{cluster_id}/scale", request)


# ---------- node-service 라우팅 ----------

@app.api_route("/nodes", methods=["GET", "POST"])
async def nodes_root(request: Request) -> Response:
    return await _proxy(request.method, NODE_SERVICE_URL, "/nodes", request)


@app.api_route("/nodes/{node_id}", methods=["GET", "DELETE"])
async def nodes_item(node_id: str, request: Request) -> Response:
    return await _proxy(request.method, NODE_SERVICE_URL, f"/nodes/{node_id}", request)


@app.api_route("/nodes/{node_id}/start", methods=["POST"])
async def nodes_start(node_id: str, request: Request) -> Response:
    return await _proxy(request.method, NODE_SERVICE_URL, f"/nodes/{node_id}/start", request)


@app.api_route("/nodes/{node_id}/stop", methods=["POST"])
async def nodes_stop(node_id: str, request: Request) -> Response:
    return await _proxy(request.method, NODE_SERVICE_URL, f"/nodes/{node_id}/stop", request)


# ---------- 조합(aggregation) 엔드포인트 ----------

@app.get("/clusters/{cluster_id}/summary")
async def cluster_summary(cluster_id: str) -> dict:
    """cluster-service의 클러스터 정보 + node-service의 소속 노드 목록을 합쳐서 반환한다."""
    cluster_resp = await _client.get(f"{CLUSTER_SERVICE_URL}/clusters/{cluster_id}")
    if cluster_resp.status_code == 404:
        raise HTTPException(404, "클러스터를 찾을 수 없습니다.")
    cluster_resp.raise_for_status()

    nodes_resp = await _client.get(f"{NODE_SERVICE_URL}/nodes", params={"cluster_id": cluster_id})
    nodes_resp.raise_for_status()

    cluster = cluster_resp.json()
    nodes = nodes_resp.json()
    running = sum(1 for n in nodes if n["state"] == "RUNNING")

    return {
        "cluster": cluster,
        "nodes": nodes,
        "node_count": len(nodes),
        "running_count": running,
    }


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await _client.aclose()
