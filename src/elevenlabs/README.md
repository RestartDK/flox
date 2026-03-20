# ElevenLabs Voice Escalation

Native ElevenLabs CLI project for the `On-Site Engineer Escalation` voice agent.

## Files

- `agents.json`
  - Native ElevenLabs CLI manifest of local agents tracked by the project.
- `tools.json`
  - Native ElevenLabs CLI manifest of reusable tools. Empty in this phase.
- `tests.json`
  - Native ElevenLabs CLI manifest of attached tests. Empty in this phase.
- `agent_configs/on_site_engineer_escalation.json`
  - Pushable agent configuration.
- `.env.example`
  - Local example for the CLI project folder.

## Required Environment Variables

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_AGENT_ID`
- `ELEVENLABS_WEBHOOK_SECRET`

## Provisioning Workflow

1. Install and authenticate the ElevenLabs CLI.
2. From this folder, create the remote agent once with:
   - `elevenlabs agents add "On-Site Engineer Escalation" --from-file agent_configs/On-Site-Engineer-Escalation.json`
3. Push subsequent config changes with:
   - `elevenlabs agents push --dry-run`
   - `elevenlabs agents push`
4. If dashboard edits are made manually, pull them back with:
   - `elevenlabs agents pull --update`

## Notes

- This folder now follows the native CLI project schema so `elevenlabs agents push` can operate cleanly.
- The call briefing order is fixed: product, situation, failure, likely cause.
- The dynamic variables expected by the prompt are:
  - `building_name`
  - `engineer_name`
  - `product_name`
  - `situation_summary`
  - `failure_name`
  - `likely_cause`
  - `likely_cause_confidence`
  - `fault_id`
  - `device_id`
  - `device_name`
  - `severity`
  - `failure_summary`
  - `recommended_action`
  - `detected_at`
  - `triggered_by`
- Success evaluation, data collection, and post-call webhook wiring are still best reviewed in the dashboard after the first push, then pulled back into repo once ElevenLabs materializes the exact stored schema.
- If the dashboard is used for experimentation, pull those changes back into this folder before treating them as final.
