import json
from pathlib import Path
from typing import Any, Dict
from urllib import error, request

from src.utils.config import OLLAMA_ENABLED, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS


class Explainer:
	def __init__(self, prompt_path: str = "src/llm/prompt.txt") -> None:
		self.prompt_path = prompt_path
		self.ollama_enabled = OLLAMA_ENABLED
		self.ollama_host = OLLAMA_HOST.rstrip("/")
		self.ollama_model = OLLAMA_MODEL
		self.ollama_timeout_seconds = OLLAMA_TIMEOUT_SECONDS

	def _base_prompt(self) -> str:
		try:
			return Path(self.prompt_path).read_text(encoding="utf-8").strip()
		except OSError:
			return "You are an explanation-only assistant. Never change system actions."

	def _call_ollama(self, prompt: str) -> str | None:
		if not self.ollama_enabled:
			return None

		chat_url = f"{self.ollama_host}/api/chat"
		chat_payload = {
			"model": self.ollama_model,
			"messages": [{"role": "user", "content": prompt}],
			"stream": False,
			"options": {"temperature": 0.2},
		}
		chat_data = json.dumps(chat_payload).encode("utf-8")
		chat_req = request.Request(url=chat_url, data=chat_data, headers={"Content-Type": "application/json"}, method="POST")

		try:
			with request.urlopen(chat_req, timeout=self.ollama_timeout_seconds) as resp:
				body = resp.read().decode("utf-8")
			parsed = json.loads(body)
			message = parsed.get("message", {})
			text = message.get("content", "") if isinstance(message, dict) else ""
			if isinstance(text, str) and text.strip():
				return text.strip()
		except (error.URLError, TimeoutError, json.JSONDecodeError, OSError):
			pass

		generate_url = f"{self.ollama_host}/api/generate"
		generate_payload = {
			"model": self.ollama_model,
			"prompt": prompt,
			"stream": False,
			"options": {"temperature": 0.2},
		}
		generate_data = json.dumps(generate_payload).encode("utf-8")
		generate_req = request.Request(
			url=generate_url,
			data=generate_data,
			headers={"Content-Type": "application/json"},
			method="POST",
		)

		try:
			with request.urlopen(generate_req, timeout=self.ollama_timeout_seconds) as resp:
				body = resp.read().decode("utf-8")
			parsed = json.loads(body)
			text = parsed.get("response", "")
			return text.strip() if isinstance(text, str) else None
		except (error.URLError, TimeoutError, json.JSONDecodeError, OSError):
			return None

	@staticmethod
	def _try_parse_json_object(raw: str) -> Dict[str, Any] | None:
		text = raw.strip()
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
				obj = json.loads(text[start : end + 1])
				return obj if isinstance(obj, dict) else None
			except json.JSONDecodeError:
				return None

	def explain(self, fault: str, metrics: Dict, confidence: float) -> Dict:
		recommendation = "Monitor closely"
		if fault == "F1":
			recommendation = "Node restart is recommended"
		elif fault == "F2":
			recommendation = "Traffic load should be reduced"
		elif fault == "F3":
			recommendation = "Network quality issue detected; observe trend"

		explanation = (
			f"Fault={fault}, confidence={confidence:.3f}, "
			f"latency={metrics.get('latency_ms', 0):.2f}ms, "
			f"throughput={metrics.get('throughput_mbps', 0):.2f}Mbps, "
			f"loss={metrics.get('packet_loss', 0):.4f}."
		)

		reasoning = "Explanation-only layer generated from metrics and fault classification."
		fallback = {
			"explanation": explanation,
			"reasoning": reasoning,
			"recommendation": recommendation,
		}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return strict JSON with keys: explanation, reasoning, recommendation.\n"
			f"fault={fault}, confidence={confidence:.3f}, metrics={json.dumps(metrics)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback

		obj = self._try_parse_json_object(llm_text)
		if not obj:
			return fallback

		if all(isinstance(obj.get(key), str) for key in ["explanation", "reasoning", "recommendation"]):
			if len(obj["recommendation"].strip()) < 12:
				return fallback
			return {
				"explanation": obj["explanation"],
				"reasoning": obj["reasoning"],
				"recommendation": obj["recommendation"],
			}
		return fallback

	def explain_incident(
		self,
		fault: str,
		metrics: Dict,
		confidence: float,
		action: str,
		verification_state: str,
	) -> Dict:
		latency = float(metrics.get("latency_ms", 0.0))
		throughput = float(metrics.get("throughput_mbps", 0.0))
		loss = float(metrics.get("packet_loss", 0.0))

		explanation = (
			f"Action {action} triggered because {fault} was detected "
			f"(latency={latency:.1f}ms, throughput={throughput:.1f}Mbps, loss={loss:.3f}, conf={confidence:.3f}). "
			f"Status: {verification_state}."
		)

		if verification_state == "RESOLVED":
			recommendation = "Fault fixed and system stabilized."
		else:
			recommendation = "Issue persists; escalation path should continue."

		fallback = {
			"explanation": explanation,
			"reasoning": "Short operational incident summary.",
			"recommendation": recommendation,
		}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return strict JSON with keys: explanation, reasoning, recommendation. Keep concise ops language.\n"
			f"fault={fault}, action={action}, verification_state={verification_state}, "
			f"confidence={confidence:.3f}, metrics={json.dumps(metrics)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback

		obj = self._try_parse_json_object(llm_text)
		if not obj:
			return fallback

		if all(isinstance(obj.get(key), str) for key in ["explanation", "reasoning", "recommendation"]):
			if len(obj["recommendation"].strip()) < 12:
				return fallback
			return {
				"explanation": obj["explanation"],
				"reasoning": obj["reasoning"],
				"recommendation": obj["recommendation"],
			}
		return fallback

	def explain_run_summary(self, incidents: list[Dict], summary: Dict) -> Dict:
		if not incidents:
			fallback_no_incidents = {
				"title": "No actionable incidents detected",
				"overview": "No F1/F2/F3 incident crossed ACT criteria in this run.",
				"fault_timeline": [],
				"final_note": "System remained stable under configured thresholds.",
			}
			prompt = (
				f"{self._base_prompt()}\n\n"
				"Return strict JSON with keys: title, overview, fault_timeline (array), final_note.\n"
				f"run_summary={json.dumps(summary)} incidents=[]"
			)
			llm_text = self._call_ollama(prompt)
			if not llm_text:
				return fallback_no_incidents
			obj = self._try_parse_json_object(llm_text)
			if not obj:
				return fallback_no_incidents
			if isinstance(obj.get("title"), str) and isinstance(obj.get("overview"), str) and isinstance(obj.get("final_note"), str):
				if not isinstance(obj.get("fault_timeline"), list):
					obj["fault_timeline"] = []
				return obj
			return fallback_no_incidents

		timeline = []
		for incident in incidents:
			timeline.append(
				{
					"fault": incident.get("fault", "UNKNOWN"),
					"metric_timestamp": incident.get("metric_timestamp", -1),
					"action": incident.get("action", "no_action"),
					"state": incident.get("verification_state", "UNKNOWN"),
					"short": incident.get("llm_explanation", ""),
				}
			)

		f1_count = sum(1 for item in incidents if item.get("fault") == "F1")
		f2_count = sum(1 for item in incidents if item.get("fault") == "F2")
		resolved = int(summary.get("resolved", 0))
		escalated = int(summary.get("escalated", 0))

		overview = (
			f"Detected F1={f1_count}, F2={f2_count}; resolved={resolved}, escalated={escalated}. "
			"Each incident entry includes occurrence time and action outcome."
		)
		final_note = "Primary unresolved faults need escalation workflow." if escalated > 0 else "All observed faults were resolved."

		fallback = {
			"title": "Run Completion Report",
			"overview": overview,
			"fault_timeline": timeline,
			"final_note": final_note,
		}

		prompt = (
			f"{self._base_prompt()}\n\n"
			"Return strict JSON with keys: title, overview, fault_timeline, final_note.\n"
			"fault_timeline must be an array where each item has: fault, metric_timestamp, action, state, short.\n"
			"Do not invent new incidents; only use provided timeline entries.\n"
			f"run_summary={json.dumps(summary)}\n"
			f"timeline={json.dumps(timeline)}"
		)
		llm_text = self._call_ollama(prompt)
		if not llm_text:
			return fallback

		obj = self._try_parse_json_object(llm_text)
		if not obj:
			return fallback

		if not isinstance(obj.get("title"), str):
			return fallback
		if not isinstance(obj.get("overview"), str):
			return fallback
		if not isinstance(obj.get("final_note"), str):
			return fallback
		if not isinstance(obj.get("fault_timeline"), list):
			obj["fault_timeline"] = timeline
		elif len(obj["fault_timeline"]) == 0 and len(timeline) > 0:
			obj["fault_timeline"] = timeline

		return obj
