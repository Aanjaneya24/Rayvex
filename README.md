# Rayvex- AI Revenue Recovery Infrastructure

Razorpay AI Buildathon 2026 — Track 3.

Rayvex is a recovery-intelligence system for failed and abandoned
payments: it decides which recovery action is worth taking, executes it
only within strict policy limits, verifies the actual payment outcome
independently, and measures how much more revenue it recovers than
blindly retrying everything. The agent proposes; a deterministic policy
engine decides; a payment's own verified state — never the fact that an
action was merely taken — is the only source of "recovered."

**Status: end-to-end recovery loop, webhook ingestion (RabbitMQ +
worker), policy engine, payment verification, audit trail, a
Rayvex-vs-Naive-Retry benchmark, recovery intelligence (including a
LightGBM model and merchant-specific learning), A/B experimentation,
human-in-the-loop escalation review, a chaos test suite, agent
observability, dashboard auth/PII masking/rate limiting, a recovery
strategy simulator, case-detail UI, and a reproducible one-command demo
are all built and tested against real Postgres + Redis + RabbitMQ.**
Two smaller scope items — historical case-similarity search and an
additional recovery channel (e.g. SMS/voice) — were deliberately not
built: the feature space available doesn't support a similarity search
that would out-perform the segment-bucket estimator already in place,
and there's no real channel credential configured anywhere in this
environment to build a non-fake integration against.

## Demo

**[5-minute walkthrough video](https://drive.google.com/file/d/1ceEutOOI_V4uTreEdMaVPHYQlR0igHHl/view?usp=drive_link)**

Screenshots below are from a live run against the seeded demo data
(`scripts/seed_demo.py --benchmark-n 500`), not mockups — the numbers,
case IDs, and statuses are whatever that seed run actually produced.

### Command Center

![Command Center](docs/screenshots/command-center.png)

The landing page. Every number is queried live from Postgres on page
load — revenue at risk, verified recovered revenue, today's recovery
rate. The recovery funnel underneath shows how many of the current
cases made it through each pipeline stage (diagnosed → eligible →
action taken → verified recovered), and the comparison chart is the
most recent Rayvex-vs-naive-retry benchmark run, not a static graphic.

### Cases

![Cases list](docs/screenshots/cases.png)

Every seeded case, real filters (status, failure type, amount range,
created-date range), and a real database search — no client-side
filtering over a fixed list. Status badges are honest about outcome:
`recovered`, `stopped`, `verification pending`, `escalated`, each
reflecting the case's actual `current_state` in the database.

### Escalations

![Escalation queue](docs/screenshots/escalations.png)

Cases land here only when the system genuinely can't resolve them on
its own — in this run, a payment whose captured amount didn't match
what was expected, which verification refuses to auto-confirm and
escalates for a human instead of silently marking it recovered.

![Escalation review panel](docs/screenshots/escalation-review.png)

Clicking a queued case opens its full context — the agent's original
proposal, confidence and risk level, failure code, amount — next to
the reviewer's decision panel. A reason is required and audited for
every Approve, Override, or Reject; a viewer-role account never sees
these three buttons at all (nor can it call the endpoint directly —
the API itself enforces this with a 403).

### Control Center

![Control Center](docs/screenshots/control-center.png)

Every threshold the policy engine actually enforces — retry limits,
amount thresholds, rate limits, communication hours, risk score — is
editable here by a reviewer, with a live "Preview effect" simulation
before saving so a policy change is never a blind guess. Saving is
reviewer-only; a viewer sees exactly why the control is disabled
instead of a button that silently does nothing.

## Quickest path to seeing it work

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # adjust ports if 5432/6379/5672 are already taken locally

docker compose up -d postgres redis rabbitmq
python scripts/seed_demo.py --benchmark-n 500
```

That resets the database to a clean, migration-defined state and runs 11
demo scenarios (UPI timeout retry, insufficient-funds alternative payment,
checkout abandonment recovery, a repeated-failure policy stop, a
suspicious-velocity policy stop flagged for escalation, duplicate-webhook
idempotency, a failed→captured reconciliation, a prompt-injection attempt
safely ignored, a verification that correctly stays pending, a captured
amount that doesn't match the expected payment and escalates for human
review, and a batch Rayvex-vs-Naive-Retry benchmark run) — plus the
benchmark itself, printing each case's real outcome as it happens. The
amount-mismatch scenario is what populates the Escalations queue in the
dashboard; every other STOPPED/pending scenario is visible on the Cases
list but doesn't queue for human review. `seed_demo.py` drives
cases through the pipeline directly, the same call the worker below
makes per queue message — it doesn't need the worker running.

Then, to browse it (and to have real, live-received webhooks actually get
processed):

```bash
uvicorn apps.api.main:app --reload

python -m apps.worker.consumer

cd apps/web && npm install && npm run dev
```

Open `http://localhost:3000` — sign in with the demo credentials from
`.env.example`'s `DASHBOARD_CREDENTIALS` (`demo_viewer`/`demo_viewer_pw` to
browse, `demo_reviewer`/`demo_reviewer_pw` to also act on the escalation
queue). Command center, case list, case detail, escalations, evaluation,
and control-center screens, every number fetched from the API you just
seeded.

