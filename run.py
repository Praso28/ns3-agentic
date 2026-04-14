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


def run_system(
	scenario_path: str = "scenarios/combo.json",
	engine: str = ENGINE_REAL,
	ns3_command: Optional[str] = None,
) -> Dict:
	if engine == ENGINE_REAL:
		runner = Ns3Runner.from_scenario(scenario_path=scenario_path, command_override=ns3_command)
		metric_source = runner.iter_raw_metrics()
		controller = runner.controller
	else:
		runner = ScenarioRunner(scenario_path=scenario_path)
		metric_source = runner.iter_raw_metrics()
		controller = runner.controller

	bridge = Ns3Bridge()
	agent = AgentCore()
	executor = Executor(controller)
	verifier = Verifier()
	incident_manager = IncidentManager()
	logger = AuditLogger()
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

		logger.write_live_metric(
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

		if pending is not None:
			pending["post_window"].append(metric)
			if len(pending["post_window"]) >= VERIFY_WINDOW:
				verification = verifier.verify(pending["pre_window"], pending["post_window"])
				llm_data = explainer.explain_incident(
					fault=pending["decision"]["fault"],
					metrics=metric,
					confidence=pending["decision"]["confidence"],
					action=pending["decision"]["action"],
					verification_state=verification["state"],
				)

				entry = {
					"timestamp": utc_now_iso(),
					"metric_timestamp": pending.get("incident_metric_timestamp", metric_ts),
					"incident_id": pending["incident"]["incident_id"],
					"fault": pending["decision"]["fault"],
					"confidence": pending["decision"]["confidence"],
					"action": pending["decision"]["action"],
					"verification_state": verification["state"],
					"llm_explanation": llm_data["explanation"],
				}
				logger.write_audit(entry)
				incidents.append(entry)

				if verification["state"] == "RESOLVED":
					incident_manager.close_incident()
					cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
					pending = None
				else:
					retry_count = int(pending.get("retry_count", 0))
					if retry_count < INCIDENT_MAX_RETRIES:
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
							incident_manager.close_incident()
							cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
							pending = None
					else:
						incident_manager.close_incident()
						cooldown_until = metric_ts + INCIDENT_COOLDOWN_SECONDS
						pending = None

		should_act = (
			decision["mode"] == "ACT"
			and decision["action"] != "no_action"
			and observation.get("persistence", 0.0) >= MIN_PERSISTENCE_TO_ACT
			and metric_ts >= cooldown_until
		)
		if should_act and incident_manager.active_incident_id is None:
			incident = incident_manager.open_incident(decision["fault"], decision["target"])
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

	summary = {
		"scenario": scenario_path,
		"engine": engine,
		"records_processed": total_records,
		"incidents": len(incidents),
		"resolved": sum(1 for item in incidents if item["verification_state"] == "RESOLVED"),
		"escalated": sum(1 for item in incidents if item["verification_state"] == "ESCALATE"),
		"fault_counts": {
			"F1": sum(1 for item in incidents if item.get("fault") == "F1"),
			"F2": sum(1 for item in incidents if item.get("fault") == "F2"),
			"F3": sum(1 for item in incidents if item.get("fault") == "F3"),
		},
	}
	llm_run_report = explainer.explain_run_summary(incidents=incidents, summary=summary)
	logger.write_final_report(summary=summary, incidents=incidents, llm_run_report=llm_run_report)
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
