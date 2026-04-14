from collections import deque
from typing import Deque, Dict

from src.utils.config import Thresholds, WINDOW_SECONDS


class Observer:
	def __init__(self, window_seconds: int = WINDOW_SECONDS, thresholds: Thresholds = Thresholds()) -> None:
		self.window_seconds = window_seconds
		self.thresholds = thresholds
		self.window: Deque[Dict] = deque(maxlen=window_seconds)
		self.signal_history: Deque[bool] = deque(maxlen=window_seconds)

	def _mean(self, key: str) -> float:
		if not self.window:
			return 0.0
		return sum(item[key] for item in self.window) / len(self.window)

	def observe(self, snapshot: Dict) -> Dict:
		self.window.append(snapshot)
		if len(self.window) < max(6, self.window_seconds // 4):
			return {
				"anomaly": False,
				"signals": {},
				"severity": 0.0,
				"persistence": 0.0,
				"latest": snapshot,
			}

		mean_latency = self._mean("latency_ms")
		mean_throughput = self._mean("throughput_mbps")
		mean_loss = self._mean("packet_loss")

		latency_spike = (
			snapshot["latency_ms"] > max(mean_latency * 1.4, self.thresholds.latency_ms_high)
		)
		throughput_drop = (
			snapshot["throughput_mbps"] < min(mean_throughput * 0.60, self.thresholds.throughput_mbps_low)
		)
		packet_loss_increase = (
			snapshot["packet_loss"] > max(mean_loss * 1.5, self.thresholds.packet_loss_high)
		)
		jitter_high = snapshot["jitter"] > self.thresholds.jitter_high

		signals = {
			"latency_spike": latency_spike,
			"throughput_drop": throughput_drop,
			"packet_loss_increase": packet_loss_increase,
			"jitter_high": jitter_high,
		}

		active_count = sum(1 for value in signals.values() if value)
		anomaly = active_count > 0
		self.signal_history.append(anomaly)

		severity = active_count / 4.0
		persistence = (
			sum(1 for value in self.signal_history if value) / len(self.signal_history)
			if self.signal_history
			else 0.0
		)

		return {
			"anomaly": anomaly,
			"signals": signals,
			"severity": round(severity, 4),
			"persistence": round(persistence, 4),
			"latest": snapshot,
		}
