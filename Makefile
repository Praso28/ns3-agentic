SHELL := /bin/bash

PYTHON ?= .venv/bin/python
UVICORN ?= .venv/bin/uvicorn
HOST ?= 0.0.0.0
PORT ?= 8080

DURATION ?= 120
REALTIME ?= 1
CONTROL_CHANNEL ?= /tmp/ai5g-control.jsonl
OLLAMA_MODEL ?= qwen2.5:1.5b

NS3_CMD = ./ns3 run scratch/ai5g-metrics -- --metricsToStdout=1 --durationSeconds=$(DURATION) --enableDefaultFaults=1 --clearControlAtStart=1 --controlChannel=$(CONTROL_CHANNEL) --realTime=$(REALTIME)

.PHONY: help install dashboard run-sim run-real run-real-quick run-real-ollama mentor-demo

help:
	@echo "Available commands:"
	@echo "  make install           # install Python deps in current venv"
	@echo "  make dashboard         # start live dashboard on $(HOST):$(PORT)"
	@echo "  make run-sim           # run simulation engine"
	@echo "  make run-real          # run real ns-3 path (default 120s)"
	@echo "  make run-real-quick    # run real ns-3 path (30s quick check)"
	@echo "  make run-real-ollama   # run real ns-3 with Ollama enabled"
	@echo "  make mentor-demo       # dashboard-friendly real demo with Ollama"
	@echo ""
	@echo "Optional overrides:"
	@echo "  make run-real DURATION=60"
	@echo "  make run-real-ollama OLLAMA_MODEL=qwen2.5:1.5b"

install:
	$(PYTHON) -m pip install -r requirements.txt

dashboard:
	$(UVICORN) src.dashboard.server:app --reload --host $(HOST) --port $(PORT)

run-sim:
	$(PYTHON) run.py --engine simulation --scenario scenarios/f2_congestion.json

run-real:
	$(PYTHON) run.py --engine real --scenario scenarios/ns3_real_template.json --ns3-command "$(NS3_CMD)"

run-real-quick:
	$(MAKE) run-real DURATION=30

run-real-ollama:
	OLLAMA_ENABLED=1 OLLAMA_MODEL=$(OLLAMA_MODEL) $(PYTHON) run.py --engine real --scenario scenarios/ns3_real_template.json --ns3-command "$(NS3_CMD)"

mentor-demo:
	OLLAMA_ENABLED=1 OLLAMA_MODEL=$(OLLAMA_MODEL) $(MAKE) run-real DURATION=120 REALTIME=1
