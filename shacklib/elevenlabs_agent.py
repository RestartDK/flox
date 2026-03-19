from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping
from urllib import error, request as urllib_request
from uuid import uuid4

from shacklib.backend_state import update_state
from shacklib.diagnosis_engine import utc_now_iso

LOGGER = logging.getLogger("elevenlabs-agent")

_AUDIT_LOG_LIMIT = 250
_DYNAMIC_VARIABLE_KEYS = (
    "building_name",
    "engineer_name",
    "product_name",
    "situation_summary",
    "failure_name",
    "likely_cause",
    "likely_cause_confidence",
    "fault_id",
    "device_id",
    "device_name",
    "severity",
    "failure_summary",
    "recommended_action",
    "detected_at",
    "estimated_impact",
    "energy_waste",
    "triggered_by",
)

_REQUIRED_DYNAMIC_VARIABLE_KEYS = frozenset(
    {
        "building_name",
        "engineer_name",
        "product_name",
        "situation_summary",
        "failure_name",
        "likely_cause",
        "fault_id",
        "device_id",
        "device_name",
        "severity",
        "recommended_action",
        "detected_at",
    }
)


class ElevenLabsConfigurationError(RuntimeError):
    pass


class ElevenLabsSignatureError(ValueError):
    pass


class ElevenLabsWebhookPayloadError(ValueError):
    pass


