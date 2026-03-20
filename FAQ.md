# Flox FAQ

This FAQ is written for both non-technical and semi-technical readers.

- If you are non-technical, read the first paragraph of each answer.
- If you are semi-technical, read the **Technical note** under each answer.

## 1) What is Flox?

Flox is a monitoring and fault-intelligence platform for HVAC actuators. It helps teams spot problems early, understand severity, and decide what to fix first.

**Technical note:** Flox ingests actuator telemetry (torque, motor position, temperature, signal quality), stores it in PostgreSQL, runs continuous diagnosis with a classifier worker, and displays health/fault state in a React dashboard.

## 2) What problem does it solve?

Most buildings collect device data but do not turn it into clear action. Flox translates raw signals into fault alerts and recommended actions so teams can reduce downtime, avoid comfort issues, and improve reliability.

**Technical note:** Faults are detected at device level and propagated up the node hierarchy (actuator -> AHU -> plant), so system-level health reflects downstream conditions.

## 3) Who is Flox for?

Facility managers, operations teams, and maintenance teams can use Flox without deep engineering knowledge.

**Technical note:** Developers and data teams can also use API endpoints, worker services, and optional ML inference to extend or integrate the platform.

## 4) What kinds of faults can Flox detect today?

Flox detects common actuator issues and marks each with severity so teams know what is urgent.

Current built-in fault kinds:

- `stiction_suspected` (Critical)
- `high_torque_anomaly` (Warning)
- `temperature_drift` (Warning)
- `signal_loss` (Critical)
- `weak_signal` (Warning)

**Technical note:** Rule-based detection is always available; optional ML classifiers can extend coverage beyond fixed thresholds.

## 5) Does Flox automatically control equipment?

No. Flox is designed to keep humans in control. It can recommend and prepare actions, but sensitive actions require explicit operator approval.

**Technical note:** The operations agent can run tools (status checks, diagnosis, fault history, resolution workflows), but write actions are approval-gated in the UI.

## 6) How real-time is the system?

Flox is near real-time for operational use. You can monitor current health and active issues as data arrives.

**Technical note:** The diagnosis loop runs continuously, with interval controlled by `CLASSIFIER_INTERVAL_SECONDS` (default 5 seconds).

## 7) Do we need AI to use Flox?

No, but AI adds convenience. You can still use the dashboard and core fault pipeline without chatting with the operations agent.

**Technical note:** `ANTHROPIC_API_KEY` is required for agent chat features. Core ingest, classification, and dashboard views are separate from the chat layer.

## 8) Is machine learning mandatory?

No. Flox works with built-in heuristic rules out of the box.

**Technical note:** ML inference is optional and can be started with the ML profile to improve or broaden fault classification behavior.

## 9) How do I start Flox quickly?

Use the setup commands below. This brings up the platform and opens the web dashboard.

```bash
cp .env.example .env
make init
make up
make dev
```

Then open `http://localhost:3000`.

**Technical note:** The frontend expects backend health/status data at `/api/status`.

## 10) Why does the dashboard show a connection error?

Usually this means the backend services are not running yet.

Try:

```bash
make up
make ps
make logs
```

**Technical note:** `make up` starts core services (PostgreSQL, Redis, FastAPI backend, classifier service, worker).

## 11) Can we demo the system without live devices?

Yes. Flox can run with a simulator so teams can test flows safely.

**Technical note:** Use `make lift.sim` to run core services plus the node simulator.

## 12) Where is data stored?

Operational data is stored centrally so teams can view both current and historical behavior.

**Technical note:** State is persisted in normalized PostgreSQL tables, with a legacy JSONB snapshot maintained for compatibility.

## 13) How do we stop services?

Run:

```bash
make down
```

This stops all Docker Compose services started by the project.

## 14) What should we do first after setup?

Start with three checks:

1. Confirm system health in the dashboard.
2. Review top active faults and severities.
3. Use the operations agent for plain-language investigation of one high-priority issue.

**Technical note:** `make doctor` validates local tooling, and `make help` lists all available workflow commands.

## Judge-style FAQ

### 15) Why does this matter right now?

Operational complexity is rising and maintenance teams are stretched. Flox focuses on reducing avoidable downtime and repeated issues using data that many facilities already collect.

**Technical note:** The product leverages existing actuator telemetry, which lowers adoption friction versus projects that require full hardware replacement.

### 16) What makes Flox different from a normal BMS dashboard?

Most dashboards show alerts; Flox is built to help teams decide what to do first. It highlights severity, likely cause, and operational impact so action can happen faster.

**Technical note:** Flox combines fault classification, hierarchy-level health propagation, and approval-gated operations support in one workflow.

### 17) What measurable value should a customer expect?

The expected value is faster response and fewer repeated failures from unresolved actuator issues.

**Technical note:** Core success metrics are MTTD, MTTR, high-severity fault recurrence, and resolution quality per resolved fault.

### 18) How would you prove ROI in a pilot?

Start small, compare before and after, and report concrete results tied to maintenance and reliability outcomes.

**Technical note:** A practical pilot uses a baseline period and a monitored period, then compares response time, recurrence, and issue closure quality.

### 19) Who pays for this, and who uses it daily?

Budget owners are usually facility or operations leaders, while daily users are technicians and control-room operators.

**Technical note:** Buyer and user are often different personas, so onboarding, reporting, and value messaging must serve both groups.

### 20) What is the business model?

A simple subscription model is easiest to adopt and scale across portfolios.

**Technical note:** Typical structure: base site fee plus portfolio or device-tier pricing, with optional premium analytics/AI modules.

### 21) How do you avoid alert fatigue?

The goal is quality over quantity: fewer, clearer, better-prioritized alerts.

**Technical note:** Confidence scoring, severity tiers, and deduplication help reduce noisy notifications and focus attention on high-impact faults.

### 22) Why should operators trust recommendations from an AI-assisted system?

Trust comes from transparency and control. Teams can see why a recommendation appears and keep final approval in human hands.

**Technical note:** Each recommendation should include evidence context and traceable actions; write actions remain explicit approval steps.

### 23) What are the biggest adoption risks?

The main risks are data quality, workflow change resistance, and unclear ownership.

**Technical note:** Mitigation includes staged rollout, champion users, regular review cadences, and clear operational handoff responsibilities.

### 24) How does this scale from one building to many?

The same approach works portfolio-wide: standard fault language, shared playbooks, and centralized visibility.

**Technical note:** Multi-site deployment benefits from consistent taxonomy and benchmark reporting by asset type, site, and region.

### 25) What is defensible about Flox long-term?

Defensibility comes from becoming part of day-to-day operations, not just being another dashboard.

**Technical note:** Historical fault outcomes, site-specific tuning, and workflow integration create compounding operational intelligence over time.

### 26) What does success look like after 6-12 months?

Success means teams rely on Flox during daily operations and can point to measurable reliability improvements.

**Technical note:** Targets can include reduced critical fault duration, lower repeat incidents, and documented response improvements across pilot sites.

### 27) If you were judging this project, why would it stand out?

It tackles a real industrial pain point, demonstrates practical implementation, and connects technology to measurable operational outcomes.

**Technical note:** The combination of live diagnostics, action prioritization, and human-in-the-loop governance is strong for real-world adoption.
