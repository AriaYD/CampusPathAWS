# CampusPath

**An agent fleet that turns "who I want to become" into a validated, calendar-aware growth plan — and keeps every step honest.**

Built for the *All Things Agentic Hackathon* (Google Cloud × Devpost, Aug 2026) · Category: **Collaborative Partner**
Stack: **Gemini 3.5 Flash on Vertex AI** · **Google GenAI SDK + ADK** · **Cloud Run** · Cloud Scheduler + Cloud Run Jobs · Vertex AI Agent Engine · Secret Manager

> This is the public submission repository. The Chinese engineering ledgers (spec, plan, progress) are kept in the private working repository and are not part of the submission.

| | |
|---|---|
| Live demo | https://campuspath-web-786160486093.asia-east2.run.app (passcode is printed on the public landing page: `/landing`) |
| API (OpenAPI) | https://campuspath-api-786160486093.asia-east2.run.app/docs |
| Architecture | [`docs/hackathon/architecture.svg`](docs/hackathon/architecture.svg) · full text in [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| Demo video | *(link added on submission)* |
| Data | **All student, calendar, opportunity and publisher data is synthetic.** Course catalog and degree requirements are scraped from HKUST's public catalog. UI shows a `Synthetic / Demo Data` badge. |

---

## 1. The friction

A university student asks a simple question — *"I want to be a data scientist; what do I do this semester?"* — and gets a fragmented answer: a degree-requirements PDF, a careers-office noticeboard, 90+ department web pages that change weekly, a calendar that is already full, and an advisor with a 3-week queue. Advice that ignores prerequisites, capacity or sleep is worse than no advice: it produces plans that get abandoned in week 3.

CampusPath is the **collaborative partner** in that loop. It does not chat. It **proposes** a concrete plan (courses + activities + preparation actions), shows the evidence for every item, asks the student to approve or decline item by item, projects the approved items into the calendar, watches the environment in the background, and **adapts** from the student's own feedback — reflections, ratings, and refusals.

## 2. What the agents actually do (beyond a chat loop)

| Agent | Role | Hard constraint (enforced in the type layer, not in prompts) |
|---|---|---|
| **A0 Orchestrator** | Routes an intent to the agents it needs | Deterministic routing table first; the LLM only composes for unknown intents (trace tells them apart) |
| **A1 Student Context** | Extracts facts from résumé / reflections | Output is **always a pending proposal**; nothing is written until the student confirms (B3) |
| **A2 Academic** | Facts and candidate courses | Emits facts only — no ranking, no trade-offs |
| **A3 Goal-Gap** | Decomposes a target role into requirements, finds the gap | Uses compiled role packs (from real JD corpora) + live Google-Search-grounded research when no pack matches |
| **A4 Opportunity Scout** | Extracts opportunity drafts from **untrusted** external pages | Tool whitelist of exactly two tools; external text is user-role data and never enters a system prompt; output can only be a *draft* (a human reviewer publishes). Runs under a **separate service account** with zero student-data permissions |
| **A5 Pathway** | The **only** agent allowed to make trade-offs | Every `PlanItem` must carry a `validation_id` issued by the zero-LLM Rules engine, or the API rejects it (B8). Repair loop ≤ 3 rounds; on failure it falls back to a validated fixture and negative-caches the goal for the day |

Nine **deterministic services** (zero LLM, AST-scanned in CI) own everything that must be reproducible: prerequisite logic and eligibility, calendar capacity, wellbeing thresholds and templates, consent/receipts, k-anonymous aggregation for the institution, event monitoring/replan scope, publishing review, and source connectors. **Calendar tokens never reach any LLM context**; the institution dashboard cannot re-identify a student (cells with n < 5 are suppressed); private reflections cannot physically flow to the institution (the boundary is a Pydantic type, not a policy).

**Asynchronous / background execution**

- **Cloud Scheduler → Cloud Run Job** (`campuspath-sources-refresh`, daily 09:00 HKT): sweeps 93 registered sources (85 real HKUST pages), sha256 change detection, routes changed official pages through A4 extraction to the opportunity plaza — no human in the loop for whitelisted official sources.
- **Background draft builder**: plan drafts are built in a worker thread with progress reporting; the student is asked to approve when it lands.
- **Live market research task**: unknown target roles trigger a background job that searches live job postings (Google Search grounding on Vertex), extracts requirements, and refuses to invent anything it cannot read (`NO_REQUIREMENTS`).
- **Feedback loop**: reflections produce structured, anonymous `EventQualityFeedback` (a sixth ranking dimension) and a personal fit tag; "not attending" adds to a decline list that A5 and the fixture path both respect; memory is *advisory only* and forgettable.

## 3. Architecture

![CampusPath architecture](docs/hackathon/architecture.svg)

Two planes, contract-first: the **semantic plane** (A0–A5, the only code allowed to call a model, Vertex-only) and the **deterministic plane** (nine services, zero LLM). Every exchange between them is a Pydantic model in [`contracts/`](contracts/README.md) (the single source of truth: JSON Schema + OpenAPI + generated TypeScript types). Data the types don't allow physically cannot flow.

**Google Cloud in use at runtime**

| Service | Role |
|---|---|
| Vertex AI — `gemini-3.5-flash` (global endpoint) | The only model exit. A generation floor (≥ 3.5) is asserted in the client constructor; running with an older model is a construction error, not a warning |
| Google GenAI SDK | Request-path agents (A0–A5) |
| Google ADK | Agent Engine mirrors of A0 and A4 (`agents/cloud/`), with a CI test asserting the routing table is identical to the local one |
| Vertex AI Agent Engine (us-central1) | Managed runtimes for the two ADK agents; the web app shows a live runtime/billing status light |
| Cloud Run (asia-east2) | `campuspath-web` (Next.js 16, PWA) and `campuspath-api` (FastAPI) |
| Cloud Run Jobs + Cloud Scheduler | Daily source sweep |
| Secret Manager | Check-in HMAC secret and Moodle token |
| Cloud Storage / Firestore | Provisioned by `infra/bootstrap.sh` (private evidence vault, canonical store). The demo deployment currently keeps state in-process (`max-instances=1`) — see *Findings* |

## 4. Run it locally (≈ 10 minutes)

Prerequisites: Python 3.12, [`uv`](https://docs.astral.sh/uv/), [`bun`](https://bun.sh), `gcloud` CLI, a Google Cloud project with the Vertex AI API enabled.

```bash
git clone <this repo> campuspath && cd campuspath
cp .env.example .env            # then set GOOGLE_CLOUD_PROJECT=<your-project>
gcloud auth application-default login   # Vertex uses ADC; no API keys anywhere

bash scripts/install-hooks.sh   # pre-commit: secret hygiene + "Vertex only" guard
make setup                      # uv venv + installs every package in editable mode
bash scripts/preflight.sh       # billing / secrets / backend checks — must print "可以开工"
make smoke                      # < 10 s: contracts + seed + core services
make api                        # FastAPI on :8000 (sources .env; model endpoints 503 without ADC)
cd apps/web && bun install && bun run dev --port 3100
```

Open http://127.0.0.1:3100 → **Login** (synthetic personas: students `STU-A` … `STU-L`, plus institution roles). Language switch (EN / 简 / 繁) is in the top bar. Without ADC the app still runs end-to-end on deterministic fixtures; only model-backed endpoints return 503.

Full verification: `make check` (all suites + zero-LLM scans + harness self-test) and `make eval` (13 BLOCKER + 12 TARGET metrics, machine-judged; the last run is in [`eval/results/report.md`](eval/results/report.md)).

## 5. Deploy to Google Cloud

```bash
# 0. one-time infrastructure (idempotent; prints a dry-run without --apply)
bash infra/bootstrap.sh --apply        # Firestore, GCS vault, two service accounts, secrets, Artifact Registry
bash infra/verify.sh                   # negative checks: A4's SA must NOT hold student-data roles

# 1. API — Vertex model calls go through the global endpoint
gcloud run deploy campuspath-api --source . --region asia-east2 \
  --update-env-vars GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global \
  --max-instances 1

# 2. Web (ships the generated contract types into the image)
cd apps/web && rm -rf .contracts-generated && cp -r ../../contracts/generated .contracts-generated
gcloud run deploy campuspath-web --source . --region asia-east2 \
  --update-env-vars CAMPUSPATH_API_ORIGIN=<api url>,APP_ORIGIN=<web url>,AUTH_SECRET=<random>,CAMPUSPATH_DEMO_PASSCODE=<passcode>

# 3. Daily source sweep (Cloud Run Job + Cloud Scheduler)
bash infra/sources_job.sh create --apply

# 4. Agent Engine runtimes for the two ADK agents (billed hourly — delete when idle)
bash infra/agent_engine.sh start && bash infra/agent_engine.sh status   # `stop` to delete both runtimes
```

## 6. Findings & learnings

- **Put the rule in the constructor, not the README.** Two things that must never silently regress — "only Vertex, never AI-Studio billing" and "Gemini ≥ 3.5" — are asserted when the model client is constructed, and each has a *known-failing sample* test proving the guard actually fires.
- **A plan item without a validation credential is not a plan item.** Making the Rules engine the issuer of `validation_id` and making the API reject unbacked items removed a whole class of "plausible but impossible" plans, and gave A5 a concrete repair signal instead of a vague "be careful with prerequisites".
- **Gemini 3.5 changed the latency profile, not just the quality.** `thinking_budget=0` (the 2.x idiom) costs 20.9 s per call on 3.5-flash; `thinking_level=MINIMAL` costs 0.7 s. Every migration re-measures latency before trusting old parameters.
- **State in-process is the honest weakness of this demo.** The API runs with `max-instances=1` and rebuilds its seed on cold start; Firestore is provisioned but not yet the backing store. It is the top item on the roadmap below.
- **Metrics names decide how people read them.** An institution metric first called "discovery rate" read as an algorithm report card; renaming it "reach rate" and keeping the denominator fixed made the same number honest.

## 7. Pre-existing work disclosure

This repository was started on **2026-07-29** for a university-internal Google hackathon and was substantially extended during the *All Things Agentic* submission period (2026-08-04 → 2026-08-31). In the spirit of the rules we disclose the split explicitly:

- **Pre-existing (before 2026-08-04, commits `afd5f45..b37be24`)**: product spec, contract layer, synthetic seed, the nine deterministic services, the A0–A5 agent roster on Gemini 2.5, the two portals' UI, Cloud Run deployment, evaluation harness.
- **Built during the submission period (commits `b37be24..HEAD`; 47+ commits, +22k lines at the time of writing)**: plan draft → approval gate, résumé direct-write with undo, expiry governance and curation badges, the institution metrics pipeline (`/insights`) and visual reports, mobile-first rewrite + installable PWA, trilingual landing page, **Gemini 3.5 migration with the generation floor**, and the hackathon batches listed in [`docs/plans/hackathon-all-things-agentic-2026-08-24.md`](docs/plans/hackathon-all-things-agentic-2026-08-24.md) (persistence, observability, agent registry, ADK on the request path).

Third-party inputs: HKUST public course catalog (scraped with a 1 s polite interval and disk cache; no student data), public job postings via Google Search grounding, open-source libraries under their licenses. No sponsor funding or support was received.

## 8. Repository map

```text
contracts/   Pydantic contracts → JSON Schema / OpenAPI / TS types (single source of truth)
agents/      A0–A5 (GenAI SDK, Vertex-only) · agents/cloud: ADK mirrors for Agent Engine
services/    api (FastAPI orchestration) + 9 zero-LLM services (rules, capacity, wellbeing, state, action, aggregation, monitor, publishing, connector, packs, mock-campus)
apps/web/    Next.js 16 student + institution portals, PWA, i18n (en / zh-Hans / zh-Hant)
seed/        Synthetic data generator + HKUST catalog scraper
eval/        13 BLOCKER + 12 TARGET acceptance metrics (`make eval`)
jobs/        Cloud Run Job: daily source refresh
infra/       GCP bootstrap / verify / cost / Agent Engine / Scheduler scripts (dry-run by default)
docs/        Design tokens, runbooks, verification screenshots, hackathon materials
```

---
