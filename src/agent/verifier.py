from typing import Dict, List


class Verifier:
	def _avg(self, data: List[Dict], key: str) -> float:
		if not data:
			return 0.0
		return sum(item[key] for item in data) / len(data)

	def verify(self, pre_window: List[Dict], post_window: List[Dict]) -> Dict:
		pre_latency = self._avg(pre_window, "latency_ms")
		pre_throughput = self._avg(pre_window, "throughput_mbps")
		pre_loss = self._avg(pre_window, "packet_loss")

		post_latency = self._avg(post_window, "latency_ms")
		post_throughput = self._avg(post_window, "throughput_mbps")
		post_loss = self._avg(post_window, "packet_loss")

		improved = (
			post_latency < pre_latency
			and post_throughput > pre_throughput
			and post_loss < pre_loss
		)

		return {
			"state": "RESOLVED" if improved else "ESCALATE",
			"deltas": {
				"latency_ms": round(post_latency - pre_latency, 4),
				"throughput_mbps": round(post_throughput - pre_throughput, 4),
				"packet_loss": round(post_loss - pre_loss, 6),
			},
		}
