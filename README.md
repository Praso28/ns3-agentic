# ai5g-ns3

Simulation-driven AI agent pipeline for 5G core fault detection and response.

## Core Principle

REAL METRICS -> REAL DETECTION -> REAL ACTION -> REAL VERIFICATION -> LLM EXPLANATION

## Repository Layout

- `src/simulation/`: scenario and fault-driven simulation stream.
- `src/collector/`: bridge/parser that normalizes raw simulation metrics.
- `src/agent/`: observer, diagnoser, confidence, planner, executor, verifier.
- `src/llm/`: explanation-only output layer.
- `src/utils/`: runtime config and report logging.
- `scenarios/`: fault scenarios (`f1`, `f2`, `f3`, `combo`).
- `reports/`: generated audit and final report artifacts.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py --engine simulation
```

Optional scenario stream run:

```bash
python src/simulation/scenario_runner.py --scenario scenarios/f2_congestion.json
```

## Real ns-3 Mode (Required Spec Path)

Deploy ns-3 first:

```bash
./scripts/deploy_ns3.sh
```

Run with real mode:

```bash
python run.py --engine real --scenario scenarios/ns3_real_template.json
```

Real mode contract:

- The ns-3 program must print one JSON metric record per line to stdout.
- Each record must include: `timestamp`, `latency`, `throughput`, `packet_loss`, `jitter`.
- Optional prefix `METRIC ` is supported (e.g., `METRIC { ... }`).
- To support control actions, ns-3 should watch the configured `control_channel` JSONL file.
	- `restart_node` and `reduce_load` actions are written there by the agent.

Scenario config keys for real mode:

- `ns3.command`: command to launch ns-3 process.
- `ns3.workdir`: ns-3 repository working directory.
- `ns3.control_channel`: path for action command JSONL.

## Pipeline

`run.py` executes:

1. simulation stream (real ns-3 process in `--engine real`)
2. collector normalization
3. observer anomaly detection
4. diagnoser fault mapping
5. confidence scoring
6. planner decision
7. executor control action
8. verifier post-action check
9. audit logging
10. LLM explanation (non-binding)

## Notes

- Decision logic is deterministic and rule-based.
- LLM layer does not modify decisions or trigger actions.
- Reports are written to `reports/audit.jsonl` and `reports/final_report.json`.
- `--engine real` is the production/spec path; `--engine simulation` is a local fallback.

## Ollama-Backed Final Report

The explainer now calls Ollama for incident text and the final run report when available.
If Ollama is offline/unreachable, the pipeline automatically falls back to deterministic local text.

Default endpoint/model:

- `OLLAMA_HOST=http://127.0.0.1:11434`
- `OLLAMA_MODEL=llama3.1:8b`

Run with explicit model selection:

```bash
OLLAMA_ENABLED=1 OLLAMA_MODEL=llama3.1:8b python run.py --engine real --scenario scenarios/ns3_real_template.json
```

Disable Ollama and force local fallback:

```bash
OLLAMA_ENABLED=0 python run.py --engine real --scenario scenarios/ns3_real_template.json
```

If you see Ollama error `model requires more system memory ... than is available`, select a smaller model:

```bash
ollama pull qwen2.5:1.5b
OLLAMA_MODEL=qwen2.5:1.5b python run.py --engine real --scenario scenarios/ns3_real_template.json
```

## Live Dashboard

Install/update Python dependencies:

```bash
pip install -r requirements.txt
```

Run dashboard server:

```bash
uvicorn src.dashboard.server:app --reload --host 0.0.0.0 --port 8080
```

If websocket live stream does not connect, install websocket runtime deps:

```bash
pip install websockets wsproto
```

Open:

```text
http://127.0.0.1:8080
```

The dashboard streams live updates from `reports/live_metrics.jsonl` and summary from `reports/final_report.json`.

Tip: if you run `./ns3 ...` and see exit code 127, run the command from `tools/ns-3-dev` or use absolute path `/home/pranay/ai5g/ns3-agentic/tools/ns-3-dev/ns3`.

## Short Commands (Mentor Demo Friendly)

Use the `Makefile` so you do not need long CLI flags every time:

```bash
make help
make dashboard
make run-real
make run-real-ollama
make mentor-demo
```

Useful overrides:

```bash
make run-real DURATION=60
make run-real-ollama OLLAMA_MODEL=qwen2.5:1.5b
```