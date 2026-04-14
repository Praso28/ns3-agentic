from typing import Dict


class Diagnoser:
	def diagnose(self, observation: Dict) -> Dict:
		latest = observation.get("latest", {})
		signals = observation.get("signals", {})

		if not observation.get("anomaly", False):
			return {"fault": "NONE", "target": latest.get("node_id", "node-1")}

		throughput = latest.get("throughput_mbps", 0.0)
		node_up = latest.get("node_up", True)

		if (not node_up) or throughput <= 0.5:
			return {"fault": "F1", "target": latest.get("node_id", "node-1")}

		if signals.get("latency_spike") and signals.get("throughput_drop"):
			return {"fault": "F2", "target": latest.get("node_id", "node-1")}

		if signals.get("packet_loss_increase") and signals.get("jitter_high"):
			return {"fault": "F3", "target": latest.get("node_id", "node-1")}

		if signals.get("latency_spike") or signals.get("throughput_drop"):
			return {"fault": "F2", "target": latest.get("node_id", "node-1")}

		return {"fault": "F3", "target": latest.get("node_id", "node-1")}
