from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Callable, TypeVar

try:
    import psycopg
    from psycopg.types.json import Json
except ModuleNotFoundError:  # pragma: no cover - exercised in no-DB local runs
    psycopg = None
    Json = None

State = dict[str, Any]
T = TypeVar("T")
_SCHEMA_READY = False
_MEMORY_STATE: State | None = None


def _empty_state() -> State:
    return {
        "nodes": {},
        "faults": {},
        "catalog": {
            "deviceTemplates": [],
            "zones": [],
            "ahuUnits": [],
            "faultMetaByDeviceId": {},
        },
        "meta": {
            "lastIngestAt": None,
            "lastClassificationAt": None,
            "lastFaultResolutionAt": None,
            "seedSource": None,
            "seededAt": None,
        },
        "agent": {
            "pendingActions": {},
            "auditLog": [],
        },
    }


def _normalize_state(state: Any) -> State:
    if not isinstance(state, dict):
        return _empty_state()

    state.setdefault("nodes", {})
    state.setdefault("faults", {})
    state.setdefault("catalog", {})
    state.setdefault("meta", {})
    state.setdefault("agent", {})

    if not isinstance(state["nodes"], dict):
        state["nodes"] = {}
    if not isinstance(state["faults"], dict):
        state["faults"] = {}
    if not isinstance(state["catalog"], dict):
        state["catalog"] = {}
    if not isinstance(state["meta"], dict):
        state["meta"] = {}
    if not isinstance(state["agent"], dict):
        state["agent"] = {}

    state["catalog"].setdefault("deviceTemplates", [])
    state["catalog"].setdefault("zones", [])
    state["catalog"].setdefault("ahuUnits", [])
    state["catalog"].setdefault("faultMetaByDeviceId", {})

    state["meta"].setdefault("lastIngestAt", None)
    state["meta"].setdefault("lastClassificationAt", None)
    state["meta"].setdefault("lastFaultResolutionAt", None)
    state["meta"].setdefault("seedSource", None)
    state["meta"].setdefault("seededAt", None)

    state["agent"].setdefault("pendingActions", {})
    state["agent"].setdefault("auditLog", [])
    if not isinstance(state["agent"]["pendingActions"], dict):
        state["agent"]["pendingActions"] = {}
    if not isinstance(state["agent"]["auditLog"], list):
        state["agent"]["auditLog"] = []

    for node in state["nodes"].values():
        if not isinstance(node, dict):
            continue
        node.setdefault("position", 0.0)
        node.setdefault("historyByVariable", {})
        if not isinstance(node["historyByVariable"], dict):
            node["historyByVariable"] = {}

    return state


def _postgres_dsn() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for backend state storage")
    return database_url


def _use_memory_storage() -> bool:
    return not os.getenv("DATABASE_URL")


def ensure_storage_ready() -> None:
    global _MEMORY_STATE, _SCHEMA_READY
    if _SCHEMA_READY:
        return

    if _use_memory_storage():
        _MEMORY_STATE = _normalize_state(_MEMORY_STATE)
        _SCHEMA_READY = True
        return

    if psycopg is None or Json is None:
        raise RuntimeError("psycopg is required when DATABASE_URL is set")

    with psycopg.connect(_postgres_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS backend_state (
                    id SMALLINT PRIMARY KEY,
                    state JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CHECK (id = 1)
                )
                """
            )
            cur.execute(
                """
                INSERT INTO backend_state (id, state)
                VALUES (1, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (Json(_empty_state()),),
            )

    _SCHEMA_READY = True


def read_state() -> State:
    global _MEMORY_STATE
    ensure_storage_ready()

    if _use_memory_storage():
        _MEMORY_STATE = _normalize_state(_MEMORY_STATE)
        return deepcopy(_MEMORY_STATE)

    with psycopg.connect(_postgres_dsn(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM backend_state WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                state = _empty_state()
                cur.execute(
                    "INSERT INTO backend_state (id, state) VALUES (1, %s)",
                    (Json(state),),
                )
            else:
                state = _normalize_state(row[0])
            conn.commit()
    return state


def update_state(mutator: Callable[[State], T]) -> T:
    global _MEMORY_STATE
    ensure_storage_ready()

    if _use_memory_storage():
        _MEMORY_STATE = _normalize_state(_MEMORY_STATE)
        result = mutator(_MEMORY_STATE)
        _MEMORY_STATE = _normalize_state(_MEMORY_STATE)
        return result

    with psycopg.connect(_postgres_dsn(), autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT state FROM backend_state WHERE id = 1 FOR UPDATE")
            row = cur.fetchone()
            if row is None:
                state = _empty_state()
                cur.execute(
                    "INSERT INTO backend_state (id, state) VALUES (1, %s)",
                    (Json(state),),
                )
            else:
                state = _normalize_state(row[0])

            result = mutator(state)

            cur.execute(
                """
                UPDATE backend_state
                SET state = %s, updated_at = NOW()
                WHERE id = 1
                """,
                (Json(state),),
            )
            conn.commit()
    return result
