import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
	latency_ms_high: float = 80.0
	throughput_mbps_low: float = 35.0
	packet_loss_high: float = 0.08
	jitter_high: float = 12.0


@dataclass(frozen=True)
class ConfidenceCoefficients:
	a: float = 5.0
	b: float = -2.0
	act_threshold: float = 0.55


WINDOW_SECONDS = 30
VERIFY_WINDOW = 5
REPORTS_DIR = "reports"
AUDIT_LOG_PATH = "reports/audit.jsonl"
FINAL_REPORT_PATH = "reports/final_report.json"
LIVE_METRICS_PATH = "reports/live_metrics.jsonl"

MIN_PERSISTENCE_TO_ACT = 0.25
INCIDENT_MAX_RETRIES = 2
INCIDENT_COOLDOWN_SECONDS = 10

ENGINE_REAL = "real"
ENGINE_SIMULATION = "simulation"


OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "1") not in {"0", "false", "False", "FALSE"}
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "20"))
