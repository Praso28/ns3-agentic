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

	def _std(self, key: str, mean_value: float) -> float:
		if not self.window:
			return 0.0
		variance = sum((item[key] - mean_value) ** 2 for item in self.window) / len(self.window)
		return variance**0.5

	def _positive_z(self, value: float, mean_value: float, std_value: float) -> float:
		return max(0.0, (value - mean_value) / max(std_value, self.thresholds.epsilon))

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
		mean_jitter = self._mean("jitter")

		std_latency = self._std("latency_ms", mean_latency)
		std_throughput = self._std("throughput_mbps", mean_throughput)
		std_loss = self._std("packet_loss", mean_loss)
		std_jitter = self._std("jitter", mean_jitter)

		latency_threshold = max(
			self.thresholds.latency_ms_floor,
			mean_latency + self.thresholds.latency_sigma_k * std_latency,
			self.thresholds.latency_base_offset_ms + self.thresholds.latency_jitter_k * mean_jitter,
		)
		throughput_threshold = max(
			self.thresholds.throughput_mbps_floor,
			min(
				mean_throughput * self.thresholds.throughput_drop_ratio,
				mean_throughput - self.thresholds.throughput_sigma_k * std_throughput,
			),
		)
		loss_threshold = max(
			self.thresholds.packet_loss_floor,
			mean_loss + self.thresholds.packet_loss_sigma_k * std_loss,
		)
		jitter_threshold = max(
			self.thresholds.jitter_floor,
			mean_jitter + self.thresholds.jitter_sigma_k * std_jitter,
		)

		node_down = not bool(snapshot.get("node_up", True))

		latency_spike = snapshot["latency_ms"] > latency_threshold
		throughput_drop = snapshot["throughput_mbps"] < throughput_threshold
		packet_loss_increase = snapshot["packet_loss"] > loss_threshold
		jitter_high = snapshot["jitter"] > jitter_threshold

		signals = {
			"node_down": node_down,
			"latency_spike": latency_spike,
			"throughput_drop": throughput_drop,
			"packet_loss_increase": packet_loss_increase,
			"jitter_high": jitter_high,
		}

		active_count = sum(1 for value in signals.values() if value)
		anomaly = active_count > 0
		self.signal_history.append(anomaly)

		z_latency = self._positive_z(snapshot["latency_ms"], mean_latency, std_latency)
		z_throughput_drop = self._positive_z(mean_throughput - snapshot["throughput_mbps"], 0.0, std_throughput)
		z_loss = self._positive_z(snapshot["packet_loss"], mean_loss, std_loss)
		z_jitter = self._positive_z(snapshot["jitter"], mean_jitter, std_jitter)

		severity = (
			0.35 * min(z_latency / 3.0, 1.0)
			+ 0.30 * min(z_throughput_drop / 3.0, 1.0)
			+ 0.20 * min(z_loss / 3.0, 1.0)
			+ 0.15 * min(z_jitter / 3.0, 1.0)
		)
		if node_down:
			severity = 1.0
		persistence = (
			sum(1 for value in self.signal_history if value) / len(self.signal_history)
			if self.signal_history
			else 0.0
		)

		return {
			"anomaly": anomaly,
			"signals": signals,
			"severity": round(min(severity, 1.0), 4),
			"persistence": round(persistence, 4),
			"latest": snapshot,
			"derived_thresholds": {
				"latency_ms": round(latency_threshold, 4),
				"throughput_mbps": round(throughput_threshold, 4),
				"packet_loss": round(loss_threshold, 6),
				"jitter": round(jitter_threshold, 4),
			},
			"z_scores": {
				"latency": round(z_latency, 4),
				"throughput_drop": round(z_throughput_drop, 4),
				"packet_loss": round(z_loss, 4),
				"jitter": round(z_jitter, 4),
			},
		}
