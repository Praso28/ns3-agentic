from typing import Dict


class Executor:
	def __init__(self, simulation_controller: object) -> None:
		self.controller = simulation_controller

	def execute(self, decision: Dict) -> Dict:
		action = decision.get("action", "no_action")
		target = decision.get("target", "node-1")

		if action == "restart_node":
			if self.controller is None or not hasattr(self.controller, "restart_node"):
				return {"executed": False, "action": action, "target": target, "reason": "controller_missing"}
			self.controller.restart_node(target)
			return {"executed": True, "action": action, "target": target}

		if action == "reduce_load":
			if self.controller is None or not hasattr(self.controller, "reduce_load"):
				return {"executed": False, "action": action, "target": target, "reason": "controller_missing"}
			self.controller.reduce_load()
			return {"executed": True, "action": action, "target": target}

		return {"executed": False, "action": "no_action", "target": target}
