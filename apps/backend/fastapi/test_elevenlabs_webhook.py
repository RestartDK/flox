from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
FASTAPI_DIR = ROOT / "apps" / "backend" / "fastapi"

for path in (str(ROOT), str(FASTAPI_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import server  # noqa: E402
from shacklib import backend_state, elevenlabs_agent  # noqa: E402
from shacklib.mock_datacenter import build_seed_state  # noqa: E402


def _reset_memory_state(monkeypatch, state: dict) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(backend_state, "_SCHEMA_READY", False)
    monkeypatch.setattr(backend_state, "_MEMORY_STATE", state)


def test_normalize_post_call_transcription_event_extracts_structured_results():
    normalized = elevenlabs_agent.normalize_post_call_webhook_event(
        {
            "type": "post_call_transcription",
            "event_timestamp": 1739537297,
            "data": {
                "agent_id": "agent-123",
                "conversation_id": "conv-123",
                "status": "done",
                "has_audio": True,
                "metadata": {
                    "start_time_unix_secs": 1739537297,
                    "call_duration_secs": 22,
                    "termination_reason": "agent_ended_call",
                },
                "analysis": {
                    "evaluation_criteria_results": {
                        "engineer_acknowledged_issue": {
                            "result": "success",
                            "rationale": "The engineer agreed to inspect the issue.",
                        }
                    },
                    "data_collection_results": {
                        "acknowledged": {"value": True, "rationale": "Engineer confirmed"},
                        "callback_eta": {
                            "value": "15 minutes",
                            "rationale": "Engineer gave ETA",
                        },
                        "engineer_response_summary": {
                            "value": "Will inspect shortly.",
                            "rationale": "Summary captured",
                        },
                        "needs_follow_up": {
                            "value": False,
                            "rationale": "No additional follow-up required right now.",
                        },
                    },
                    "call_successful": "success",
                    "transcript_summary": "The engineer acknowledged the issue and will inspect shortly.",
                },
                "conversation_initiation_client_data": {
                    "dynamic_variables": {
                        "building_name": "Demo Tower",
                        "engineer_name": "Alex",
                        "product_name": "Belimo Energy Valve",
                        "situation_summary": "Cooling output is degraded on the north loop.",
                        "failure_name": "Valve tracking fault",
                        "likely_cause": "The actuator is not tracking commanded position.",
                        "likely_cause_confidence": "medium",
                        "fault_id": "fault-003",
                    }
                },
            },
        }
    )

    assert normalized["eventType"] == "post_call_transcription"
    assert normalized["conversationId"] == "conv-123"
    assert normalized["callSuccessful"] == "success"
    assert normalized["dynamicVariables"]["building_name"] == "Demo Tower"
    assert normalized["dynamicVariables"]["product_name"] == "Belimo Energy Valve"
    assert (
        normalized["analysis"]["evaluationCriteriaResults"][
            "engineer_acknowledged_issue"
        ]["result"]
        == "success"
    )
    assert normalized["futureEscalationAttempt"]["acknowledged"] is True
    assert normalized["futureEscalationAttempt"]["callbackEta"] == "15 minutes"
    assert normalized["futureEscalationAttempt"]["engineerResponseSummary"] == "Will inspect shortly."
    assert normalized["futureEscalationAttempt"]["needsFollowUp"] is False


def test_normalize_call_initiation_failure_masks_phone_numbers():
    normalized = elevenlabs_agent.normalize_post_call_webhook_event(
        {
            "type": "call_initiation_failure",
            "event_timestamp": 1759931652,
            "data": {
                "agent_id": "agent-123",
                "conversation_id": "conv-123",
                "failure_reason": "busy",
                "metadata": {
                    "type": "twilio",
                    "body": {
                        "CallSid": "CA12345",
                        "To": "+441111111111",
                        "From": "+14155550123",
                        "CallStatus": "busy",
                    },
                },
            },
        }
    )

    assert normalized["eventType"] == "call_initiation_failure"
    assert normalized["failureReason"] == "busy"
    assert normalized["providerMetadata"]["providerCallId"] == "CA12345"
    assert normalized["providerMetadata"]["toNumberMasked"].endswith("1111")
    assert normalized["providerMetadata"]["fromNumberMasked"].endswith("0123")


def test_validate_and_normalize_post_call_webhook_uses_sdk_signature_validation(
    monkeypatch,
):
    class _FakeWebhooks:
        def construct_event(self, *, payload, signature, secret):
            assert payload == '{"ok":true}'
            assert signature == "sig-123"
            assert secret == "secret-123"
            return {
                "type": "call_initiation_failure",
                "event_timestamp": 1,
                "data": {
                    "agent_id": "agent-123",
                    "conversation_id": "conv-123",
                    "failure_reason": "busy",
                    "metadata": {"type": "twilio", "body": {}},
                },
            }

    class _FakeClient:
        def __init__(self):
            self.webhooks = _FakeWebhooks()

    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "secret-123")
    monkeypatch.setattr(elevenlabs_agent, "get_elevenlabs_client", lambda: _FakeClient())

    normalized = elevenlabs_agent.validate_and_normalize_post_call_webhook(
        payload=b'{"ok":true}',
        signature="sig-123",
    )

    assert normalized["eventType"] == "call_initiation_failure"
    assert normalized["conversationId"] == "conv-123"


def test_build_outbound_dynamic_variables_requires_engineer_briefing_fields():
    payload = elevenlabs_agent.build_outbound_dynamic_variables(
        building_name="Demo Tower",
        engineer_name="Alex",
        product_name="Belimo Energy Valve",
        situation_summary="Cooling output is degraded on the north loop.",
        failure_name="Valve tracking fault",
        likely_cause="The actuator is not tracking commanded position.",
        likely_cause_confidence="medium",
        fault_id="fault-003",
        device_id="BEL-VLV-003",
        device_name="North Return Valve",
        severity="high",
        failure_summary="The valve is stuck and airflow is outside the target range.",
        recommended_action="Inspect the valve actuator and confirm whether manual override is required.",
        detected_at="2026-03-19T09:30:00Z",
        estimated_impact="$280/day",
        energy_waste="145 kWh/day",
        triggered_by="facility-manager",
    )

    assert payload["engineer_name"] == "Alex"
    assert payload["product_name"] == "Belimo Energy Valve"
    assert payload["likely_cause_confidence"] == "medium"


def test_post_call_webhook_endpoint_records_normalized_audit_event(monkeypatch):
    state = build_seed_state()
    _reset_memory_state(monkeypatch, state)

    monkeypatch.setattr(server, "ensure_storage_ready", lambda: None)
    monkeypatch.setattr(server, "update_state", lambda mutator: mutator(state))
    monkeypatch.setattr(elevenlabs_agent, "update_state", lambda mutator: mutator(state))
    monkeypatch.setattr(
        server,
        "validate_and_normalize_post_call_webhook",
        lambda *, payload, signature: {
            "eventType": "post_call_transcription",
            "conversationId": "conv-abc",
            "summary": "Manager acknowledged the issue.",
            "futureEscalationAttempt": {
                "provider": "elevenlabs",
                "conversationId": "conv-abc",
                "status": "completed",
            },
        },
    )
    monkeypatch.setattr(server, "record_post_call_webhook_event", elevenlabs_agent.record_post_call_webhook_event)

    with TestClient(server.app) as client:
        response = client.post(
            "/api/voice/elevenlabs/post-call",
            content=b'{"type":"post_call_transcription"}',
            headers={"elevenlabs-signature": "sig-123"},
        )

    assert response.status_code == 200
    assert response.json()["eventType"] == "post_call_transcription"

    audit_log = state["agent"]["auditLog"]
    assert audit_log[-1]["type"] == "elevenlabs_post_call_webhook"
    assert audit_log[-1]["conversationId"] == "conv-abc"
    assert audit_log[-1]["details"]["summary"] == "Manager acknowledged the issue."


def test_post_call_webhook_endpoint_rejects_invalid_signature(monkeypatch):
    state = build_seed_state()
    _reset_memory_state(monkeypatch, state)

    monkeypatch.setattr(server, "ensure_storage_ready", lambda: None)
    monkeypatch.setattr(server, "update_state", lambda mutator: mutator(state))
    monkeypatch.setattr(
        server,
        "validate_and_normalize_post_call_webhook",
        lambda *, payload, signature: (_ for _ in ()).throw(
            elevenlabs_agent.ElevenLabsSignatureError("invalid")
        ),
    )

    with TestClient(server.app) as client:
        response = client.post(
            "/api/voice/elevenlabs/post-call",
            content=b"{}",
            headers={"elevenlabs-signature": "sig-123"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid ElevenLabs webhook signature"
