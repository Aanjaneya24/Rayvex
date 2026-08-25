# Rayvex — AI Revenue Recovery Infrastructure

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

## Quickest path to seeing it work

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # adjust ports if 5432/6379/5672 are already taken locally

docker compose up -d postgres redis rabbitmq
python scripts/seed_demo.py --benchmark-n 500
```

That resets the database to a clean, migration-defined state and runs 10
demo scenarios (UPI timeout retry, insufficient-funds alternative payment,
checkout abandonment recovery, a repeated-failure policy stop, a
suspicious-velocity escalation, duplicate-webhook idempotency, a
failed→captured reconciliation, a prompt-injection attempt safely
ignored, a verification that correctly stays pending, and a batch
Rayvex-vs-Naive-Retry benchmark run) — plus the benchmark itself,
printing each case's real outcome as it happens. `seed_demo.py` drives
cases through the pipeline directly, the same call the worker below
makes per queue message — it doesn't need the worker running.

Then, to browse it (and to have real, live-received webhooks actually get
processed):

```bash
# terminal 1
uvicorn apps.api.main:app --reload

# terminal 2 — consumes case_processing messages the webhook endpoint
# publishes; without this, a live webhook creates a case that never
# advances past RECEIVED
python -m apps.worker.consumer

# terminal 3
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

pytest          # 309 tests, all against real Postgres + Redis + RabbitMQ, no mocks
```

Skipping this step fails every DB-touching test with `relation "cases"
does not exist` — a real, easy-to-hit trap on a genuinely fresh
`docker compose down -v` + `up`, not merely theoretical.

## What's built

- **`models/` + `migrations/`** — the full schema (12 tables), Alembic-managed,
  no hand-edited state ever.
- **`services/recovery/`** — the state machine, the policy gate, the
  probability estimator + expected-value calculator, and
  `case_orchestrator.py` wiring screening through decision, the agent,
  the gate, and verification into one pipeline.
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
- **`tests/`** — 309 tests: `unit/` (DB-free where the code allows it),
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
