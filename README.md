# Reference Check Analyzer (LangGraph demo)

Replaces the manual step where a background-check analyst reads a
reference (an open-text call transcript/email, or a structured yes/no
verification form) and compares it against what the candidate claimed,
deciding whether anything needs a closer look.

## Package layout

```
refcheck/
  config.py                generic model-tier resolution + every tunable setting
  prompts.py                every LLM system prompt
  request_builders.py       every (system, user_message) pair builder
  schemas.py                Pydantic models, incl. REF1/REF2 type codes
  validation.py              input sanity checks + injection-pattern warnings
  logging_config.py          structured JSON logging + PII scrubbing

  llm/
    base.py                  BaseLLMProvider abstract class (all shared logic)
    anthropic_provider.py    AnthropicProvider  (real-time)
    bedrock_provider.py      BedrockProvider    (real-time, Converse API)
    openrouter_provider.py   OpenRouterProvider (real-time)
    providers.py              get_provider() factory -- LLM_PROVIDER env var
    batch/
      base.py                 shared BatchItem / BatchItemResult
      anthropic_batch.py       Anthropic Message Batches API backend
      bedrock_batch.py         AWS Bedrock batch inference backend (S3-based)

  api/
    store.py                  in-memory job store (queued/running/completed/failed)
    schemas.py                  API request/response models
    runner.py                    executes a check via the SAME candidate_graph, updates the store
    main.py                       FastAPI app: submit / poll / schema / health endpoints

  nodes/
    reference_nodes.py        ReferenceCheckNodes -- REF1 + REF2 flow methods
    candidate_nodes.py         CandidateNodes -- dispatch, cross-check, aggregate

  graphs/
    reference_graph.py         builds the REF1 and REF2 single-reference graphs
    candidate_graph.py          builds the multi-reference candidate graph

  pipelines/
    batch_runner.py             bulk/offline pipeline (either batch backend)

  data/
    sample_data.py               four REF1 single-reference test cases
    sample_data_multi.py          six candidate-level cases (REF1/REF2/mixed)

run_demo.py / run_demo_multi.py / run_batch_demo.py   CLI entry points
streamlit_app.py                                        web UI (submits to the API)
tests/                                                  unit tests, no API key needed
Dockerfile / docker-compose.yml / .env.example / .dockerignore
```

Every subpackage has a single, narrow job: `llm/` never imports
`nodes/`; `nodes/` never imports `pipelines/`; `graphs/` sits between
`nodes/` and the CLI scripts. The dependency direction is one-way:
`pipelines` and `graphs` depend on `nodes`, which depends on `llm` and
`schemas`/`request_builders`/`config` -- never the reverse.

## Architecture at a glance

```
llm/providers.py ── get_provider() ──▶ AnthropicProvider / BedrockProvider / OpenRouterProvider
                                          all subclass llm/base.py:BaseLLMProvider
                                                       │
                                                       ▼
nodes/reference_nodes.py: ReferenceCheckNodes(provider)   nodes/candidate_nodes.py: CandidateNodes(provider)
  - REF1 methods (extract_facts, diff_facts, ...)           - run_reference (dispatch by `type`)
  - REF2 methods (evaluate_yes_no_form, ...)                 - cross_check_references / score_overall
  - shared score_confidence / route_review
                                                       │
                                                       ▼
graphs/reference_graph.py:                    graphs/candidate_graph.py:
  build_open_ended_graph()  (REF1)               build_candidate_graph()
  build_yes_no_graph()      (REF2)                 (Send-based fan-out, dispatches each
                                                      reference by `type` to the right subgraph)
                                                       │
                                                       ▼
                                    pipelines/batch_runner.py
                                    (bulk/offline via llm/batch/anthropic_batch.py
                                     OR llm/batch/bedrock_batch.py -- same business
                                     logic, reused directly from nodes/)
```

Everything downstream of `get_provider()` is written against
`BaseLLMProvider`'s interface and never imports `anthropic`/`boto3`/`openai`
directly. Switching providers, in real-time or batch, is an environment
variable / CLI flag, not a code change.

## Two reference types: REF1 and REF2

`ReferenceInput.type` picks which shape a given reference is:

- **`"REF1"`** (`schemas.REF_TYPE_OPEN_TEXT`) -- an open-text
  transcript/email (`raw_input`). Runs `extract_facts` (LLM) →
  `diff_facts` (Python) → optionally `explain_discrepancies` (LLM) →
  scoring → summary.
