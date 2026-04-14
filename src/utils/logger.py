import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from src.utils.config import AUDIT_LOG_PATH, FINAL_REPORT_PATH, LIVE_METRICS_PATH, REPORTS_DIR


def utc_now_iso() -> str:
	return datetime.now(tz=timezone.utc).isoformat()


class AuditLogger:
	def __init__(
		self,
		audit_path: str = AUDIT_LOG_PATH,
		final_report_path: str = FINAL_REPORT_PATH,
		live_metrics_path: str = LIVE_METRICS_PATH,
	) -> None:
		self.audit_path = audit_path
		self.final_report_path = final_report_path
		self.live_metrics_path = live_metrics_path
		os.makedirs(REPORTS_DIR, exist_ok=True)
		self._archive_previous_run()
		with open(self.audit_path, "w", encoding="utf-8"):
			pass
		with open(self.live_metrics_path, "w", encoding="utf-8"):
			pass

	def _archive_previous_run(self) -> None:
		history_dir = Path(REPORTS_DIR) / "history"
		history_dir.mkdir(parents=True, exist_ok=True)
		run_tag = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

		for path in [self.audit_path, self.final_report_path, self.live_metrics_path]:
			if not os.path.exists(path):
				continue
			if os.path.getsize(path) == 0:
				continue
			src = Path(path)
			dst = history_dir / f"{run_tag}_{src.name}"
			try:
				src.replace(dst)
			except OSError:
				# Best effort archival; if rename fails we continue with current file.
				pass

	def write_audit(self, entry: Dict[str, Any]) -> None:
		with open(self.audit_path, "a", encoding="utf-8") as handle:
			handle.write(json.dumps(entry) + "\n")

	def write_final_report(
		self,
		summary: Dict[str, Any],
		incidents: List[Dict[str, Any]],
		llm_run_report: Dict[str, Any] | None = None,
	) -> None:
		payload = {
			"timestamp": utc_now_iso(),
			"summary": summary,
			"incidents": incidents,
			"llm_run_report": llm_run_report or {},
		}
		with open(self.final_report_path, "w", encoding="utf-8") as handle:
			json.dump(payload, handle, indent=2)

	def write_live_metric(self, entry: Dict[str, Any]) -> None:
		with open(self.live_metrics_path, "a", encoding="utf-8") as handle:
			handle.write(json.dumps(entry) + "\n")
