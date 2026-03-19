import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    AgentChatRequest,
    AgentChatResponse,
    IngestPayload,
    IngestResponse,
    MlFailureModeRequest,
    MlFailureModeResponse,
    NodeFaultHistoryResponse,
    ResolveFaultRequest,
    ResolveFaultResponse,
    StatusResponse,
)
from shacklib.backend_state import ensure_storage_ready, read_state, update_state
from shacklib.codex_agent import run_codex_agent_chat
from shacklib.diagnosis_engine import (
    build_status_payload,
    build_node_fault_history_payload,
    ingest_node,
    resolve_fault,
    utc_now_iso,
)
from shacklib.ml_inference_client import (
    MLInferenceError,
    infer_failure_mode_for_node,
    resolve_ml_url,
)
from shacklib.state_seed import seed_state_on_startup

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.on_event("startup")
async def startup() -> None:
    ensure_storage_ready()
    seeded = update_state(seed_state_on_startup)
    if seeded:
        print("[backend-fastapi] seeded reproducible startup telemetry state")


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(payload: IngestPayload) -> IngestResponse:
    incoming = payload.model_dump(mode="python")

    def _mutator(state: dict):
        ingest_node(state, incoming)
        return IngestResponse(
            ok=True,
            nodeId=payload.nodeId,
            acceptedAt=utc_now_iso(),
        )

    return update_state(_mutator)


@app.get("/api/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    payload = update_state(build_status_payload)
    return StatusResponse.model_validate(payload)


@app.post("/api/faults/{fault_id}/resolve", response_model=ResolveFaultResponse)
async def resolve(fault_id: str, payload: ResolveFaultRequest) -> ResolveFaultResponse:
    def _mutator(state: dict):
        result = resolve_fault(
            state=state,
            fault_id=fault_id,
            resolved_by=payload.resolvedBy,
            note=payload.note,
        )
        if result is None:
            raise KeyError(fault_id)
        return ResolveFaultResponse.model_validate(result)

    try:
        return update_state(_mutator)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="fault not found") from exc


@app.get("/api/nodes/{node_id}/fault-history", response_model=NodeFaultHistoryResponse)
async def node_fault_history(
    node_id: str,
    limit: int = Query(default=25, ge=1, le=100),
) -> NodeFaultHistoryResponse:
    state = read_state()
    nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}

    if node_id not in nodes:
        raise HTTPException(status_code=404, detail="node not found")

    payload = build_node_fault_history_payload(state, node_id=node_id, limit=limit)
    return NodeFaultHistoryResponse.model_validate(payload)


@app.post("/api/ml/failure-mode", response_model=MlFailureModeResponse)
async def ml_failure_mode(payload: MlFailureModeRequest) -> MlFailureModeResponse:
    state = read_state()
    nodes = state.get("nodes") if isinstance(state.get("nodes"), dict) else {}
    node = nodes.get(payload.nodeId) if isinstance(nodes, dict) else None

    if not isinstance(node, dict):
        raise HTTPException(status_code=404, detail="node not found")

    timeout_seconds = payload.timeoutSeconds
    try:
        inference = infer_failure_mode_for_node(
            {"id": payload.nodeId, **node},
            timeout_seconds=timeout_seconds,
        )
    except MLInferenceError as exc:
        return MlFailureModeResponse(
            nodeId=payload.nodeId,
            generatedAt=utc_now_iso(),
            mlUrl=resolve_ml_url(),
            available=False,
            error=str(exc),
        )

    return MlFailureModeResponse(
        nodeId=payload.nodeId,
        generatedAt=utc_now_iso(),
        mlUrl=str(inference.get("mlUrl") or resolve_ml_url()),
        modelType=(
            str(inference.get("modelType"))
            if inference.get("modelType") is not None
            else None
        ),
        task=str(inference.get("task")) if inference.get("task") is not None else None,
        prediction=inference.get("prediction"),
        className=(
            str(inference.get("className"))
            if inference.get("className") is not None
            else None
        ),
        confidence=inference.get("confidence"),
        diagnosis=inference.get("diagnosis"),
    )


@app.post("/api/agent/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest) -> AgentChatResponse:
    response = run_codex_agent_chat(payload.model_dump(mode="python"))
    return AgentChatResponse.model_validate(response)


if __name__ == "__main__":
    PORT = int(os.getenv("BACKEND_PORT", 5000))
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
