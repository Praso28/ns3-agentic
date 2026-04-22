import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Thresholds:
	latency_ms_floor: float = 25.0
	latency_sigma_k: float = 2.5
	latency_jitter_k: float = 1.8
	latency_base_offset_ms: float = 6.0

	throughput_mbps_floor: float = 12.0
	throughput_drop_ratio: float = 0.72
	throughput_sigma_k: float = 2.0

	packet_loss_floor: float = 0.02
	packet_loss_sigma_k: float = 2.8

	jitter_floor: float = 4.0
	jitter_sigma_k: float = 2.5

	epsilon: float = 1e-6


@dataclass(frozen=True)
class ConfidenceCoefficients:
	a: float = 5.0
	b: float = -2.0
	act_threshold: float = 0.55


@dataclass(frozen=True)
class VerifyCriteria:
	# Weighted recovery score gates by fault type.
	resolve_score_f1: float = 0.50
	resolve_score_f2: float = 0.45
	resolve_score_f3: float = 0.40

	# Relative improvements expected from successful actions.
	latency_improve_ratio: float = 0.12
	throughput_improve_ratio: float = 0.06
	loss_improve_ratio: float = 0.12

	# Small tolerance so noise does not mark recoveries as escalations.
	latency_tolerance_ms: float = 4.0
	throughput_tolerance_mbps: float = 1.0
	loss_tolerance: float = 0.01


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
