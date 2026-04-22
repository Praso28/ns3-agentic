import logging
import logging.config
from collections import deque
import argparse
from typing import Dict, List, Optional

from src.agent.executor import Executor
from src.agent.incident_manager import IncidentManager
from src.agent.main import AgentCore
from src.agent.verifier import Verifier
from src.collector.ns3_bridge import Ns3Bridge
from src.llm.explainer import Explainer
from src.simulation.ns3_runner import Ns3Runner
from src.simulation.scenario_runner import ScenarioRunner
from src.utils.config import (
	ENGINE_REAL,
	ENGINE_SIMULATION,
	INCIDENT_COOLDOWN_SECONDS,
	INCIDENT_MAX_RETRIES,
	MIN_PERSISTENCE_TO_ACT,
	VERIFY_WINDOW,
)
from src.utils.logger import AuditLogger, utc_now_iso

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
	datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("run")


def run_system(
	scenario_path: str = "scenarios/combo.json",
	engine: str = ENGINE_REAL,
	ns3_command: Optional[str] = None,
) -> Dict:
	log.info("=" * 60)
	log.info("ai5g-ns3 autonomous agent starting")
	log.info("  engine   : %s", engine)
	log.info("  scenario : %s", scenario_path)
	if ns3_command:
		log.info("  ns3 cmd  : %s", ns3_command[:100])
	log.info("=" * 60)

	if engine == ENGINE_REAL:
		log.info("Initialising real ns-3 runner")
		runner = Ns3Runner.from_scenario(scenario_path=scenario_path, command_override=ns3_command)
		metric_source = runner.iter_raw_metrics()
		controller = runner.controller
	else:
		log.info("Initialising simulation runner (TEST MODE — not real ns-3 telemetry)")
		runner = ScenarioRunner(scenario_path=scenario_path)
		metric_source = runner.iter_raw_metrics()
		controller = runner.controller

	bridge = Ns3Bridge()
	agent = AgentCore()
	executor = Executor(controller)
	verifier = Verifier()
	incident_manager = IncidentManager()
	audit_logger = AuditLogger()
	explainer = Explainer()

	pre_window: deque = deque(maxlen=VERIFY_WINDOW)
	incidents: List[Dict] = []
	pending: Optional[Dict] = None
	total_records = 0
	cooldown_until = -1

	for metric in bridge.iter_metrics(metric_source):
		total_records += 1
		pre_window.append(metric)
		metric_ts = int(metric.get("timestamp", total_records))

		result = agent.evaluate(metric)
		observation = result["observation"]
		diagnosis = result["diagnosis"]
		decision = result["decision"]

		# Always write live telemetry for dashboard visibility.
		audit_logger.write_live_metric(
			{
				"timestamp": utc_now_iso(),
				"metric_timestamp": metric_ts,
				"metric": metric,
				"observation": observation,
				"diagnosis": diagnosis,
				"decision": decision,
				"active_incident_id": incident_manager.active_incident_id,
				"pending_verification": pending is not None,
			}
		)

		log.debug(
			"ts=%d anomaly=%s fault=%s conf=%.3f sev=%.3f persist=%.3f action=%s mode=%s",
			metric_ts,
			observation.get("anomaly", False),
			diagnosis.get("fault", "?"),
			decision.get("confidence", 0.0),
			observation.get("severity", 0.0),
			observation.get("persistence", 0.0),
			decision.get("action", "?"),
			decision.get("mode", "?"),
		)

		# --- Verification window processing ------------------------------------
		# IMPORTANT: run this regardless of current anomaly state.
		# Recovery MEANS the anomaly goes away — we want to capture that as
		# improvement evidence in the post-action window.
		if pending is not None:
			pending["post_window"].append(metric)
			if len(pending["post_window"]) >= VERIFY_WINDOW:
				verification = verifier.verify(
					pending["pre_window"],
					pending["post_window"],
					fault=pending["decision"].get("fault", "NONE"),
					action=pending["decision"].get("action", "no_action"),
				)

				log.info(
					"verification incident_id=%s fault=%s action=%s state=%s score=%.4f target=%.4f",
					pending["incident"]["incident_id"],
					pending["decision"].get("fault"),
					pending["decision"].get("action"),
					verification["state"],
					verification.get("score", 0.0),
					verification.get("target_score", 0.0),
				)

				llm_data = explainer.explain_incident(
					fault=pending["decision"]["fault"],
					metrics=metric,
					confidence=pending["decision"]["confidence"],
					action=pending["decision"]["action"],
					verification_state=verification["state"],
				)

				entry: Dict = {
					"timestamp": utc_now_iso(),
					"metric_timestamp": pending.get("incident_metric_timestamp", metric_ts),
					"incident_id": pending["incident"]["incident_id"],
					"fault": pending["decision"]["fault"],
					"confidence": pending["decision"]["confidence"],
					"action": pending["decision"]["action"],
					"verification_state": verification["state"],
					"verification_score": verification.get("score"),
					"verification_checks": verification.get("checks"),
					"verification_deltas": verification.get("deltas"),
					"llm_explanation": llm_data.get("explanation", ""),
					"llm_reasoning": llm_data.get("reasoning", ""),
					"llm_recommendation": llm_data.get("recommendation", ""),
				}
				audit_logger.write_audit(entry)
				incidents.append(entry)

				if verification["state"] == "RESOLVED":
					log.info(
						"incident_resolved id=%s fault=%s action=%s",
						pending["incident"]["incident_id"],
						pending["decision"].get("fault"),
						pending["decision"].get("action"),
					)
					incident_manager.close_incident()
					cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
					pending = None
				else:
					retry_count = int(pending.get("retry_count", 0))
					if retry_count < INCIDENT_MAX_RETRIES:
						log.info(
							"incident_retry id=%s fault=%s attempt=%d/%d",
							pending["incident"]["incident_id"],
							pending["decision"].get("fault"),
							retry_count + 1,
							INCIDENT_MAX_RETRIES,
						)
						execution = executor.execute(pending["decision"])
						if execution.get("executed", False):
							pending = {
								"incident": pending["incident"],
								"decision": pending["decision"],
								"pre_window": list(pre_window),
								"post_window": [],
								"retry_count": retry_count + 1,
							}
						else:
							log.warning(
								"incident_retry_skipped id=%s reason=executor_rejected",
								pending["incident"]["incident_id"],
							)
							incident_manager.close_incident()
							cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
							pending = None
					else:
						log.warning(
							"incident_escalated id=%s fault=%s max_retries=%d reached",
							pending["incident"]["incident_id"],
							pending["decision"].get("fault"),
							INCIDENT_MAX_RETRIES,
						)
						incident_manager.close_incident()
						cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
						pending = None

		# --- New incident gate (GAP 4: no-anomaly silent path) -----------------
		# Only consider opening a new incident when an anomaly is actively present.
		# All other guards (mode, persistence, cooldown) remain in place.
		should_act = (
			observation.get("anomaly", False)  # system stays silent when healthy
			and pending is None               # no concurrent incident being verified
			and decision["mode"] == "ACT"
			and decision["action"] != "no_action"
			and observation.get("persistence", 0.0) >= MIN_PERSISTENCE_TO_ACT
			and metric_ts >= cooldown_until
			and incident_manager.active_incident_id is None
		)
		if should_act:
			incident = incident_manager.open_incident(decision["fault"], decision["target"])
			log.info(
				"incident_opened id=%s fault=%s action=%s target=%s conf=%.3f sev=%.3f",
				incident["incident_id"],
				decision["fault"],
				decision["action"],
				decision["target"],
				decision["confidence"],
				decision.get("severity", 0.0),
			)
			execution = executor.execute(decision)
			if execution["executed"]:
				pending = {
					"incident": incident,
					"incident_metric_timestamp": metric_ts,
					"decision": decision,
					"pre_window": list(pre_window),
					"post_window": [],
					"retry_count": 0,
				}
			else:
				log.warning(
					"incident_action_failed id=%s reason=%s",
					incident["incident_id"],
					execution.get("reason", "unknown"),
				)
				incident_manager.close_incident()

	# --------------------------------------------------------------------------
	# Run summary
	# --------------------------------------------------------------------------
	resolved_count = sum(1 for item in incidents if item["verification_state"] == "RESOLVED")
	escalated_count = sum(1 for item in incidents if item["verification_state"] == "ESCALATE")
	summary = {
		"scenario": scenario_path,
		"engine": engine,
		"records_processed": total_records,
		"incidents": len(incidents),
		"resolved": resolved_count,
		"escalated": escalated_count,
		"fault_counts": {
			"F1": sum(1 for item in incidents if item.get("fault") == "F1"),
			"F2": sum(1 for item in incidents if item.get("fault") == "F2"),
			"F3": sum(1 for item in incidents if item.get("fault") == "F3"),
		},
	}
	log.info(
		"run_complete records=%d incidents=%d resolved=%d escalated=%d",
		total_records, len(incidents), resolved_count, escalated_count,
	)

	llm_run_report = explainer.explain_run_summary(incidents=incidents, summary=summary)
	audit_logger.write_final_report(summary=summary, incidents=incidents, llm_run_report=llm_run_report)
	return summary


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Run ai5g-ns3 agent pipeline.")
	parser.add_argument("--scenario", default="scenarios/combo.json", help="Path to scenario JSON")
	parser.add_argument(
		"--engine",
		default=ENGINE_REAL,
		choices=[ENGINE_REAL, ENGINE_SIMULATION],
		help="Use real ns-3 process mode or local simulation mode",
	)
	parser.add_argument(
		"--ns3-command",
		default=None,
		help="Override scenario ns3.command for real mode",
	)
	args = parser.parse_args()

	result = run_system(scenario_path=args.scenario, engine=args.engine, ns3_command=args.ns3_command)
	print("Run completed:", result)
