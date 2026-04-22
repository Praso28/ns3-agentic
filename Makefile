SHELL := /bin/bash

PYTHON ?= .venv/bin/python
UVICORN ?= .venv/bin/uvicorn
HOST ?= 0.0.0.0
PORT ?= 8080

DURATION ?= 120
REALTIME ?= 1
CONTROL_CHANNEL ?= /tmp/ai5g-control.jsonl
OLLAMA_MODEL ?= qwen2.5:1.5b
SEED ?= 7

NS3_CMD = ./ns3 run scratch/ai5g-metrics -- --metricsToStdout=1 --durationSeconds=$(DURATION) --enableDefaultFaults=0 --clearControlAtStart=1 --controlChannel=$(CONTROL_CHANNEL) --realTime=$(REALTIME) --seed=$(SEED)

.PHONY: help install dashboard sync-ns3-app run-sim run-real run-real-quick run-real-faulttest evaluate-real run-real-ollama mentor-demo test

help:
	@echo "Available commands:"
	@echo "  make install           # install Python deps in current venv"
	@echo "  make test              # run the automated test suite"
	@echo "  make dashboard         # start live dashboard on $(HOST):$(PORT)"
	@echo "  make sync-ns3-app      # copy tracked ns-3 scratch source into tools workspace"
	@echo "  make run-sim           # run simulation engine (TEST MODE)"
	@echo "  make run-real          # run real ns-3 path (default 120s, no built-in faults)"
	@echo "  make run-real-quick    # run real ns-3 path (30s quick check)"
	@echo "  make run-real-faulttest # run real ns-3 with built-in faults enabled"
	@echo "  make evaluate-real     # run repeated real fault tests and write summary report"
	@echo "  make run-real-ollama   # run real ns-3 with Ollama enabled"
	@echo "  make mentor-demo       # dashboard-friendly real demo with Ollama"
	@echo ""
	@echo "Optional overrides:"
	@echo "  make run-real DURATION=60"
	@echo "  make run-real DURATION=120 REALTIME=0 SEED=11"
	@echo "  make run-real-ollama OLLAMA_MODEL=qwen2.5:1.5b"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest tests/ -v

dashboard:
	$(UVICORN) src.dashboard.server:app --reload --host $(HOST) --port $(PORT)

sync-ns3-app:
	bash scripts/sync_ns3_app.sh

run-sim:
	$(PYTHON) run.py --engine simulation --scenario scenarios/f2_congestion.json

run-real: sync-ns3-app
	$(PYTHON) run.py --engine real --scenario scenarios/ns3_real_template.json --ns3-command "$(NS3_CMD)"

run-real-quick:
	$(MAKE) run-real DURATION=30

run-real-faulttest: sync-ns3-app
	OLLAMA_ENABLED=0 $(PYTHON) run.py --engine real --scenario scenarios/ns3_real_template.json --ns3-command "./ns3 run scratch/ai5g-metrics -- --metricsToStdout=1 --durationSeconds=$(DURATION) --enableDefaultFaults=1 --clearControlAtStart=1 --controlChannel=$(CONTROL_CHANNEL) --realTime=$(REALTIME) --seed=$(SEED)"

evaluate-real: sync-ns3-app
	OLLAMA_ENABLED=0 $(PYTHON) scripts/evaluate_real_runs.py --runs 5 --duration $(DURATION) --realtime $(REALTIME) --seed-start $(SEED)

run-real-ollama: sync-ns3-app
	OLLAMA_ENABLED=1 OLLAMA_MODEL=$(OLLAMA_MODEL) $(PYTHON) run.py --engine real --scenario scenarios/ns3_real_template.json --ns3-command "$(NS3_CMD)"

mentor-demo:
	OLLAMA_ENABLED=1 OLLAMA_MODEL=$(OLLAMA_MODEL) $(MAKE) run-real DURATION=120 REALTIME=1
