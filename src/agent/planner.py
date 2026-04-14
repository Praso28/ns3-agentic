from typing import Dict

from src.utils.config import ConfidenceCoefficients


FAULT_ACTION_MAP = {
	"F1": "restart_node",
	"F2": "reduce_load",
	"F3": "no_action",
	"NONE": "no_action",
}


class Planner:
	def __init__(self, coeffs: ConfidenceCoefficients = ConfidenceCoefficients()) -> None:
		self.coeffs = coeffs

	def plan(self, diagnosis: Dict, confidence: float) -> Dict:
		fault = diagnosis.get("fault", "NONE")
		action = FAULT_ACTION_MAP.get(fault, "no_action")
		mode = "ACT" if confidence >= self.coeffs.act_threshold and action != "no_action" else "ADVISE"

		return {
			"fault": fault,
			"target": diagnosis.get("target", "node-1"),
			"confidence": round(confidence, 4),
			"action": action,
			"mode": mode,
		}
