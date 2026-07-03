# Agentic Manufacturing Integration

An LLM-agent-driven smart-manufacturing **monitoring & analysis pipeline**. A **Gemini**
agent orchestrates a simulated automation work cell (a Franka arm sorting colored cubes in
NVIDIA Isaac Sim) through **MCP**, logs every job to **PostgreSQL**, and surfaces quality
analytics in **Power BI** — plus a statistics-driven evaluation that selects the best model
checkpoint out of 20.

> Portfolio project aligned with a semiconductor **Automation Systems Integration Engineer (IMC)**
> role: SQL · Power BI · data analysis · system integration · MLOps · CI/CD over a reproducible pipeline.

## Highlights

- **Natural-language ops** — ask the agent *"現在成功率多少？成功的任務比失敗的快嗎？"* and it
  calls MCP tools, writes read-only SQL, queries Postgres, and answers in plain language.
- **Rigorous model selection** — swept **20 training checkpoints × 50 matched-seed rollouts**.
  Key finding: the *last* checkpoint (epoch 2000) scores only **30%**, but **epoch 200–300 hits 60%** —
  training longer overfit the demonstrations. Early stopping, quantified.
- **Root-cause analysis** — failures concentrate on the final (green) cube, a compounding-error
  signature confirmed across three complementary views.
- **Reproducible & tested** — two decoupled layers, unit tests, and a GitHub Actions CI
  (lint + Postgres-backed tests).

## Architecture (two decoupled layers)

```
 使用者(自然語言)
      │
      ▼
 Gemini Agent ──(MCP)──► MCP Server ──► tools ──► PostgreSQL ──► KPI/SPC ──► Power BI
      ▲                                   ▲                        (analysis)
      │  規則式排程(每小時一批)             │
 scheduler ─────────────────────────► run_job ◄── Isaac Sim 工作站 (BC-RNN policy, GPU)
```

- **sim layer** (`sim/`) — runs in the Isaac Sim env (GPU); wraps the trained BC-RNN policy into
  `run_job()` / `sweep_checkpoints.py`, emitting structured JSONL. Decoupled from the DB; not tested in CI.
- **orchestration / data layer** (`orchestration/`, `analysis/`) — MCP server, Gemini agent,
  rule-based scheduler, PostgreSQL, KPI/SPC analytics, Power BI export. Fully unit-tested & CI-covered.

## Tech stack

Python 3.11 · **MCP** · **Google Gemini** (function calling) · **PostgreSQL** (psycopg3) · pandas ·
APScheduler · Docker Compose · **Power BI** · **GitHub Actions** · NVIDIA Isaac Sim / Isaac Lab (upstream).

## The checkpoint experiment (statistics-driven)

The metric is a success rate — a **proportion** (Bernoulli), so `SE = √(p(1−p)/n)`:
n=10 → ±31% (misleading), n=50 → ±14%. A quick 10-shot sweep looked promising for several
checkpoints; **50 matched-seed rollouts overturned it**:

- **epoch 200 / 300 ≈ 60%** (best) → epoch 600 = 54% → … → **epoch 2000 = 30%** → epoch 100 = 3%.
- Early-vs-late gap is significant (200/300 vs 2000: z ≈ 3.2); the top finalists (200/300/600)
  are statistically tied at n=50 — honestly reported, not over-claimed.

Presented in Power BI as a **trend line** (success rate vs epoch) and a **ranked bar** (who's best).

## How the agent works

```
你 > 成功與失敗任務的平均 cycle time 各是多少？
助理 > 成功任務平均 1051 步、失敗任務 1800 步 — 成功的明顯較快。
```

The agent lists the MCP server's tools, converts them to Gemini function declarations, runs a
manual function-calling loop, and executes each tool via `session.call_tool()` — so it genuinely
goes *through* MCP (visible as `ListToolsRequest` / `CallToolRequest` in the server log).

## Layout

```
sim/            # run_job() + sweep_checkpoints.py: Isaac Sim work cell -> JSONL (env_isaacsim, GPU)
orchestration/  # mcp_server / agent / scheduler / tools / db / load_results (env_agent)
analysis/       # KPI, SPC/anomaly, Power BI export
sql/            # schema.sql (data contract)
contracts/      # job_result.schema.json (sim <-> data contract)
tests/          # pytest (DB-backed + pure-function; sim mocked out)
.github/        # CI workflow
```

## Quick start (orchestration / data layer — no GPU)

```bash
python3.11 -m venv ~/env_agent && source ~/env_agent/bin/activate
pip install -r requirements-agent.txt
docker compose up -d          # PostgreSQL + Adminer (http://localhost:8080)

# ask the agent (needs GEMINI_API_KEY in .env)
python -m orchestration.agent "目前成功率多少？哪個階段最常失敗？"
```

The Isaac Sim work-cell layer (`sim/`) runs separately in an Isaac Sim environment on a GPU host.

## Related

- **Simulated work cell**: [`isaac-lab-cube-sort`](https://github.com/vincenttseng26/isaac-lab-cube-sort)
  — the custom NVIDIA Isaac Lab cube-sorting task + trained BC-RNN-GMM policy that this pipeline
  drives, monitors, and evaluates.

## License

MIT (see [LICENSE](LICENSE)). Files under `sim/` are derived from NVIDIA Isaac Lab and retain their
upstream **BSD-3-Clause** headers.
