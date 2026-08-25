English edition of docs/demo-runbook.md, translated for the All Things Agentic Hackathon submission (Aug 2026).

# Demo Runbook (Spec §19's seventeen steps → actual operation)

> Written 2026-07-31. Every step is labeled **[Ready]**, **[Fallback demo]**, or **[Verbal explanation]** —
> we don't pretend the demo has features it doesn't. Going through this runbook before recording is itself the
> rehearsal checklist.

## Getting started

```bash
make api          # 127.0.0.1:8000
make web          # 127.0.0.1:3100
# Moodle (optional, the real path for step 2):
gcloud compute ssh campuspath-moodle --zone=asia-east2-a -- -L 8080:localhost:8080
```

Open `http://localhost:3100` → auto-redirects to `/login`. **Start by demoing the two portals logging in
separately**: pick STU-A on the student card (passcode = the value of the `CAMPUSPATH_DEMO_PASSCODE` environment
variable, distributed verbally by the team); log in as curator on the institution card in a separate window —
neither side's navigation is visible to the other, and a cross-portal URL gets bounced back. This alone is the
first act of D5.

Measured latency (2026-07-31): `/matches` hot path P50 ≈ 2.3s (threshold <3s); cold-start first call ≈ 22s
(Vertex initialization + reasoning generation), **warm it up with one call before the demo**.

## Walkthrough of the seventeen steps

