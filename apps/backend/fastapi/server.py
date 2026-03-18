import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from schemas import (
    IngestPayload,
    IngestResponse,
    ResolveFaultRequest,
    ResolveFaultResponse,
    StatusResponse,
)
from shacklib.backend_state import ensure_storage_ready, read_state, update_state
from shacklib.diagnosis_engine import (
    build_status_payload,
    ingest_node,
    resolve_fault,
    utc_now_iso,
)

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
    payload = build_status_payload(read_state())
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


if __name__ == "__main__":
    PORT = int(os.getenv("BACKEND_PORT", 5000))
    uvicorn.run("server:app", host="0.0.0.0", port=PORT, reload=True)