## Running the tests

The tests run against `rayvex_test` (a separate database from `rayvex`,
created automatically by `scripts/init-db.sql` on the container's first
boot) — migrate it explicitly once, since `seed_demo.py` above only
migrates `rayvex` (`DATABASE_URL`), never `rayvex_test`:

```bash
DATABASE_URL=postgresql+psycopg://rayvex:rayvex@localhost:55432/rayvex_test alembic upgrade head

pytest          # 336 tests, all against real Postgres + Redis + RabbitMQ, no mocks
```

Skipping this step fails every DB-touching test with `relation "cases"
does not exist` — a real, easy-to-hit trap on a genuinely fresh
`docker compose down -v` + `up`, not merely theoretical.

For a fast sanity check instead of the full suite (~3 minutes):

```bash
pytest tests/unit -q   # 120 tests, DB-free, ~3 seconds
```

The full suite is safe to run even while `apps/worker/consumer.py` is
running against the real dev broker — tests publish/consume on a
`case_processing_test` queue (`tests/conftest.py`), completely separate
from the `case_processing` queue a live worker process consumes, so the
two can never race each other.

## What's built

- **`models/` + `migrations/`** — the full schema (12 tables), Alembic-managed,
  no hand-edited state ever.
- **`services/recovery/`** — the state machine, the policy gate, the
  probability estimator + expected-value calculator, `action_executor.py`
  (a formal `ActionExecutor` Protocol — the one implementation is
  simulated, disclosed as such, but the swap point for a real one is
  real code, not a comment), and `case_orchestrator.py` wiring screening
  through decision, the agent, the gate, and verification into one
  pipeline.
- **`services/accounts/`** — real per-user accounts (bcrypt-hashed
  passwords in Postgres, not a shared env-var credential list).
  Self-registration always creates a viewer; the reviewer role — which
  can approve/reject/override escalations — is granted only by an
  existing reviewer, never at signup.
- **`services/policy/`** — the pure policy engine, versioned merchant
  config, real Redis-backed cooldown/velocity/daily-attempt guards.
- **`services/agent/`** — the LangChain tool-calling orchestrator, a
  strict schema that rejects malformed/unsupported output before it
  reaches anything, and a structural guarantee (tested, not just
  asserted) that the agent can never touch case state directly.
- **`services/payments/`** — `PaymentProvider` (Razorpay Test Mode +
  Simulation, both structurally labeled via a required `mode` field),
  and `verification.py` — the only code path allowed to declare a case
  `RECOVERED`, and only from an independently confirmed payment status.
- **`services/evaluation/`** — the reproducible synthetic dataset and the
  Rayvex-vs-Naive-Retry benchmark engine, both strategies run against
  the same case population, real policy/probability/expected-value
  services underneath, not a separate "benchmark version" of the logic.
- **`services/ingestion/`** — webhook signature verification, idempotency,
  out-of-order-safe case matching, and `queue.py` publishing each processed
  event to RabbitMQ for `apps/worker/` to pick up.
