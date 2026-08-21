const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun,
  AlignmentType, LevelFormat, BorderStyle,
  Table, TableRow, TableCell, WidthType, ShadingType, VerticalAlign,
} = require("docx");
const fs = require("fs");

const DIAG = "/home/claude/refcheck-agent/docs/diagrams";
const OUT = "/home/claude/refcheck-agent/docs/build/Reference_Check_Analyzer_Technical_Architecture.docx";

const US_LETTER = { width: 12240, height: 15840 };
const NAVY = "1F3864";
const ACCENT = "5B84B1";
const GREY = "595959";
const CODE_BG = "F2F2F2";

function h1(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 } });
}
function h2(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 } });
}
function body(text, opts = {}) {
  return new Paragraph({ children: [new TextRun({ text, ...opts })], spacing: { after: 160 } });
}
function bullet(text, level = 0) {
  return new Paragraph({ text, numbering: { reference: "bullets", level }, spacing: { after: 80 } });
}
function code(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Consolas", size: 19 })],
    shading: { type: ShadingType.CLEAR, fill: CODE_BG },
    spacing: { after: 160 },
    indent: { left: 200 },
  });
}
function caption(text) {
  return new Paragraph({
    children: [new TextRun({ text, italics: true, size: 20, color: GREY })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
  });
}
function image(path, widthPx, ratio = 0.62) {
  return new Paragraph({
    children: [new ImageRun({
      type: "png", data: fs.readFileSync(path),
      transformation: { width: widthPx, height: Math.round(widthPx * ratio) },
    })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
  });
}
function hr() {
  return new Paragraph({
    text: "",
    border: { bottom: { color: "AAAAAA", space: 1, style: BorderStyle.SINGLE, size: 6 } },
    spacing: { after: 200 },
  });
}

function cell(text, opts = {}) {
  return new TableCell({
    width: { size: opts.width || 2000, type: WidthType.DXA },
    shading: opts.header ? { type: ShadingType.CLEAR, fill: "DCE8FA" } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      children: [new TextRun({ text, bold: !!opts.header, font: opts.mono ? "Consolas" : undefined, size: opts.mono ? 18 : 20 })],
    })],
  });
}

function apiTable() {
  const widths = [1500, 3600, 4800];
  const header = new TableRow({
    tableHeader: true,
    children: [
      cell("Method / Path", { header: true, width: widths[0] }),
      cell("Purpose", { header: true, width: widths[1] }),
      cell("Response", { header: true, width: widths[2] }),
    ],
  });
  const rows = [
    ["POST /api/v1/checks", "Submit a candidate + references (REF1/REF2/mixed). Returns immediately; the actual run happens in the background.", "202 -> { check_id, status: \"queued\" }"],
    ["GET /api/v1/checks/{check_id}", "Poll for status and, once done, the full result.", "{ check_id, status, result, error }"],
    ["GET /api/v1/schema", "JSON schema for the request shapes -- lets a client discover REF1 vs REF2 field requirements dynamically.", "ClaimedDetails / ReferenceInput / YesNoReferenceForm schemas"],
    ["GET /health", "Liveness check.", "{ status: \"ok\" }"],
  ];
  return new Table({
    width: { size: 9900, type: WidthType.DXA },
    columnWidths: widths,
    rows: [header, ...rows.map((r) => new TableRow({
      children: [
        cell(r[0], { width: widths[0], mono: true }),
        cell(r[1], { width: widths[1] }),
        cell(r[2], { width: widths[2], mono: true }),
      ],
    }))],
  });
}

