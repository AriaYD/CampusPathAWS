English edition of infra/README.md, translated for the All Things Agentic Hackathon submission (Aug 2026).

# infra — GCP resources (WP0)

```bash
bash infra/bootstrap.sh            # dry-run: only prints what it would do
bash infra/bootstrap.sh --apply    # actually create resources (idempotent, safe to re-run)
bash infra/verify.sh               # read-only measurement: do the resources actually exist, are the permissions actually correct
bash infra/cost.sh                 # daily cost check
bash infra/moodle.sh status        # Moodle sandbox status
```

## Three design decisions

**Dry-run by default.** Every script that would change resources only prints what it would do unless `--apply` is passed.
An accidental run should never generate a bill.

**`bootstrap` and `verify` are separate.** `bootstrap.sh` finishing without an error only means the command returned 0;
it does not mean the resources were actually created or that the permissions actually took effect. `verify.sh` goes and
**fetches measured values** (Plan §10 H3). The most valuable part of it is the **negative checks**: A4's service account
**must not** have student-data permissions. Positive checks can only catch "forgot to create it"; negative checks are what
catches "granted too much."

**The Moodle VM gets its own script.** It is the only resource with real ongoing monthly cost.
Folding it into bootstrap would turn "run the initializer" into "casually spin up a machine."
The grant credits expire on 2026-09-27 — don't let an idle VM eat into the budget that should go to model calls.

## Resource inventory

| Resource | Name | Notes |
|---|---|---|
| Firestore | `(default)`, Native mode | Canonical Profile + append-only Event Store |
| Cloud Storage | `campuspath-evidence-<project>` | Private Vault, isolated by `student_id` prefix; public access blocked |
| Artifact Registry | `campuspath` | Container images |
| Service account | `campuspath-student-runtime` | A0/A1/A2/A3/A5: model + Firestore + Vault + trace |
| Service account | `campuspath-opportunity-runtime` | **A4: model and trace only, no student-data permissions at all** |
| Service account | `campuspath-moodle-reader` | Read-only Secret access, does not touch Firestore |
| Secret Manager | see `REQUIRED_SECRETS` in `config.sh` | only creates empty secret containers, values are injected manually |
| GCE | `campuspath-moodle` | Moodle sandbox, toggled on demand + shut down overnight |

## Why the two runtimes use two separate service accounts

Spec §8.1 separates the Student Path Runtime from the Opportunity Operations Runtime,
not for scaling reasons but as a **security boundary**: A4 is the only place in the system that
handles untrusted input (external scraped content and Publisher submissions).

If the two shared one service account, that boundary would rest entirely on developer discipline in the code.
That's why `bootstrap.sh` does **not** grant `roles/datastore.user` in A4's role set,
and `verify.sh` actively checks whether anyone later added it back.
Before changing anything here, read D2's security contract tests first.

## Secrets

`bootstrap.sh` only creates **empty** Secret containers, never values. Injection is done like this:

```bash
printf '%s' "$VALUE" | gcloud secrets versions add campuspath-moodle-ws-token --data-file=-
```

Values never go into the repo, the docs, or commit messages (Plan §9).
`verify.sh` reports which secrets "exist but have no value" — those features will fail at runtime,
and it's better to know that ahead of time than to find out live during the demo.

## Strands standalone deployment (AWS "Agents for Humans" submission)

`infra/deploy_strands.sh` only touches two **brand-new, independent** Cloud
Run services: `campuspath-api-strands` / `campuspath-web-strands`. The
pre-existing `campuspath-api` / `campuspath-web` are still under judging for
an earlier Google hackathon (through 2026-10-01); every subcommand does a
literal string check against the target service name and refuses to touch
the existing ones.

```bash
bash infra/deploy_strands.sh --help              # list subcommands and env vars
DRY_RUN=1 bash infra/deploy_strands.sh all       # print the gcloud commands only
bash infra/deploy_strands.sh all                 # actually run it (or make deploy-strands)
```