- **`apps/worker/`** — the RabbitMQ consumer that turns a published
  case-processing message into a real pipeline run or reconciliation,
  with a dead-letter queue for anything that fails rather than a
  silently dropped message.
- **`apps/api/`** — FastAPI routers (webhooks, cases, evaluation, policy,
  metrics), thin — every route delegates to a service above.
- **`apps/web/`** — Next.js, with `TiltCard` / `useCountUp` reference
  implementations and Recharts for the funnel and the
  Rayvex-vs-Naive-Retry comparison panel, every displayed number fetched
  from the API.
- **`scripts/seed_demo.py`** — the one-command reproducible demo.
- **`apps/api/routers/auth.py`** — `/auth/register`, `/auth/me`,
  `/auth/promote`; the frontend login screen has a real "Create an
  account" flow, and Control Center has a reviewer-only "promote a user"
  panel.
- **`tests/`** — 336 tests: `unit/` (DB-free where the code allows it),
  `integration/` (real Postgres + Redis + RabbitMQ, including a "try to
  break it" suite for payment verification and a structural scan proving
  only one module in the codebase can ever write `RECOVERED`), `agent/`
  (schema rejection, the agent-never-executes proof, prompt injection
  blocked by policy regardless of what the model decides), `chaos/`
  (failure-injection scenarios).

## Architecture at a glance

```
LLM            → judgment (proposes an action, nothing more)
Policy Engine  → guarantees (the only authority that can approve execution)
Payment Provider → execution/read (Razorpay Test Mode or a labeled simulation)
Payment Verification → truth (the only place "RECOVERED" is ever written)
PostgreSQL     → source of record
RabbitMQ       → decouples webhook ingestion from case processing
Redis          → temporary state — cooldowns, rate limits, dedup
```

The authority boundary, concretely: the agent's proposal tools take no
database or Redis handle at all — there is no code path through which
the LLM can write case state, only `services/recovery/action_gate.py`
can transition a case out of `ACTION_PENDING`, and only
`services/payments/verification.py` can ever write `RECOVERED`, and only
after an independently confirmed payment status from the provider.

## Notes on local setup

- Postgres is mapped to host port **55432**, Redis to **63790**, and
  RabbitMQ to **56720** (AMQP) / **15680** (management UI), not the
  defaults — this machine already had local instances bound to the
  standard ports. Adjust `.env` if yours doesn't.
- No `GROQ_API_KEY`/`OPENAI_API_KEY`/`RAZORPAY_KEY_ID`+`SECRET` are
  configured in this environment — `scripts/seed_demo.py` uses scripted
  (schema-validated, clearly labeled) decisions and `SimulationProvider`
  instead. Set real keys in `.env` and pass `--live` to use a real LLM;
  set Razorpay Test Mode credentials to use `RazorpayProvider` instead of
  the simulation.
- Tests run against real Postgres/Redis/RabbitMQ, never SQLite or mocks —
  the schema uses native enums, JSONB, and row locking that only a real
  Postgres exercises faithfully.

## Running in production

Three deployable units, each with a pinned-dependency image:

```bash
docker build -f Dockerfile.api -t rayvex-api .        # FastAPI, migrates + serves on :8000
docker build -f Dockerfile.worker -t rayvex-worker .   # RabbitMQ consumer
docker build -f apps/web/Dockerfile -t rayvex-web .    # Next.js, serves on :3000
```

Required environment for the API/worker images: `DATABASE_URL`,
`REDIS_URL`, `RABBITMQ_URL`, `RAZORPAY_WEBHOOK_SECRET`, `CORS_ORIGINS`
(comma-separated real frontend origin(s)), and Razorpay/LLM credentials
if not running in simulation mode. Set `DASHBOARD_CREDENTIALS` once to
create the first reviewer account, then unset it — accounts persist in
the `users` table after that. For the web image, set
`NEXT_PUBLIC_API_BASE_URL` to the API's real origin at build time.

The API image runs `alembic upgrade head` before serving, so schema
migrations apply automatically on deploy.
