from typing import Dict

from src.utils.config import ConfidenceCoefficients


FAULT_ACTION_MAP = {
	"F1": "restart_node",
	"F2": "reduce_load",
	"F3": "no_action",
	"NONE": "no_action",
}


def _reduce_load_factor(severity: float) -> float:
	"""Select load-reduction factor based on anomaly severity.

	Higher severity → larger factor so the action has a measurable effect
	that the verifier can confirm as improvement.
	"""
	if severity > 0.7:
		return 0.7
	if severity > 0.5:
		return 0.5
	return 0.3


class Planner:
	def __init__(self, coeffs: ConfidenceCoefficients = ConfidenceCoefficients()) -> None:
		self.coeffs = coeffs

	def plan(self, diagnosis: Dict, confidence: float, severity: float = 0.0) -> Dict:
		fault = diagnosis.get("fault", "NONE")
		action = FAULT_ACTION_MAP.get(fault, "no_action")
		mode = "ACT" if confidence >= self.coeffs.act_threshold and action != "no_action" else "ADVISE"

		# For reduce_load actions, compute the factor now so the executor can
		# use it without re-deriving it from raw observations.
		reduce_load_factor: float = _reduce_load_factor(severity) if action == "reduce_load" else 0.3

		return {
			"fault": fault,
			"target": diagnosis.get("target", "node-1"),
			"confidence": round(confidence, 4),
			"action": action,
			"mode": mode,
			"severity": round(severity, 4),
			"reduce_load_factor": round(reduce_load_factor, 2),
		}
