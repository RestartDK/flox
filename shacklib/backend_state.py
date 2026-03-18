from __future__ import annotations

import os
from typing import Any, Callable, TypeVar

import psycopg
from psycopg.types.json import Json

State = dict[str, Any]
T = TypeVar("T")
_SCHEMA_READY = False


def _empty_state() -> State:
    return {
        "nodes": {},
        "faults": {},
        "meta": {
            "lastIngestAt": None,
            "lastClassificationAt": None,
            "lastFaultResolutionAt": None,
        },
    }


def _normalize_state(state: Any) -> State:
    if not isinstance(state, dict):
        return _empty_state()

    state.setdefault("nodes", {})
    state.setdefault("faults", {})
    state.setdefault("meta", {})

    if not isinstance(state["nodes"], dict):
        state["nodes"] = {}
    if not isinstance(state["faults"], dict):
        state["faults"] = {}
    if not isinstance(state["meta"], dict):
        state["meta"] = {}

    state["meta"].setdefault("lastIngestAt", None)
    state["meta"].setdefault("lastClassificationAt", None)
    state["meta"].setdefault("lastFaultResolutionAt", None)

    return state


def _postgres_dsn() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for backend state storage")
    return database_url


def ensure_storage_ready() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

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
    ensure_storage_ready()
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
    ensure_storage_ready()
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