| # | Script beat | Operation | Status |
|---|---|---|---|
| 1 | Resume upload → **direct write to profile + item-by-item undo** | On /profile, in the upload area, click "one-click inject demo student Little Red Riding Hood's resume" → deterministic parsing (zero AI) → **written directly into the Growth Profile overview**, a dialog lists each item with an "undo" button; undo one, then check the overview — it's actually one item shorter. **B3 still applies**: candidate changes A1 distills from reflections remain pending and must be decided item by item in "Profile Update Proposals" (demoing both paths side by side is the most persuasive) | Ready |
| 2 | Authorize SIS/Moodle + free/busy, zero LLM | Walk through the authorization page at /onboarding; for the real Moodle path, use `python -m moodle_mcp.server` or show the measured record from `mcp/tests` directly (STU-A's 7 courses mapped to contract records); /calendar shows the two authorization tiers (STU-A has no titles / STU-B has titles) | Ready |
| 3 | Dual goals + shared gap + divergence point | Use **STU-C** (employment primary goal + academia candidate goal): /gaps shows the shared gap and the actual divergence point; STU-A (two goals in the same direction) shown side by side as "no divergence" for contrast | Ready |
| 4 | A2 course facts + A5 ranking | /planner: three-state prerequisite judgment, offering semester, conflicts; recommendation ranking | Ready |
| 5 | Publisher time-limited authorization → submission → moderation | Institution portal /publisher: authorized submission ok, out-of-scope submission refused, all three moderation verdicts | Ready |
| 6 | Square proactive discovery + "why wasn't this recommended" | On /square, filter by "official," click "why wasn't this recommended" on any non-recommended item (Rules credential explanation); favorite it → written into preference memory | Ready |
| 7 | A4 normalization + "future eligible" explanation | The `future_eligible` card on /for-you carries "when it becomes reachable"; A4's exit point: POST /ops/opportunity-drafts (dedup demo works with a same-named draft) | Ready |
| 8 | Milestones + Plan A/B/C (**written only after approval**) | First visit to /timeline is an empty state, "no plan yet" → click "start planning" → a dialog shows **the three-line basis** (your goals / your profile / preferences in the memory hub) + what will change (N additions) + the item list → only "approve and commit" writes it to the schedule; "let me think" leaves nothing behind. Afterwards the top button switches to "replan"; changing the intensity tier goes through the same approval path | Ready |
| 9 | Rules block sleep encroachment, zero LLM | The measured record from eval B1/B2 + the /wellbeing verdict panel (threshold + template, the zero-LLM statement is right there on the page) | Ready |
| 10 | Two-reminder state machine | The /wellbeing reminder panel (first reminder + re-evaluation time + non-diagnostic disclaimer); the 3rd reminder being rejected (Alert Overload) is shown via the API's measured record | Ready |
| 11 | Outreach consent branch | STU-A clicks "have my counselor contact me" → 403 shown honestly (no consent); STU-B → 200. Real email delivery needs the Counseling mailbox secret (no value set), explained verbally | Ready (email explained verbally) |
| 12 | After confirmation, write to the CampusPath Plan calendar | /actions: approve → server issues a receipt → written (STU-B); STU-C demos the honest branch of "approved but the write is unauthorized"; a forged receipt gets 403, backed by a regression test | Ready |
| 13 | Three-way separation of reflection | /reflections attaches to a specific object; the path from rating to quality feedback flow is in the backlog, explained verbally as the B4/B10 type-level isolation | Ready (partly verbal) |
| 14 | Consistently low quality gets downweighted + reviewed | Institution portal **/insights** "Resource Effectiveness Insights": three utilization metrics + per-period trend + supply gaps (school-wide and by-school two-tier) + square conversion; clicking "expand full report" unfolds five visualization sections **in place** (including a 95% confidence-interval whisker on the four-dimension quality score). T6 measured at 0% | Ready |
| 15 | Complete a project → confirm the profile update | On /profile, "Profile Update Proposals": accept A1's proposal → version advances, event is logged. **Note the contrast with step 1**: here it's an AI inference and must be confirmed item by item; uploading a self-authored resume writes directly | Ready |
| 16 | Memory curation + local replanning | /memory: correct (old entry kept with a trace), lock (locked entries can't be overwritten), forget; /actions shows a preview of the replanning scope (does not touch `long_term`) | Ready |
| 17 | (§19 wrap-up) Metrics and governance | `make eval`: 13/13 BLOCKER, 11/12 TARGET (T11 shown red, honestly), BL1–BL5 comparison numbers; the institution portal /console's 5 isolated 403 panels. **When demoing /insights, switch to "by year"** — 2 of the 4 cells show "insufficient sample," which is the privacy invariant at work, not unprepared data (rationale in Spec §17.7) | Ready |

## Known not-demoed list (per Spec §18.3 and the gap ledger)

Real Calendar OAuth (per user decision, a fixture is used instead), real Counseling email delivery,
the `phd-to-industry` pack (not shown, not claimed), T11's 75% precision (shown honestly in red).

## New demo points added 2026-08-02 (feat/pack-sources-intl)

| Demo | Operation | Status |
|---|---|---|
| Real scraping from official sources straight to the square | Institution console → source registry card (92 sources grouped, real/mock labeled) → click "refresh" on the HKUST events calendar → the student square shows today's real events labeled "officially scraped" (OPP-LIVE-*) | Ready |
| Policy change alert | In the console, refresh any policy source (e.g. Immigration Department IANG) → an alert card appears in the square's "policy relevant to international students" category (links only to the official source, no signup action; visible only to students who checked the international-student box) | Ready |
| Global international-student toggle | On the profile page, check "I am an international student" → fill in the form → the goal breakdown gains an extra "international student preparation" column (badge for pending policy review + disclaimer), For You/electives get a `.intl-note` annotation, and the action center shows a document expiry reminder | Ready |
| Market-evidence-backed breakdown | Goal studio: for SWE/AI PM goals, the breakdown's core items are bold-underlined + a "required by N of 10 job postings" market annotation + a clickable link to an authoritative ranking (36 links, all verified) | Ready |
| Live AI decomposition | For a candidate goal (e.g. Data Analyst, not matched to any persona) → click "AI live decomposition" → a progress bar → **switch to another page and back, progress is preserved** → once complete, the item is tagged "AI live decomposition · pending verification" | Ready (requires Vertex) |
| Enrolled courses ↔ calendar share the same source | On planner, expand the "courses enrolled this semester" panel (4 courses) ↔ the calendar page shows the same 4 course blocks (capacity stats share the same source) | Ready |

> F1 note: the top bar's "click to start Cloud Run" actually deploys the Agent Engine (about 5–10 minutes per
> runtime, billed hourly) — **do one manual dry run of the full start path before the actual demo**; after the
> demo click "click to shut down" to delete the runtime and save cost.

## New demo points added 2026-08-04

- **North Star metric VGA** (top of the Growth Momentum page, gold star card): first show judges the Spec §17.1
  definition (it does not reward clicks/favorites/registrations), then demo it live — write a reflection submission
  for an activity already registered for → return to this page: **the number next to the star is +1**, and the
  action list gains a line tagged "reflection loop closed ✓" with a date. A cold-start 0 is the honest value, and
  it's a good opportunity to make the point that "the metric doesn't reward busyness, only evidenced completion."
- **One-click demo resume injection** (two blue-link lines above the upload area on the Growth Profile page):
  Little Red Riding Hood (marketing) / Big Bad Wolf (mechanical engineering) — one click uploads and parses,
  so judges don't need to bring their own file.

## New demo points added 2026-08-03

- **Top-bar status light**: a pulsing green dot = Agent Engine is running (and being billed) — a detail that
  demonstrates "we're being honest about cost"
- **Three planning-intensity tiers** (extracurricular planning page, mist-colored tab): light/balanced/ambitious →
  activities in the next two weeks ≤3/5/7, courses 2/3/4 — switching tiers replans live (A5 genuinely
  regenerates, takes 5–15 seconds)
- **Activity trash can**: bottom-right of any planned activity → two-step confirmation "confirm not attending" →
  the item and its calendar block both disappear, and regeneration does not bring it back
- **Passcode gate**: remember to get past the gate before demoing (passcode communicated verbally by the team,
  not written anywhere in the UI or docs)