- **`"REF2"`** (`schemas.REF_TYPE_YES_NO`) -- a structured yes/no
  verification form (`yes_no_form`: confirmed_title / confirmed_dates /
  confirmed_company / would_rehire / performance_concerns, each
  `"yes"/"no"/"unsure"`, plus optional free-text `additional_comments`).
  Since the answers already ARE the extracted facts, this skips
  `extract_facts` entirely -- `evaluate_yes_no_form` (pure Python)
  builds discrepancies/red-flags directly from the form, and only calls
  an LLM (`sentiment_from_comments`, reusing the exact same prompt as
  REF1's `sentiment_and_redflags`) if the reference left comments.

Routing on `type` happens in exactly two places:
`graphs/candidate_graph.py:fan_out_references` (builds the right
`Send` payload per reference) and
`nodes/candidate_nodes.py:CandidateNodes.run_reference` (invokes the
right compiled subgraph). Both flows are separate compiled graphs
sharing one `ReferenceCheckNodes` instance and converging on the same
`score_confidence` / `route_review` / `flag_for_human_review` /
`auto_summarize` methods -- one candidate can freely mix both types
across their references (see `mixed_reference_types` in
`data/sample_data_multi.py`).

## Provider abstraction

`llm/base.py:BaseLLMProvider` owns everything identical across
providers: retry/backoff, timeout handling, forced structured output via
tool-calling, schema validation, logging. Each concrete provider
implements only three things:

- `_execute(...)` -- the actual API call
- `_extract_tool_input(...)` -- pulling the tool-call result out of that
  provider's response shape
- `_is_retryable_exception(...)` -- which exceptions mean "try again"

`llm/providers.py:get_provider()` instantiates the right one by name
(default from `LLM_PROVIDER` env var), with lazy imports so you don't
need `boto3` installed unless you actually select Bedrock.

## Generic model resolution

No code anywhere hardcodes a model ID string. `config.MODEL_TIERS` is a
`provider -> tier -> model_id` table (tiers: `"extraction"` for
pattern-extraction, `"reasoning"` for tasks needing more judgment).
`config.get_model(provider, tier)` resolves one entry, with an env var
override (`MODEL_<PROVIDER>_<TIER>`). Every `BaseLLMProvider` subclass
exposes `self.get_model(tier)`, delegating to
`config.get_model(self.PROVIDER_NAME, tier)`. The batch pipeline uses
the exact same function -- `config.get_model(batch_provider, tier)` --
so tiering is identical whether a model is called synchronously or via
a batch job.

## Batch API: two backends

`pipelines/batch_runner.py` is a separate pipeline for bulk/offline
processing -- not a mode switch on the real-time graphs. It runs the
same 8-phase pipeline (mirroring both REF1 and REF2 real-time flows)
against either backend, selected via `batch_provider`:

**`llm/batch/anthropic_batch.py`** -- Anthropic's Message Batches API.
Inline: you submit a list of requests directly, poll a batch resource,
read results back per `custom_id`. Simple, one call per phase.

**`llm/batch/bedrock_batch.py`** -- AWS Bedrock's batch inference API.
Structurally different: S3-based. You upload a JSONL file of requests
to S3, call `CreateModelInvocationJob` (a different `bedrock` control-
plane client, not `bedrock-runtime`), poll the job resource, then read
result JSONL file(s) back out of a different S3 location. **Key
constraint: one Bedrock batch job runs against exactly one model** --
there's no per-request model field like Anthropic's Batch API, so this
module transparently groups items by model and submits one job per
distinct model, hidden behind the same `run_batch_sync(items) ->
dict[custom_id, BatchItemResult]` interface `anthropic_batch.py`
exposes. Requires additional setup: an S3 bucket and an IAM role the
batch job assumes (see `.env.example`'s `BEDROCK_BATCH_*` variables).

Both backends resolve models via `config.get_model(batch_provider, tier)`
-- the same generic tiering as the real-time providers, just applied to
whichever batch backend is active.

```bash
python run_batch_demo.py                     # Anthropic batch (default)
python run_batch_demo.py --provider bedrock   # Bedrock batch
```

**Verification note:** both batch backends' method/field names match
each provider's documented API as of this codebase's last verification,
but neither was confirmed against a live call in this environment (no
network access during development). `bedrock_batch.py`'s docstring has
additional caveats specific to it (unenforced minimum record count,
unpredictable output filenames handled via directory listing rather
than a fixed name) -- read it before using this against a real AWS
account.

## Design principles carried through the whole codebase

- **Structured diff, not free-text comparison (REF1).** `extract_facts`
  (LLM) pulls facts into the same schema as the candidate's claims;
  `diff_facts` (pure Python) does the actual comparison deterministically.
- **No LLM extraction step to get wrong (REF2).** The form's structured
  answers are compared directly -- there's nothing to extract.
- **Fan-out / fan-in, multi-reference.** `graphs/candidate_graph.py`
  uses LangGraph's `Send` API to fan out across however many references
  a candidate has (either type, or a mix), then `cross_check_references`
  flags where references disagree with EACH OTHER (not just vs. the
  candidate's claims).
- **No duplicated business logic between real-time and batch.**
  `pipelines/batch_runner.py` imports `diff_facts`,
  `evaluate_yes_no_form`, `score_confidence`, `route_review`,
  `cross_check_references`, `score_overall`, and every routing method
  directly from `ReferenceCheckNodes(llm_provider=None)` /
  `CandidateNodes(llm_provider=None)` -- there is exactly one
  implementation of each piece of business logic in this codebase.

## API service + Streamlit UI

Instead of only running against the static sample data in `data/`, the
pipeline is exposed over HTTP so an external caller (or the bundled
Streamlit form) can submit a real candidate check and either poll for
the result or receive it via webhook.

**`refcheck/api/main.py`** (FastAPI):
```
POST /api/v1/checks         submit a check -> {check_id, status: "queued"} (202, returns immediately)
GET  /api/v1/checks/{id}    poll -> {check_id, status, result, error}
GET  /api/v1/schema         JSON schema for ClaimedDetails / ReferenceInput / YesNoReferenceForm
GET  /health                liveness check
```

Submission is async on purpose -- a real reference check involves
several LLM calls (potentially in parallel across references) and can
take seconds to tens of seconds, so the endpoint queues the work as a
FastAPI `BackgroundTask` and returns a `check_id` immediately rather
than holding the connection open. The caller has two ways to get the
result, and can use either or both:

- **Pull**: poll `GET /api/v1/checks/{check_id}` until `status` is
  `"completed"` or `"failed"`.
- **Push**: pass `callback_url` in the submit request; when the check
  finishes, the full result is POSTed there as JSON (best-effort, logged
  on failure, not retried -- see `runner.py:_send_callback`).

The API calls the exact same `build_candidate_graph()` used by
`run_demo_multi.py` -- no separate logic. The job store
(`refcheck/api/store.py`) is a simple in-memory dict behind a lock,
explicitly documented as a demo-grade choice (lost on restart, not
shared across worker processes) -- swap it for Redis/a database/a task
queue for production, its interface (`create` / `get` / `mark_*`) is
small enough that nothing else needs to change.

**`streamlit_app.py`**: a form that builds up a candidate + references,
adapts its fields to the reference type you pick per-reference (a text
area for REF1, five yes/no dropdowns + a comments box for REF2), submits
to the API, and polls (with an optional auto-refresh checkbox) until the
result is ready, then renders it -- per-reference discrepancies/red
flags/summary, cross-reference flags, overall summary.

```bash
# terminal 1
uvicorn refcheck.api.main:app --reload --port 8000
# terminal 2
API_BASE_URL=http://localhost:8000 streamlit run streamlit_app.py
```

or via Docker (see below) -- `docker compose up api streamlit` runs both
with `API_BASE_URL` wired automatically.

## Running it

### Locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY (and/or Bedrock/OpenRouter
                        # credentials if you'll switch LLM_PROVIDER)
export $(grep -v '^#' .env | xargs)   # or use direnv / your own method

python run_demo.py                              # single-reference, REF1 only
python run_demo_multi.py                         # multi-reference, REF1+REF2+mixed
python run_demo_multi.py yes_no_with_concerns
python run_demo_multi.py mixed_reference_types

python run_batch_demo.py                          # bulk/offline, Anthropic batch
python run_batch_demo.py --provider bedrock        # bulk/offline, Bedrock batch

# API + UI (see "API service + Streamlit UI" above for details)
uvicorn refcheck.api.main:app --reload --port 8000
streamlit run streamlit_app.py

pytest tests/ -v                                    # no API key needed

# switch real-time providers without touching any code:
LLM_PROVIDER=bedrock AWS_REGION=us-east-1 python run_demo_multi.py
LLM_PROVIDER=openrouter OPENROUTER_API_KEY=sk-or-... python run_demo_multi.py
```

### Docker

```bash
cp .env.example .env
docker compose build

docker compose up api streamlit          # full stack: API on :8000, UI on :8501
docker compose run --rm demo
docker compose run --rm demo-multi
docker compose run --rm batch            # Anthropic batch
docker compose run --rm batch-bedrock    # Bedrock batch
docker compose run --rm test

# or without compose:
docker build -t reference-check-agent .
docker run --env-file .env reference-check-agent run_demo_multi.py
docker run --env-file .env reference-check-agent -m pytest tests/ -v
```

## Production-readiness notes

**Implemented:**
- **Modular package structure** -- `llm/`, `nodes/`, `graphs/`,
  `pipelines/`, `data/` each own one concern; dependencies flow one way.
- **Provider abstraction + dynamic selection** -- one env var
  (`LLM_PROVIDER`) switches the real-time pipeline between Anthropic,
  Bedrock, and OpenRouter; `--provider` switches the batch pipeline
  between Anthropic and Bedrock batch backends.
- **Generic, provider-agnostic model tiering** -- `config.get_model(provider, tier)`
  is the only place a model ID string is constructed, used identically
  by real-time and batch code paths.
- **Two reference input types (REF1/REF2)**, routed consistently through
  both the real-time graphs and the batch pipeline, sharing scoring and
  summary logic.
- **HTTP API + UI** -- async submit/poll (with optional webhook
  callback) over the same real-time graph, no separate business logic;
  a Streamlit form that adapts to REF1/REF2 per reference.
- **Retry/backoff, timeouts, structured logging with PII scrubbing,
  input validation, concurrency caps, per-reference failure isolation**
  -- unchanged in substance from prior iterations, just reorganized into
  the new package layout.
- **Unit tests** covering every pure-Python method/function, including
  REF1/REF2 dispatch shape validation, model resolution, and the batch
  custom_id convention -- all runnable without an API key.
- **Containerization** -- `Dockerfile` + `docker-compose.yml` +
  `.env.example` document every configurable environment variable,
  including the Bedrock-batch-specific S3/IAM ones.

**Deliberately left as extension points:**
- **Secrets management** -- API keys/IAM details come from env vars;
  production should use a secrets manager instead.
- **Job store durability** -- `refcheck/api/store.py` is in-memory: lost
  on restart, not shared across multiple API worker processes. Fine for
  a single-process demo; swap for Redis/a database/a task queue before
  running more than one API worker.
- **API auth** -- no authentication/authorization on the FastAPI
  endpoints; add an API key or OAuth layer before exposing this beyond
  a trusted network.
- **Webhook delivery guarantees** -- `_send_callback` is fire-and-forget
  with no retry; a transient failure on the caller's end means the
  result is only reachable via polling for that check.
- **PII at rest / audit logging** -- no encryption-at-rest or audit
  trail for report access.
- **True human-in-the-loop persistence** -- `overall_flag_for_review`
  produces a summary but doesn't pause the graph for a checkpointed
  human decision.
- **Observability beyond logging** -- no distributed tracing or
  per-candidate cost/token tracking.
- **Bedrock batch minimum-record enforcement** -- `bedrock_batch.py`
  warns but doesn't block a too-small batch; a real submission below
  AWS's minimum will be rejected at the API level.
- **A model that doesn't respect forced tool choice** raises
  `StructuredCallError` immediately; no automatic fallback to a
  different model.

## Extending

- Swap the crude seniority-word list in
  `ReferenceCheckNodes.diff_facts` for something more robust.
- Add a fourth `BaseLLMProvider` subclass (Azure OpenAI, Vertex AI,
  etc.) -- implement the three abstract methods, register it in
  `llm/providers.py:get_provider()`, done.
- Add a fourth batch backend the same way -- implement
  `run_batch_sync(items) -> dict[custom_id, BatchItemResult]` matching
  `llm/batch/base.py`'s shapes, register it in
  `pipelines/batch_runner.py:_get_batch_backend()`.
- Add a real LangGraph checkpointer + `interrupt()` before the overall
  decision for true human-in-the-loop review.
- `cross_check_references` only compares REF1 references' extracted
  fields today (REF2 references contribute empty `extracted_facts`, so
  they're naturally excluded) -- extend with a parallel cross-check over
  REF2 forms' `confirmed_*` answers if that granularity matters.