Subcommands: `secrets` (AWS credentials → Secret Manager, plus IAM grant),
`api` (builds the root `Dockerfile` and deploys with
`CAMPUSPATH_AGENT_RUNTIME=agentcore` + Bedrock), `web` (builds
`apps/web/Dockerfile`, points `CAMPUSPATH_API_ORIGIN` at the new API's
URL), `status` (read-only: URLs / revisions / health check), `all` (runs
the first four in order).

Two design choices differ from `bootstrap.sh`/`verify.sh`:
- **`DRY_RUN=1` is an environment variable, not an `--apply` flag** — this
  script actually creates Cloud Run services and Secret Manager secrets, so
  it doesn't reuse `config.sh`'s default-dry-run `run()`/`run_idempotent()`
  convention. A real run wraps each gcloud call in a scoped `set -x` so the
  exact expanded command is printed to stderr before it executes; `DRY_RUN=1`
  prints the equivalent preview and executes nothing.
- **AWS credentials and the freshly generated web `AUTH_SECRET`/
  `CAMPUSPATH_DEMO_PASSCODE` are always masked in printed previews** — the
  `secrets` subcommand reads from a local AWS profile (`AWS_PROFILE`,
  default `campuspath`) via `aws configure get`, falling back to parsing
  `~/.aws/credentials` with awk if the `aws` CLI isn't installed; the value
  passes through exactly one pipe into `gcloud secrets versions add
  --data-file=-` and never appears in any `printf` or `set -x` trace.

The service account isn't hardcoded: the `api`/`secrets` subcommands do one
read-only `gcloud run services describe campuspath-api ...
--format='value(spec.template.spec.serviceAccountName)'` to measure which
service account the live API actually uses (as of 2026-09-12 that's Cloud
Run's default compute service account, not the `campuspath-student-runtime`
that `bootstrap.sh` creates — the live service was originally deployed with
`gcloud run deploy --source .` without an explicit `--service-account`), and
the new service copies that same account; override with the
`API_SERVICE_ACCOUNT` env var. The health path `/healthz` (no `/v1` prefix)
and `/v1/ops/agents` are taken from the actual routes in
`services/api/campuspath_api/app.py`, not guessed.

## Known rough edges

- **`gcloud` calls are slow.** Even a dry-run has to `describe` each resource one at a time to determine whether it exists,
  so a full pass on this machine takes several minutes. There's no way around it short of giving up idempotency.
- **`cost.sh` doesn't give an exact figure.** Getting an accurate number would require exporting billing data to BigQuery.
  Rather than show an inaccurate number, it accurately answers "what is currently being billed by time right now."
- **The Vertex region is measured, not asserted.** `VERTEX_LOCATION` in `config.sh` is only a default;
  `verify.sh` queries the API for the real value at runtime. Which models a region supports changes over time,
  so hardcoding it in the docs would eventually go stale.
- **The AgentCore Runtime trusts the system prompt in the payload.** (Noted 2026-09-12; not fixed in that pass.)
  Whatever arrives as `request.system` goes straight into the model's system slot. The only thing backing that is
  deployment configuration: `invoke_agent_runtime` is IAM-gated, and the sole caller is the Cloud Run service account.
  So "the system prompt only ever comes from instructions written in this repo" is guaranteed by *configuration*,
  not by *shape* — add a second caller, or leak that credential, and it stops holding. The real fix is to move the six
  system prompts into the Runtime and let the payload carry only `purpose` plus data blocks, so that splicing external
  content into the system prompt becomes impossible at the protocol level. There is a matching TODO in the entrypoint
  (`agents/cloud/agentcore_app.py::_checked_request`).
  The half that *is* done: every payload field is type-checked and capped at 32 KiB per block (`MAX_FIELD_BYTES`),
  and anything out of bounds comes back as `{"error": ...}` instead of raising.
- **The staged bundle must be verified on Python 3.12.** `agentcore.json` declares `runtimeVersion: PYTHON_3_12`, and
  `verify_staged.py` prints the interpreter it ran on and fails when that is not 3.12.x (escape hatch:
  `CAMPUSPATH_STAGED_PY_OK=1`). A green run on 3.14 proves something about a different environment.
