English edition of seed/DATA_DICTIONARY.md, translated for the All Things Agentic Hackathon submission (Aug 2026).

# Synthetic Campus Sandbox — Data Dictionary

Seed version: `seed/1.0.0` · Data baseline date: **2026-09-15** (midterm of the 2026-27 fall semester)

All pages and datasets are labeled `Synthetic / Demo Data`.

## Where the line between real and synthetic data sits

| Data | Source | Notes |
|---|---|---|
| **Course catalog** (code, name, credits, prerequisite/exclusion expressions, CILOs) | **Real**: HKUST's public undergraduate course catalog | Public pages, **contains no student data**. Prerequisite expressions are kept verbatim (e.g. `(COMP 2011 OR COMP 2012 OR COMP 2012H) AND (COMP 2711 OR ...)`), which makes for natural test material for the Rules Engine's prerequisite parsing |
| Course offerings, sections, seat counts, exam times | Synthetic | Not publicly disclosed by the university; we need controllable conflict and full-enrollment scenarios as failure samples |
| Degree programs and graduation requirement groups | Synthetic | Modeled after the real course structure, but credit values and grouping are ours; not a reproduction of the institution's official handbook |
| Students, grades, calendars, experiences, evidence, opportunities, publishers, feedback | **Entirely synthetic** | No real names, emails, student IDs, or grades. The `StudentProfile` contract itself has no name field |

The course snapshot `seed/raw/hkust_catalog/courses.json` is **frozen once ingested**: the Gold Label is bound to it,
and since the university's page can change at any time, freezing it is the only way to guarantee "judges see the
same scenario every time." The HTML cache itself is not checked in.

## Generation and validation

```bash
make seed          # generate full + tiny
make seed-reset    # delete old artifacts and regenerate, with a byte-for-byte comparison of the two builds
make seed-check    # 16 cross-table consistency checks
make seed-selftest # verify the checker actually fails, using 16 known contradictions
```

Artifacts land in `seed/generated/<profile>/` (not checked in, reproducible by the generator), each carrying a
`manifest.json`: seed version, baseline date, per-table record counts, and the first 16 characters of a SHA-256
checksum.

## Two size profiles

| Profile | Purpose | Contents |
|---|---|---|
| `full` | Demo, evaluation, acceptance | 3 degree programs / 12 students / 96 courses / 143 opportunities, meets every lower bound in Spec §11.2 |
| `tiny` | smoke tests and unit tests (Plan §10.5) | 1 degree program / 1 persona, builds in < 0.1 second |

`tiny` is shrunk by **only building a single degree program**, not by "only keeping N courses" —
the latter would leave a degree program referencing courses that were trimmed out, creating the cross-table
contradiction Spec §11.5 explicitly forbids.

## What each of the three deep personas is responsible for demonstrating

These are not three roughly similar students — each one is a specific scenario that has to be demonstrated.

| Persona | Program / year | What it demonstrates | Key setup |
|---|---|---|---|
| **A · Explorer** | BSc COMP / sophomore | G3 multi-objective (primary + candidate), discovery cost, **B6 counterexample** | **No sleep window or recovery preference set** → wellbeing escalation must not fire no matter how busy the calendar is |
| **B · Sprinter** | BBA ISOM / junior | Wellbeing vertical slice, capacity overload replanning | Sleep window already set at 00:30–07:30, hard Saturday caregiving constraint, 6 existing commitments → weekly disposable capacity is negative |
| **C · Pivoter** | BEng IEDA / junior | Goal review, primary/candidate goal divergence, course trade-offs | Primary goal confidence 0.35 and declining, candidate goal confidence 0.55; has visa-related constraints |

There are also 9 lightweight students (STU-D…STU-L), covering four class years and five development patterns,
used to get grouped aggregation up to `MIN_CELL_N`.

## Data tables

| File | Contract type | Record count (full) | Notes |
|---|---|---:|---|
| `programs.json` | `AcademicProgram` | 3 | BSc COMP / BBA ISOM / BEng IEDA |
| `degree_requirements.json` | `DegreeRequirement` | 18 | 5–7 requirement groups per program |
| `courses.json` | `CourseCatalogItem` | 96 | Real course data |
| `course_offerings.json` | `CourseOffering` | 558 | Includes `full` / `waitlist` states, for "full enrollment" samples |
| `students.json` | `StudentProfile` | 12 | No name field |
| `student_display.json` | — | 12 | Display pseudonyms, obviously pseudonymous at a glance |
| `student_course_records.json` | `StudentCourseRecord` | 184 | Arranged into historical semesters in prerequisite-tier order |
| `experiences / projects / achievements / skills / evidence / notes` | corresponding contracts | 4 / 3 / 2 / 8 / 7 / 3 | Only the deep personas have these |
| `goals.json` | `Goal` | 14 | Primary goals + candidate goals |
| `calendar_connections.json` | `CalendarConnection` | 3 | **No token field** |
| `availability_blocks.json` | `AvailabilityBlock` | 588 | 6 weeks × 3 people; **no title/attendees/location** |
| `capacity_snapshots.json` | `CapacitySnapshot` | 18 | Satisfies the §16.6 formula; both overloaded and non-overloaded cases present |
| `opportunities.json` | `Opportunity` | 143 | Includes 3 extra records injected as failure samples |
| `opportunity_meta.json` | — | 140 | The **generation rule** behind each opportunity (Spec §11.5) |
| `publisher_grants / publication_submissions / moderation_decisions / scope_violations` | corresponding contracts | 10 / 24 / 17 / 4 | At least one sample for every terminal state of the state machine |
| `event_quality_feedback.json` | `EventQualityFeedback` | 40 | **No student_id, no free text** |
| `metric_tuples.json` | `MetricTuple` | 12 | Cross-domain tuples, the physical embodiment of B10 |
| `profile_update_proposals / profile_change_events` | corresponding contracts | 24 / 20 | Covers all four branches: confirmed / modified / **rejected** / pending |
| `memory_entries.json` | `MemoryEntry` | 15 | Includes the `rejection` type, the evidence source for T6 |
| `gold_set.json` | — | see below | Gold Label |
| `failure_cases.json` | — | 16 | **Full coverage** of the sixteen categories in Spec §11.3 |

