import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Executor:
	"""Translates planner decisions into controller calls and emits structured action logs."""

	def __init__(self, simulation_controller: Any) -> None:
		self.controller = simulation_controller

	def execute(self, decision: Dict) -> Dict:
		"""Execute the given decision and return a structured execution result.

		Returns a dict with at minimum:
		  - executed (bool)
		  - action (str)
		  - target (str)
		  - reason (str, present only on failure)
		  - factor (float, present for reduce_load)
		"""
		action: str = decision.get("action", "no_action")
		target: str = decision.get("target", "node-1")
		fault: str = decision.get("fault", "NONE")
		severity: float = float(decision.get("severity", 0.0))
		confidence: float = float(decision.get("confidence", 0.0))

		if action == "restart_node":
			if self.controller is None or not hasattr(self.controller, "restart_node"):
				result = {"executed": False, "action": action, "target": target, "reason": "controller_missing"}
				logger.warning("action_skipped action=%s target=%s reason=controller_missing", action, target)
				return result
			try:
				self.controller.restart_node(target)
			except Exception as exc:  # noqa: BLE001
				result = {"executed": False, "action": action, "target": target, "reason": str(exc)}
				logger.error("action_failed action=%s target=%s error=%s", action, target, exc)
				return result
			result = {"executed": True, "action": action, "target": target}
			logger.info(
				"action_sent action=%s target=%s fault=%s severity=%.3f confidence=%.3f",
				action, target, fault, severity, confidence,
			)
			return result

		if action == "reduce_load":
			if self.controller is None or not hasattr(self.controller, "reduce_load"):
				result = {"executed": False, "action": action, "target": target, "reason": "controller_missing"}
				logger.warning("action_skipped action=%s target=%s reason=controller_missing", action, target)
				return result
			# Use severity-based factor baked into the decision by the planner.
			factor: float = float(decision.get("reduce_load_factor", 0.3))
			try:
				self.controller.reduce_load(factor=factor, target=target)
			except Exception as exc:  # noqa: BLE001
				result = {"executed": False, "action": action, "target": target, "reason": str(exc)}
				logger.error("action_failed action=%s target=%s factor=%.2f error=%s", action, target, factor, exc)
				return result
			result = {"executed": True, "action": action, "target": target, "factor": factor}
			logger.info(
				"action_sent action=%s target=%s factor=%.2f fault=%s severity=%.3f confidence=%.3f",
				action, target, factor, fault, severity, confidence,
			)
			return result

		# no_action or unknown
		logger.debug("action_skipped action=%s target=%s reason=no_actionable_intent", action, target)
		return {"executed": False, "action": "no_action", "target": target}