function tierTable() {
  const widths = [2400, 3600, 3900];
  const header = new TableRow({
    tableHeader: true,
    children: [
      cell("Provider", { header: true, width: widths[0] }),
      cell("Extraction tier (default)", { header: true, width: widths[1] }),
      cell("Reasoning tier (default)", { header: true, width: widths[2] }),
    ],
  });
  const rows = [
    ["Anthropic (direct)", "claude-haiku-4-5", "claude-sonnet-4-6"],
    ["AWS Bedrock", "anthropic.claude-haiku-4-5-v1:0", "anthropic.claude-sonnet-4-6-v1:0"],
    ["OpenRouter", "anthropic/claude-haiku-4.5", "anthropic/claude-sonnet-4.6"],
  ];
  return new Table({
    width: { size: 9900, type: WidthType.DXA },
    columnWidths: widths,
    rows: [header, ...rows.map((r) => new TableRow({
      children: [
        cell(r[0], { width: widths[0] }),
        cell(r[1], { width: widths[1], mono: true }),
        cell(r[2], { width: widths[2], mono: true }),
      ],
    }))],
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 360, hanging: 260 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 260 } } } },
        ],
      },
    ],
  },
  sections: [
    {
      properties: { page: { size: US_LETTER, margin: { top: 1080, bottom: 1080, left: 1260, right: 1260 } } },
      children: [
        new Paragraph({
          children: [new TextRun({ text: "Reference Check Analyzer", bold: true, size: 56, color: NAVY })],
          spacing: { after: 80 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "Technical Architecture", size: 32, color: ACCENT })],
          spacing: { after: 40 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "LangGraph-based pipeline, provider-agnostic LLM layer, real-time + batch execution, HTTP API.", italics: true, size: 22, color: GREY })],
          spacing: { after: 400 },
        }),
        hr(),

        h1("1. Overview"),
        body("The system is a LangGraph pipeline that automates comparing a candidate's claimed employment history against what their references actually say. It supports two reference input shapes (REF1: open-text transcript/email, REF2: structured yes/no verification form), runs in real time (single reference, or fan-out across a candidate's full reference list) or in bulk via a Batch API, and is exposed both as an importable Python package and as an HTTP service with a Streamlit front end."),
        body("Design principles that recur throughout the codebase:"),
        bullet("Deterministic comparison logic (diffing claimed vs. stated facts, scoring, routing) is plain Python, never left to an LLM to \u201cjudge\u201d freely -- LLM calls are used only where free-text understanding is genuinely required (extraction, sentiment, summarization)."),
        bullet("Exactly one implementation of every piece of business logic. The batch pipeline and the HTTP API both call the same node classes as the interactive CLI demos -- nothing is reimplemented per execution path."),
        bullet("Provider selection (which LLM backend) is a runtime configuration choice, never a code change."),

        h1("2. System Architecture"),
        image(`${DIAG}/architecture.png`, 580, 0.62),
        caption("Figure 1. Component overview -- clients, API layer, core pipeline, and the provider abstraction."),
        body("Three ways into the pipeline (Streamlit UI and any external HTTP caller both go through the FastAPI service; CLI scripts call the graphs directly), one shared core (graphs -> nodes -> provider abstraction), and three interchangeable LLM backends behind a common interface."),

        h1("3. Package Layout"),
        code("refcheck/"),
        code("  config.py            model-tier resolution (provider,tier)->model_id, every tunable setting"),
        code("  prompts.py            every LLM system prompt"),
        code("  request_builders.py   every (system, user_message) pair -- shared by real-time + batch"),
        code("  schemas.py             Pydantic models, incl. REF1/REF2 type codes"),
        code("  validation.py          input checks + prompt-injection pattern warnings"),
        code("  logging_config.py      structured JSON logging + PII scrubbing"),
        code(""),
        code("  llm/"),
        code("    base.py               BaseLLMProvider abstract class (shared retry/logging/output logic)"),
        code("    anthropic_provider.py / bedrock_provider.py / openrouter_provider.py"),
        code("    providers.py           get_provider() factory, selected via LLM_PROVIDER env var"),
        code("    batch/"),
        code("      anthropic_batch.py    Anthropic Message Batches API backend"),
        code("      bedrock_batch.py      AWS Bedrock batch inference backend (S3-based)"),
        code(""),
        code("  nodes/"),
        code("    reference_nodes.py    ReferenceCheckNodes -- REF1 + REF2 flow methods"),
        code("    candidate_nodes.py     CandidateNodes -- dispatch, cross-check, aggregate"),
        code(""),
        code("  graphs/                 reference_graph.py, candidate_graph.py (LangGraph StateGraphs)"),
        code("  pipelines/              batch_runner.py (bulk/offline, either batch backend)"),
        code("  data/                   sample_data.py, sample_data_multi.py"),
        code("  api/                    store.py, schemas.py, runner.py, main.py (FastAPI)"),
        code(""),
        code("run_demo.py / run_demo_multi.py / run_batch_demo.py   CLI entry points"),
        code("streamlit_app.py                                       web UI"),
        code("tests/                                                 unit tests, no API key needed"),

        h1("4. Reference Type Routing: REF1 / REF2"),
        body("A reference's `type` field (REF_TYPE_OPEN_TEXT = \"REF1\", REF_TYPE_YES_NO = \"REF2\" in schemas.py) determines which of two compiled StateGraphs processes it. Both graphs are built from one shared ReferenceCheckNodes instance and converge on the same scoring, routing, and summary methods -- there is exactly one confidence-scoring implementation regardless of which reference type produced the input."),
        image(`${DIAG}/reference_graphs.png`, 580, 0.86),
        caption("Figure 2. REF1 (open-text) and REF2 (yes/no form) single-reference graphs."),
        h2("REF1 -- open text"),
        bullet("extract_facts (LLM, extraction tier) and sentiment_and_redflags (LLM, extraction tier) run in parallel."),
        bullet("diff_facts (pure Python) compares extracted facts against the candidate's claims -- never an LLM freely judging similarity."),
        bullet("explain_discrepancies (LLM, reasoning tier) only runs if diff_facts actually found something -- a conditional edge skips the call entirely on a clean match."),
        h2("REF2 -- yes/no form"),
        bullet("No extraction step -- the form's answers ARE the facts. evaluate_yes_no_form (pure Python) builds discrepancies and red flags directly from the confirmed_title / confirmed_dates / confirmed_company / would_rehire / performance_concerns answers."),
        bullet("sentiment_from_comments (LLM, extraction tier) only runs if the form has free-text comments, reusing the identical prompt REF1 uses for sentiment analysis."),
        body("Routing itself happens in exactly two places: graphs/candidate_graph.py:fan_out_references (builds the right payload per reference) and nodes/candidate_nodes.py:CandidateNodes.run_reference (invokes the matching compiled subgraph)."),

        h1("5. Candidate-Level Orchestration"),
        body("A candidate can have any number of references, of either type or a mix. LangGraph's Send API fans out to one run_reference invocation per reference in parallel (capped by MAX_CONCURRENT_REFERENCES), then aggregates."),
        image(`${DIAG}/candidate_graph.png`, 460, 1.33),
        caption("Figure 3. Fan-out across references, then cross-reference consistency check and overall scoring."),
        body("cross_check_references is the signal that per-reference scoring alone can't catch: it flags references disagreeing with EACH OTHER (e.g. conflicting performance ratings, mismatched company/title between two references), separately from any single reference's discrepancy against the candidate's own claims. score_overall averages per-reference confidence and applies an additional penalty for any such cross-reference disagreement."),

        h1("6. Provider Abstraction and Model Tiering"),
        body("llm/base.py:BaseLLMProvider implements retry/backoff (tenacity, exponential backoff on rate limits/timeouts/5xx), timeout handling, forced structured output via tool-calling, Pydantic schema validation of the result, and structured logging -- once. Each concrete provider (AnthropicProvider, BedrockProvider, OpenRouterProvider) implements exactly three methods: _execute (the API call), _extract_tool_input (pulling the result out of that provider's response shape), and _is_retryable_exception."),
        body("Model selection never hardcodes a model string. config.get_model(provider, tier) is the single resolution point, with an env var override (MODEL_<PROVIDER>_<TIER>) checked first:"),
        tierTable(),
        new Paragraph({ text: "", spacing: { after: 160 } }),
        body("Switching the real-time provider is the LLM_PROVIDER environment variable; no code changes downstream of llm/providers.py:get_provider()."),

        h1("7. Batch Processing"),
        body("pipelines/batch_runner.py runs the same business logic as the real-time graphs, restructured into 8 phases so every LLM call of the same kind -- across every candidate and reference in the run -- is submitted as one batch job instead of one call per reference. Deterministic phases (diff_facts, evaluate_yes_no_form, score_confidence, cross_check_references, score_overall, and all routing) call ReferenceCheckNodes(llm_provider=None) / CandidateNodes(llm_provider=None) directly -- the exact same methods the real-time graphs use, with no separate implementation."),
        body("Two selectable batch backends, chosen per run via a batch_provider argument (also config.get_model(batch_provider, tier) for tiering, same mechanism as real-time):"),
        bullet("Anthropic (llm/batch/anthropic_batch.py) -- inline request list, submit/poll/retrieve against the Message Batches API."),
        bullet("Bedrock (llm/batch/bedrock_batch.py) -- structurally different: S3-based. Uploads a JSONL request file, calls CreateModelInvocationJob, polls the job resource, reads result JSONL back from S3. A Bedrock batch job runs against exactly one model, so this module transparently groups mixed-tier requests into one job per distinct model, hidden behind the same run_batch_sync() interface the Anthropic backend exposes."),
        body("Use case split: real-time graphs for anything a person is waiting on; batch for bulk/offline runs (e.g. an overnight queue) where the Batch API's own SLA (typically well under an hour, no hard guarantee) is acceptable, in exchange for roughly 50% lower cost."),

        h1("8. HTTP API"),
        body("refcheck/api/main.py exposes the real-time candidate graph over HTTP. Submission is asynchronous: the endpoint queues the work as a FastAPI BackgroundTask and returns a check_id immediately, since a check can involve several parallel LLM calls and take seconds to tens of seconds."),
        apiTable(),
        new Paragraph({ text: "", spacing: { after: 160 } }),
        body("Two ways to retrieve a result once submitted, usable independently or together:"),
        bullet("Pull -- poll GET /api/v1/checks/{check_id} until status is completed or failed."),
        bullet("Push -- supply callback_url in the submit request; the full result is POSTed there as JSON when the check finishes (best-effort, logged on failure, not retried)."),
        body("The job store (refcheck/api/store.py) is an in-memory dict behind a thread lock -- explicitly a demo-grade choice, documented as not durable across restarts and not shared across multiple worker processes. Its interface (create / get / mark_running / mark_completed / mark_failed) is small enough to back with Redis or a database without touching main.py or runner.py."),

        h1("9. Client: Streamlit UI"),
        body("streamlit_app.py builds a candidate + reference list interactively: a form for candidate/claimed details, then a per-reference form whose fields switch based on the REF1/REF2 radio selection (a text area for REF1, five yes/no dropdowns plus a comments box for REF2). On submit it POSTs to the API and polls (manual refresh button or an auto-refresh checkbox) until the result is ready, then renders per-reference discrepancies, red flags, and summaries, cross-reference flags, and the overall verdict."),

        h1("10. Deployment"),
        body("Dockerfile builds a single image capable of running any entry point (docker run <image> <script.py>); all three provider SDKs (anthropic, boto3, openai) are installed by default so switching LLM_PROVIDER never requires a rebuild. docker-compose.yml defines services for the API, the Streamlit UI (wired to the API automatically via API_BASE_URL), each CLI demo, both batch backends, and the test suite."),
        body("Every tunable setting -- provider selection, model IDs per tier, retry/timeout behavior, scoring thresholds and penalty weights, concurrency caps, input length limits, Bedrock batch S3/IAM configuration -- is an environment variable, documented in .env.example."),

        h1("11. Testing"),
        body("tests/ covers every pure-Python method/function directly -- diff_facts, evaluate_yes_no_form, score_confidence, cross_check_references, score_overall, all routing functions, config.get_model resolution, the provider factory, the batch custom_id convention, and the API's request validation/store wiring (with the actual LLM call monkeypatched out) -- all runnable via pytest tests/ -v with no API key or network access required."),

        h1("12. Production-Readiness Notes"),
        h2("Implemented"),
        bullet("Retry/backoff, timeouts, and structured JSON logging with PII scrubbing on every LLM call, across all three providers and both batch backends."),
        bullet("Input validation (length bounds) and non-blocking prompt-injection pattern detection before any text reaches an LLM call."),
        bullet("Concurrency caps on reference fan-out; per-reference failure isolation (one bad reference is flagged for manual review rather than failing the whole candidate's run, in both real-time and batch)."),
        bullet("Optional prompt caching (off by default -- current prompts are below the practical cacheable minimum size)."),
        h2("Left as extension points"),
        bullet("Secrets management -- credentials currently come from environment variables; a production deployment should use a secrets manager."),
        bullet("Job store durability and API authentication -- both called out explicitly above."),
        bullet("True human-in-the-loop persistence -- a flagged case produces a summary today but does not pause the graph for a checkpointed reviewer decision; wiring a LangGraph checkpointer + interrupt() is the natural next step."),
        bullet("Distributed tracing / per-candidate cost tracking beyond the existing structured logs."),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT);
});