def get_elevenlabs_api_key() -> str:
    value = str(os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not value:
        raise ElevenLabsConfigurationError("ELEVENLABS_API_KEY is not set")
    return value


def get_elevenlabs_agent_id() -> str:
    value = str(os.getenv("ELEVENLABS_AGENT_ID") or "").strip()
    if not value:
        raise ElevenLabsConfigurationError("ELEVENLABS_AGENT_ID is not set")
    return value


def get_elevenlabs_webhook_secret() -> str:
    value = str(os.getenv("ELEVENLABS_WEBHOOK_SECRET") or "").strip()
    if not value:
        raise ElevenLabsConfigurationError("ELEVENLABS_WEBHOOK_SECRET is not set")
    return value


def get_elevenlabs_client() -> Any:
    try:
        from elevenlabs.client import ElevenLabs
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env sync
        raise ElevenLabsConfigurationError(
            "The elevenlabs SDK is not installed. Run `uv sync` to install project dependencies."
        ) from exc

    return ElevenLabs(api_key=get_elevenlabs_api_key())


def get_elevenlabs_phone_number_id() -> str:
    """Return the registered ElevenLabs phone number ID.

    Reads ELEVENLABS_PHONE_NUMBER_ID from env first; if absent, fetches the
    first phone number assigned to the configured agent from the API.
    """
    value = str(os.getenv("ELEVENLABS_PHONE_NUMBER_ID") or "").strip()
    if value:
        return value

    client = get_elevenlabs_client()
    agent_id = get_elevenlabs_agent_id()
    numbers = client.conversational_ai.phone_numbers.list()
    for num in numbers:
        info = getattr(num, "assigned_agent", None)
        if info and getattr(info, "agent_id", None) == agent_id:
            phone_number_id = getattr(num, "phone_number_id", None)
            if phone_number_id:
                return str(phone_number_id)

    raise ElevenLabsConfigurationError(
        "No phone number assigned to the configured agent. "
        "Set ELEVENLABS_PHONE_NUMBER_ID or assign a number in the ElevenLabs dashboard."
    )


def place_outbound_call(
    *,
    to_number: str,
    building_name: str,
    engineer_name: str,
    product_name: str,
    situation_summary: str,
    failure_name: str,
    failure_summary: str,
    likely_cause: str,
    likely_cause_confidence: str,
    fault_id: str,
    device_id: str,
    device_name: str,
    severity: str,
    recommended_action: str,
    detected_at: str,
    estimated_impact: str,
    energy_waste: str,
    triggered_by: str,
) -> dict[str, Any]:
    """Place an outbound call via ElevenLabs Twilio integration.

    Returns a dict with keys: ok, conversationId, callSid.
    """
    try:
        from elevenlabs.types import ConversationInitiationClientDataRequestInput
    except ModuleNotFoundError as exc:
        raise ElevenLabsConfigurationError(
            "The elevenlabs SDK is not installed. Run `uv sync`."
        ) from exc

    dynamic_variables = build_outbound_dynamic_variables(
        building_name=building_name,
        engineer_name=engineer_name,
        product_name=product_name,
        situation_summary=situation_summary,
        failure_name=failure_name,
        failure_summary=failure_summary,
        likely_cause=likely_cause,
        likely_cause_confidence=likely_cause_confidence,
        fault_id=fault_id,
        device_id=device_id,
        device_name=device_name,
        severity=severity,
        recommended_action=recommended_action,
        detected_at=detected_at,
        estimated_impact=estimated_impact,
        energy_waste=energy_waste,
        triggered_by=triggered_by,
    )

    client = get_elevenlabs_client()
    agent_id = get_elevenlabs_agent_id()
    phone_number_id = get_elevenlabs_phone_number_id()

    result = client.conversational_ai.twilio.outbound_call(
        agent_id=agent_id,
        agent_phone_number_id=phone_number_id,
        to_number=to_number,
        conversation_initiation_client_data=ConversationInitiationClientDataRequestInput(
            dynamic_variables=dynamic_variables,
        ),
    )

    LOGGER.info(
        json.dumps(
            {
                "message": "placed_elevenlabs_outbound_call",
                "conversationId": getattr(result, "conversation_id", None),
                "callSid": getattr(result, "call_sid", None),
                "toNumber": to_number,
                "faultId": fault_id,
            }
        )
    )

    return {
        "ok": bool(getattr(result, "success", True)),
        "conversationId": str(getattr(result, "conversation_id", "") or ""),
        "callSid": str(getattr(result, "call_sid", "") or ""),
    }


_DEFAULT_BACKEND_URL = "http://localhost:9812"


def escalate_fault(
    fault_spec: dict[str, Any], *, backend_url: str | None = None
) -> dict[str, Any]:
    """HTTP client helper for use by the AI agent.

    Posts the fault spec to the backend outbound-call route and returns the
    response dict with keys: ok, conversationId, callSid.
    """
    base = (
        backend_url or os.getenv("VITE_BACKEND_URL") or _DEFAULT_BACKEND_URL
    ).rstrip("/")
    url = f"{base}/api/voice/elevenlabs/outbound-call"
    body = json.dumps(fault_spec).encode()
    req = urllib_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        raise RuntimeError(
            f"Backend escalation call failed ({exc.code}): {raw}"
        ) from exc


def build_outbound_dynamic_variables(**kwargs: Any) -> dict[str, str]:
    payload: dict[str, str] = {}

    for key in _DYNAMIC_VARIABLE_KEYS:
        raw_value = kwargs.get(key)
        text = str(raw_value or "").strip()
        if not text and key in _REQUIRED_DYNAMIC_VARIABLE_KEYS:
            raise ElevenLabsWebhookPayloadError(
                f"Missing required ElevenLabs dynamic variable: {key}"
            )
        payload[key] = text

    return payload


def validate_and_normalize_post_call_webhook(
    *, payload: bytes | str, signature: str | None
) -> dict[str, Any]:
    if not signature:
        raise ElevenLabsSignatureError("Missing ElevenLabs-Signature header")

    payload_text = payload.decode("utf-8") if isinstance(payload, bytes) else payload

    try:
        event = get_elevenlabs_client().webhooks.construct_event(
            payload=payload_text,
            signature=signature,
            secret=get_elevenlabs_webhook_secret(),
        )
    except ElevenLabsConfigurationError:
        raise
    except Exception as exc:
        raise ElevenLabsSignatureError("Invalid ElevenLabs webhook signature") from exc

    return normalize_post_call_webhook_event(event)


def normalize_post_call_webhook_event(event: Any) -> dict[str, Any]:
    event_payload = _coerce_mapping(event)
    event_type = _optional_text(event_payload.get("type")) or _optional_text(
        getattr(event, "type", None)
    )
    event_timestamp = event_payload.get("event_timestamp")
    if event_timestamp is None:
        event_timestamp = getattr(event, "event_timestamp", None)
    data = _coerce_mapping(event_payload.get("data"))
    if not data:
        data = _coerce_mapping(getattr(event, "data", None))

    if not event_type:
        raise ElevenLabsWebhookPayloadError("Webhook event type is required")

    if event_type == "post_call_transcription":
        return _normalize_post_call_transcription(data, event_timestamp)
    if event_type == "call_initiation_failure":
        return _normalize_call_initiation_failure(data, event_timestamp)

    raise ElevenLabsWebhookPayloadError(
        f"Unsupported ElevenLabs webhook type: {event_type}"
    )


def record_post_call_webhook_event(event: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(event)
    event_type = _optional_text(normalized.get("eventType")) or "unknown"
    conversation_id = _optional_text(normalized.get("conversationId")) or "unknown"

    LOGGER.info(
        json.dumps(
            {
                "message": "received_elevenlabs_post_call_webhook",
                "eventType": event_type,
                "conversationId": conversation_id,
            }
        )
    )

    recorded_at = utc_now_iso()

    def _mutator(state: dict[str, Any]) -> dict[str, Any]:
        agent = state.setdefault("agent", {})
        if not isinstance(agent, dict):
            agent = {}
            state["agent"] = agent

        audit_log = agent.setdefault("auditLog", [])
        if not isinstance(audit_log, list):
            audit_log = []
            agent["auditLog"] = audit_log

        audit_log.append(
            {
                "id": f"audit-{uuid4().hex[:10]}",
                "type": "elevenlabs_post_call_webhook",
                "eventType": event_type,
                "conversationId": conversation_id,
                "createdAt": recorded_at,
                "details": normalized,
            }
        )
        if len(audit_log) > _AUDIT_LOG_LIMIT:
            del audit_log[:-_AUDIT_LOG_LIMIT]

        return {
            "ok": True,
            "eventType": event_type,
            "conversationId": conversation_id,
            "recordedAt": recorded_at,
        }

    return update_state(_mutator)


def _normalize_post_call_transcription(
    data: Mapping[str, Any], event_timestamp: Any
) -> dict[str, Any]:
    analysis = _coerce_mapping(data.get("analysis"))
    metadata = _coerce_mapping(data.get("metadata"))
    initiation = _coerce_mapping(data.get("conversation_initiation_client_data"))
    dynamic_variables = _coerce_mapping(initiation.get("dynamic_variables"))

    data_collection = _normalize_data_collection_results(
        _coerce_mapping(analysis.get("data_collection_results"))
    )
    evaluation = _normalize_evaluation_criteria_results(
        _coerce_mapping(analysis.get("evaluation_criteria_results"))
    )
    summary = _optional_text(analysis.get("transcript_summary"))

    return {
        "provider": "elevenlabs",
        "eventType": "post_call_transcription",
        "eventTimestamp": event_timestamp,
        "agentId": _optional_text(data.get("agent_id")),
        "conversationId": _required_text(
            data.get("conversation_id"), "conversation_id"
        ),
        "status": _optional_text(data.get("status")) or "done",
        "callSuccessful": _optional_text(analysis.get("call_successful")),
        "summary": summary,
        "metadata": {
            "startTimeUnixSeconds": metadata.get("start_time_unix_secs"),
            "callDurationSeconds": metadata.get("call_duration_secs"),
            "terminationReason": _optional_text(metadata.get("termination_reason")),
            "hasAudio": bool(data.get("has_audio"))
            if data.get("has_audio") is not None
            else None,
            "hasUserAudio": bool(data.get("has_user_audio"))
            if data.get("has_user_audio") is not None
            else None,
            "hasResponseAudio": bool(data.get("has_response_audio"))
            if data.get("has_response_audio") is not None
            else None,
        },
        "dynamicVariables": {
            key: str(value)
            for key, value in dynamic_variables.items()
            if value is not None
        },
        "analysis": {
            "evaluationCriteriaResults": evaluation,
            "dataCollectionResults": data_collection,
        },
        "futureEscalationAttempt": {
            "provider": "elevenlabs",
            "conversationId": _required_text(
                data.get("conversation_id"), "conversation_id"
            ),
            "status": "completed",
            "callSuccessful": _optional_text(analysis.get("call_successful")),
            "summary": summary,
            "acknowledged": _extract_data_collection_scalar(
                data_collection.get("acknowledged"), expected_type=bool
            ),
            "callbackEta": _extract_data_collection_text(
                data_collection.get("callback_eta")
            ),
            "engineerResponseSummary": _extract_data_collection_text(
                data_collection.get("engineer_response_summary")
            )
            or summary,
            "needsFollowUp": _extract_data_collection_scalar(
                data_collection.get("needs_follow_up"), expected_type=bool
            ),
        },
    }


def _normalize_call_initiation_failure(
    data: Mapping[str, Any], event_timestamp: Any
) -> dict[str, Any]:
    metadata = _coerce_mapping(data.get("metadata"))
    provider_type = _optional_text(metadata.get("type")) or "unknown"
    body = _coerce_mapping(metadata.get("body"))
    provider_call_id = _optional_text(body.get("CallSid")) or _optional_text(
        body.get("call_sid")
    )
    to_number = _optional_text(body.get("To")) or _optional_text(body.get("to_number"))
    from_number = _optional_text(body.get("From")) or _optional_text(
        body.get("from_number")
    )

    return {
        "provider": "elevenlabs",
        "eventType": "call_initiation_failure",
        "eventTimestamp": event_timestamp,
        "agentId": _optional_text(data.get("agent_id")),
        "conversationId": _required_text(
            data.get("conversation_id"), "conversation_id"
        ),
        "failureReason": _optional_text(data.get("failure_reason")) or "unknown",
        "providerMetadata": {
            "type": provider_type,
            "providerCallId": provider_call_id,
            "toNumberMasked": _mask_phone_number(to_number),
            "fromNumberMasked": _mask_phone_number(from_number),
            "callStatus": _optional_text(body.get("CallStatus"))
            or _optional_text(body.get("sip_status")),
            "errorReason": _optional_text(body.get("error_reason")),
        },
        "futureEscalationAttempt": {
            "provider": "elevenlabs",
            "conversationId": _required_text(
                data.get("conversation_id"), "conversation_id"
            ),
            "status": "call_initiation_failure",
            "failureReason": _optional_text(data.get("failure_reason")) or "unknown",
            "providerType": provider_type,
            "providerCallId": provider_call_id,
            "toNumberMasked": _mask_phone_number(to_number),
            "fromNumberMasked": _mask_phone_number(from_number),
        },
    }


def _normalize_evaluation_criteria_results(
    raw_results: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for key, raw_value in raw_results.items():
        value = _coerce_mapping(raw_value)
        if value:
            normalized[str(key)] = {
                "result": _optional_text(value.get("result"))
                or _optional_text(raw_value),
                "rationale": _optional_text(value.get("rationale")),
            }
            continue
        normalized[str(key)] = {"result": raw_value, "rationale": None}
    return normalized


def _normalize_data_collection_results(
    raw_results: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for key, raw_value in raw_results.items():
        value = _coerce_mapping(raw_value)
        if value:
            normalized[str(key)] = {
                "value": value.get("value"),
                "rationale": _optional_text(value.get("rationale")),
            }
            continue
        normalized[str(key)] = {"value": raw_value, "rationale": None}
    return normalized


def _extract_data_collection_scalar(
    entry: Mapping[str, Any] | None, *, expected_type: type[Any]
) -> Any:
    if not isinstance(entry, Mapping):
        return None
    value = entry.get("value")
    if isinstance(value, expected_type):
        return value
    return None


def _extract_data_collection_text(entry: Mapping[str, Any] | None) -> str | None:
    if not isinstance(entry, Mapping):
        return None
    return _optional_text(entry.get("value"))


def _mask_phone_number(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) <= 4:
        return "*" * len(digits) if digits else None
    return f"{'*' * max(0, len(digits) - 4)}{digits[-4:]}"


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)

    if hasattr(value, "__dict__") and isinstance(value.__dict__, dict):
        return {
            key: item for key, item in value.__dict__.items() if not key.startswith("_")
        }

    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="python")
        if isinstance(dumped, dict):
            return dumped

    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dumped

    return {}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ElevenLabsWebhookPayloadError(f"Missing required field: {field_name}")
    return text
