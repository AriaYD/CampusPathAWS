English edition of contracts/README.md, translated for the All Things Agentic Hackathon submission (Aug 2026).

# contracts — CampusPath contract layer (WP1)

**The single source of truth for schema.** Frontend TypeScript types, agent output validation, mock services, and
evaluation assertions are all generated from or imported from here. Contracts exist before the implementation —
this is not documentation reverse-engineered from the implementation.

```
contracts/
├── campuspath_contracts/     Pydantic models (the only hand-written source)
├── schema/                   exported JSON Schema (one file per model + _index.json)
├── openapi/campuspath.json   Agent ↔ service OpenAPI 3.1 contract
├── generated/                frontend types generated from OpenAPI
├── scripts/export_schemas.py exporter (supports --check)
└── tests/                    contract tests
```

## Common commands

```bash
make smoke            # < 1 second, used most often
make test             # full contract test suite
make contracts        # re-export schema/ and openapi/
make contracts-check  # assert that the on-disk artifacts match the code
make types            # generate frontend TypeScript types from OpenAPI
```

After changing any model in `campuspath_contracts/`, you **must** run `make contracts`,
or `test_disk_artifacts_match_the_code` will fail.

## Which invariants this layer enforces

The contract layer is not "a collection of data structures" — it is where several D6 BLOCKERs are implemented.
Every one of them has a corresponding test, and each test has itself been verified with a **known-to-fail sample** (Plan §10 H5).

| Invariant | How it is enforced in the contract layer | Test |
|---|---|---|
| B1 Capacity Violation | `CapacitySnapshot` validates the §16.6 formula; construction is rejected if an overload isn't flagged | `test_capacity_and_schedule.py` |
| B2 Protected Block Violation | A `ScheduleProposal` containing a blocking conflict cannot reach `approved` | same as above |
| B3 Unconfirmed Profile Write | A rejected proposal must not bump the version; confirmation must be exactly +1 | `test_profile_write_path.py` |
| B4 Private Reflection Exposure | `EventQualityFeedback` has no free-text field of any kind — it's the only type through which A1 can reach aggregation | `test_boundary_guards.py` |
| B5 Calendar Detail Over-collection | Walks **every** model in the `calendar` module, scanning for calendar-detail and credential terms (not a hand-written list) | same as above |
| B6 Wellbeing False Escalation | A sleep/recovery signal cannot be constructed without the student explicitly setting it | `test_wellbeing_contracts.py` |
| B7 Unauthorized Publication | The contract layer only provides the **transition table and a judgment helper**; enforcement lives in `services/publishing` (every transition passes a role check) | `test_publication_state_machine.py` + `services/publishing/tests` |
| B8 Unbacked Plan Item | `validation_id` is required + regex-checked + looked up against the issuer + **checked for whether the verdict can back it** | `test_validation_binding.py` |
| B9 Metric Re-identification | Sample size below `MIN_CELL_N` must suppress the value; the number of grouping dimensions is limited | `test_aggregation_privacy.py` |
| B10 MetricTuple Field Leakage | Field allow-list + `extra="forbid"` + recursive field-name scan | `test_boundary_guards.py` |
| B11 LLM-free Path Integrity | Four layers: runtime / dependency tree (real distribution names) / source import / dynamic import and raw HTTP | `test_llm_free_path.py`, `llm_free.py` |
| B12 AI Studio path | Judged by **usage pattern** (API key / dedicated endpoint / `genai.Client(` without `vertexai=True`); three enforcement points share `scripts/check_ai_studio.py` | same as above |
| B13 Outreach Consent Integrity | Email field allow-list; the consent receipt and the trigger must be self-consistent | `test_wellbeing_contracts.py` |

## Two design decisions that are easy to misread

**How strong is the guarantee this layer provides?**
`extra="forbid"` and validators block construction and deserialization; `model_copy(update=...)` has also been
overridden to re-validate, and frozen records reject any copy that carries an update at all. `model_construct` still
skips validation — that is pydantic's documented escape hatch, and evaluation needs it to build violation samples.
The difference is that it has to be written explicitly. The guarantees that are truly type-level (no construction path
can violate them) are currently half of B8's shape check and half of B13's allow-list; the rest are combinations of
validator invariants, field scans, and service-layer enforcement.

**Why scan field names instead of relying solely on `extra="forbid"`?**
`extra="forbid"` blocks extra fields passed in at runtime, but it does not block someone later adding a
`title: str` field to `AvailabilityBlock`. That would break B5 without turning any test red.
`guards.py` recursively walks the model's field graph and turns "these fields must not appear on this path" into an
assertion. The one exemption is `CalendarWriteDraft.event_title` — that's the event name we generate and the student
previews before it's written back, not a title read from the student's calendar. The exemption set is pinned by
**exact equality**, so adding another entry turns it red — relying only on "it's written in a test so the diff is
visible" isn't enough, since a leak and its exemption could be added in the same commit.

**Why does `validation_id` get checked three ways?**
Checking shape alone lets a model make up a `val_` plus 32 hex digits and pass; checking issuance alone means an
output missing a field has already propagated as though it were a valid object before it reaches the gate;
**with only those two layers, a genuinely issued Rules verdict of "prerequisite not satisfied" could still back a
plan item** — that proves provenance, not compliance. The third layer checks whether the verdict is in
`BACKING_VERDICTS`.

## Constraints

- This package **must not depend on any model SDK**. The deterministic service plane imports it,
  and if an SDK slips in, the zero-LLM assertions for Rules / Capacity / Wellbeing all break at once.
- Data contract types do not rank anything. Scores are only allowed to appear on A5's output types
  (`MatchResult`, `CoursePlan`).
- Adding or changing a field must be accompanied by bumping `CONTRACTS_VERSION` and running `make contracts`.