Every record is a contract-layer model instance before serialization, already validated by Pydantic:
the dataset cannot contain a record that violates B1/B2/B3/B6/B9, because those objects simply cannot be
constructed in the first place.

## Gold Set

| Dataset | Count | Lower bound (D6.5) | Contents |
|---|---:|---:|---|
| Four-state eligibility | 60 | 60 | **15 of each** of the four states — sampling in sequence alone would produce a set that's almost entirely `eligible_now`, which would make T2 untestable |
| Course constraints | 40 | 40 | Requirement-group membership, prerequisite status, offering semester, schedule conflicts |
| Replanning scenarios | 12 | 12 | Covers all 11 `ReplanTriggerType` categories, each stating explicitly what remains **unaffected** |
| Failure samples | 16 categories | 12 categories | see below |
| Memory regression | 20 | 20 | Already-rejected / already-completed items, verifying no duplicate recommendations |

**Labeling status**: all labels are `rule_generated` (Plan R8: rule-generated first draft, human review only for
verification). **Until human review is complete, T1/T2/T3 figures computed from it are only a self-assessment and
cannot be treated as a validated accuracy figure.** The review schedule is in Plan §5, non-blocking item 5.

Every label carries `reasons`, stating the basis for the judgment and quoting the original rule text (D6.5 rule ②);
in case of conflict, the original source text takes precedence over model output (rule ③);
the Gold Set carries a `seed_version`, and once frozen, any change must bump it (rule ④).

The Gold Label judgment logic is **deliberately written separately from the WP5 Rules Engine** —
using the same code to both generate labels and evaluate against them would be grading your own homework.

### Four-state merge priority

When an opportunity matches multiple rules, they are merged by this priority, encoded in `goldset.STATE_PRECEDENCE`:

```
ineligible_current_cycle > future_eligible > needs_confirmation > eligible_now
```

`eligible_now` ranking last is deliberate: it directly corresponds to T2 (misclassifying an ineligible item as
eligible), which is a more critical metric than T1.

## Failure samples (full coverage of the sixteen categories in Spec §11.3)

| # | Category | Expected behavior | **What must not happen** |
|---:|---|---|---|
| 01 | Expired but page still live | Judged `ineligible_current_cycle` | Must not be treated as applicable just because the page is reachable |
| 02 | Ineligible in freshman year, reachable by junior year | Judged `future_eligible` + bridging action | Must not be permanently deleted |
| 03 | Ambiguous year-level requirement | Judged `needs_confirmation` | Must not be eliminated by a uniform year-level assumption |
| 04 | Conflicting deadlines from two sources | Flagged as conflicting, showing both dates | Must not silently pick one |
| 05 | Different titles, duplicate content | Deduplicated and merged, keeping both sources | Must not appear twice in the Top-N |
| 06 | Well-promoted but consistently poor feedback | Quality confidence downgraded and replaced | Must not output the raw individual feedback text |
| 07 | High-quality activity but too basic for this student | Personal-fit weight lowered | Must not lower the **global** quality score based on this |
| 08 | Conflicts with a course or a rest boundary | Shows a blocking conflict | Must not silently schedule into a protected block |
| 09 | Workload field missing | Flagged as uncertain | Must not default to 0 hours |
| 10 | Similar activity already done | Not recommended again, or the difference is explained | Must not be re-recommended under a different name |
| 11 | Career goal satisfied but graduation credits insufficient | Rules reject and point out the missing group | Graduation hard constraints must not be offset by career score |
| 12 | Prerequisite unmet / not offered / full / conflicting | Each case judged separately | Must not be uniformly shown as "unavailable" |
| 13 | Calendar gap is actually protected time | Not counted as Usable Free Time | Must not be treated as compressible free time |
| 14 | Resume extraction error / expired credential / rejected write | Event kept but not written to Profile | Must not silently write to the Canonical Profile |
| 15 | Out-of-scope submission (four reasons) | All intercepted and logged | Must not be intercepted without a record |
| 16 | Update not re-reviewed / still shown after cancellation | Reverted to `in_review`; taken down | Must not skip review and go straight to published |

Every entry states **what must not happen** — a sample that only records expected behavior can't be falsified.

## Consistency validation

`make seed-check` runs 16 cross-table checks: course/student/evidence references, prerequisite ordering, unique
opportunity IDs, Gold Set references and judgment basis, four-state coverage, publisher references, MetricTuple
de-identification, real-PII shape scanning, Synthetic labeling, size lower bounds, Gold lower bounds, falsifiability
of failure samples, and rejected proposals not being written.

`make seed-selftest` injects 16 **known contradictions** into the dataset and asserts that **the corresponding
check** actually fails. Asserting only "some check failed" isn't enough — that would let an overly broad check mask
every other failure.

## Determinism

- The time baseline is a constant, not `date.today()`;
- All randomness is derived via `rng.stream(namespace)`, namespaced so that changing one table doesn't shift every
  other table out of alignment;
- Seeds are derived via SHA-256, not the built-in `hash()` (which is randomized by `PYTHONHASHSEED`);
- Iteration is always sorted, never relying on dict/set iteration order;
- `make seed-reset` does a **byte-for-byte comparison** of two builds and errors on any mismatch.
