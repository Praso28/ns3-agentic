import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request

from src.utils.config import OLLAMA_ENABLED, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_FALLBACK = (
	"You are an explanation-only assistant for a 5G autonomous network management system. "
	"Never change or override system control decisions. "
	"Return only the JSON object requested — no markdown fences, no preamble."
)


class Explainer:
	"""LLM-powered narrative generator for fault incidents and run summaries.

	The LLM is STRICTLY explanation-only.  All control decisions are made by
	the deterministic agent pipeline; this class only produces human-readable
	text for dashboards and reports.

	When Ollama is unavailable or times out, deterministic fallback text is
	returned so the pipeline never blocks on LLM availability.
	"""

	def __init__(self, prompt_path: str = "src/llm/prompt.txt") -> None:
		self.prompt_path = prompt_path
		self.ollama_enabled = OLLAMA_ENABLED
		self.ollama_host = OLLAMA_HOST.rstrip("/")
		self.ollama_model = OLLAMA_MODEL
		self.ollama_timeout_seconds = OLLAMA_TIMEOUT_SECONDS
		if self.ollama_enabled:
			logger.info("explainer: Ollama enabled model=%s host=%s", self.ollama_model, self.ollama_host)
		else:
			logger.info("explainer: Ollama disabled — deterministic fallback active")

	def _base_prompt(self) -> str:
		try:
			text = Path(self.prompt_path).read_text(encoding="utf-8").strip()
			if text:
				return text
		except OSError:
			pass
		return _SYSTEM_PROMPT_FALLBACK

	def _call_ollama(self, prompt: str) -> Optional[str]:
		"""Try /api/chat first, fall back to /api/generate.  Return None on any failure."""
		if not self.ollama_enabled:
			return None

		# --- /api/chat --------------------------------------------------------
		chat_url = f"{self.ollama_host}/api/chat"
		chat_payload = {
			"model": self.ollama_model,
			"messages": [{"role": "user", "content": prompt}],
			"stream": False,
			"options": {"temperature": 0.2},
		}
		try:
			chat_req = request.Request(
				url=chat_url,
				data=json.dumps(chat_payload).encode("utf-8"),
				headers={"Content-Type": "application/json"},
				method="POST",
			)
			with request.urlopen(chat_req, timeout=self.ollama_timeout_seconds) as resp:
				body = resp.read().decode("utf-8")
			parsed = json.loads(body)
			message = parsed.get("message", {})
			text = message.get("content", "") if isinstance(message, dict) else ""
			if isinstance(text, str) and text.strip():
				logger.debug("explainer: ollama chat response received len=%d", len(text))
				return text.strip()
		except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
			logger.debug("explainer: ollama chat failed (%s); trying generate endpoint", exc)

		# --- /api/generate fallback -------------------------------------------
		generate_url = f"{self.ollama_host}/api/generate"
		generate_payload = {
			"model": self.ollama_model,
			"prompt": prompt,
			"stream": False,
			"options": {"temperature": 0.2},
		}
		try:
			gen_req = request.Request(
				url=generate_url,
				data=json.dumps(generate_payload).encode("utf-8"),
				headers={"Content-Type": "application/json"},
				method="POST",
			)
			with request.urlopen(gen_req, timeout=self.ollama_timeout_seconds) as resp:
				body = resp.read().decode("utf-8")
			parsed = json.loads(body)
			text = parsed.get("response", "")
			if isinstance(text, str) and text.strip():
				logger.debug("explainer: ollama generate response received len=%d", len(text))
				return text.strip()
		except (error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
			logger.warning("explainer: ollama generate also failed (%s); using fallback", exc)

		return None

	@staticmethod
	def _try_parse_json_object(raw: str) -> Optional[Dict[str, Any]]:
		"""Extract and parse the first JSON object in *raw*, tolerating markdown fences."""
		text = raw.strip()
		# Strip common markdown code fences the model might emit.
		for fence in ("```json", "```"):
			if text.startswith(fence):
				text = text[len(fence):]
			if text.endswith("```"):
				text = text[:-3]
		text = text.strip()
		if not text:
			return None
		try:
			obj = json.loads(text)
			return obj if isinstance(obj, dict) else None
		except json.JSONDecodeError:
			start = text.find("{")
			end = text.rfind("}")
			if start == -1 or end == -1 or end <= start:
				return None
			try:
				obj = json.loads(text[start: end + 1])
				return obj if isinstance(obj, dict) else None
			except json.JSONDecodeError:
				return None

	@staticmethod
	def _validate_incident_obj(obj: Dict[str, Any]) -> bool:
		"""Return True if obj has all required string keys with meaningful content."""
		required = ["explanation", "reasoning", "recommendation"]
		if not all(isinstance(obj.get(k), str) for k in required):
			return False
		return len(obj["recommendation"].strip()) >= 12

	def explain(self, fault: str, metrics: Dict, confidence: float) -> Dict:
		"""Generate a short explanation for a detected fault condition."""
		recommendation = "Monitor closely"
		if fault == "F1":
			recommendation = "Node restart is recommended to restore connectivity."
		elif fault == "F2":
			recommendation = "Reduce traffic load to relieve congestion."
		elif fault == "F3":
			recommendation = "Network quality issue detected; observe trend for escalation."

		latency = float(metrics.get("latency_ms", 0.0))
		throughput = float(metrics.get("throughput_mbps", 0.0))
		loss = float(metrics.get("packet_loss", 0.0))

		explanation = (
			f"Fault {fault} detected with confidence {confidence:.3f}. "
			f"Latency={latency:.2f}ms, throughput={throughput:.2f}Mbps, loss={loss:.4f}."
		)
		fallback: Dict[str, Any] = {
			"explanation": explanation,
			"reasoning": "Explanation generated from metrics and fault classification.",
			"recommendation": recommendation,
		}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return a JSON object with exactly these keys: explanation, reasoning, recommendation. "
			"No markdown. No extra keys.\n"
			f"fault={fault}, confidence={confidence:.3f}, metrics={json.dumps(metrics)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback
		obj = self._try_parse_json_object(llm_text)
		if obj and self._validate_incident_obj(obj):
			return {"explanation": obj["explanation"], "reasoning": obj["reasoning"], "recommendation": obj["recommendation"]}
		return fallback

	def explain_incident(
		self,
		fault: str,
		metrics: Dict,
		confidence: float,
		action: str,
		verification_state: str,
	) -> Dict:
		"""Generate a structured explanation for a completed incident lifecycle."""
		latency = float(metrics.get("latency_ms", 0.0))
		throughput = float(metrics.get("throughput_mbps", 0.0))
		loss = float(metrics.get("packet_loss", 0.0))

		explanation = (
			f"Action '{action}' executed for {fault} fault "
			f"(latency={latency:.1f}ms, throughput={throughput:.1f}Mbps, loss={loss:.3f}, "
			f"confidence={confidence:.3f}). Outcome: {verification_state}."
		)
		recommendation = (
			"Fault resolved; system stabilized."
			if verification_state == "RESOLVED"
			else "Issue persists; escalation required."
		)
		fallback: Dict[str, Any] = {
			"explanation": explanation,
			"reasoning": "Operational incident summary derived from telemetry and verifier output.",
			"recommendation": recommendation,
		}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return a JSON object with exactly these keys: explanation, reasoning, recommendation. "
			"Use concise operational language. No markdown. No extra keys.\n"
			f"fault={fault}, action={action}, verification_state={verification_state}, "
			f"confidence={confidence:.3f}, metrics={json.dumps(metrics)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback
		obj = self._try_parse_json_object(llm_text)
		if obj and self._validate_incident_obj(obj):
			return {"explanation": obj["explanation"], "reasoning": obj["reasoning"], "recommendation": obj["recommendation"]}
		return fallback

	def explain_run_summary(self, incidents: list, summary: Dict) -> Dict:
		"""Generate a structured JSON run summary with LLM narrative enrichment.

		Always returns a dict with keys: title, overview, fault_timeline, final_note.
		Falls back gracefully when Ollama is unavailable or returns invalid JSON.
		"""
		timeline = [
			{
				"fault": inc.get("fault", "UNKNOWN"),
				"metric_timestamp": inc.get("metric_timestamp", -1),
				"action": inc.get("action", "no_action"),
				"state": inc.get("verification_state", "UNKNOWN"),
				"short": inc.get("llm_explanation", ""),
			}
			for inc in incidents
		]

		f1_count = sum(1 for inc in incidents if inc.get("fault") == "F1")
		f2_count = sum(1 for inc in incidents if inc.get("fault") == "F2")
		f3_count = sum(1 for inc in incidents if inc.get("fault") == "F3")
		resolved = int(summary.get("resolved", 0))
		escalated = int(summary.get("escalated", 0))
		total = int(summary.get("incidents", 0))

		if not incidents:
			fallback: Dict[str, Any] = {
				"title": "No Actionable Incidents Detected",
				"overview": "No F1/F2/F3 incident crossed the ACT confidence threshold in this run.",
				"fault_timeline": [],
				"final_note": "System remained stable under configured adaptive thresholds.",
			}
		else:
			overview = (
				f"Run processed {summary.get('records_processed', 0)} telemetry samples. "
				f"Detected {total} incident(s): F1={f1_count}, F2={f2_count}, F3={f3_count}. "
				f"Resolved={resolved}, Escalated={escalated}."
			)
			final_note = (
				"All observed faults were successfully remediated."
				if escalated == 0
				else f"{escalated} fault(s) remain unresolved and require escalation."
			)
			fallback = {
				"title": "Autonomous Agent Run Report",
				"overview": overview,
				"fault_timeline": timeline,
				"final_note": final_note,
			}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return a JSON object with exactly these keys: title, overview, fault_timeline, final_note. "
			"fault_timeline must be a list; each element has: fault, metric_timestamp, action, state, short. "
			"Do not invent incidents. Use only the provided timeline data. No markdown.\n"
			f"run_summary={json.dumps(summary)}\n"
			f"timeline={json.dumps(timeline)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback

		obj = self._try_parse_json_object(llm_text)
		if not obj:
			return fallback

		# Validate required string fields; fall back on any missing key.
		for key in ("title", "overview", "final_note"):
			if not isinstance(obj.get(key), str) or not obj[key].strip():
				logger.warning("explainer: run_summary LLM response missing key=%s — using fallback", key)
				return fallback

		# Ensure fault_timeline is a list; restore original if LLM dropped entries.
		if not isinstance(obj.get("fault_timeline"), list):
			obj["fault_timeline"] = timeline
		elif timeline and not obj["fault_timeline"]:
			obj["fault_timeline"] = timeline

		return obj
