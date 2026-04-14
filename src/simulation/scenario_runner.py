import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterator, List

if str(Path(__file__).resolve().parents[2]) not in sys.path:
	sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.simulation.fault_profiles import FaultEvent, load_scenario_file, parse_fault_events


class SimulationController:
	def __init__(self, seed: int = 7) -> None:
		self.random = random.Random(seed)
		self.node_up = True
		self.load_multiplier = 1.0
		self.degradation = 0.0
		self.active_faults: Dict[str, int] = {}
		self.node_id = "node-1"

	def apply_fault_event(self, event: FaultEvent) -> None:
		if event.event_type == "node_failure":
			self.node_up = False
			self.active_faults["node_failure"] = event.duration
		elif event.event_type == "traffic_spike":
			self.load_multiplier = max(self.load_multiplier, 1.0 + event.severity)
			self.active_faults["traffic_spike"] = event.duration
		elif event.event_type == "network_degradation":
			self.degradation = max(self.degradation, 0.15 * event.severity)
			self.active_faults["network_degradation"] = event.duration

	def restart_node(self, _target: str) -> None:
		self.node_up = True
		self.active_faults.pop("node_failure", None)

	def reduce_load(self, factor: float = 0.30) -> None:
		self.load_multiplier = max(1.0, self.load_multiplier * (1.0 - factor))
		if self.load_multiplier == 1.0:
			self.active_faults.pop("traffic_spike", None)

	def _tick_fault_decay(self) -> None:
		expired: List[str] = []
		for fault, remaining in self.active_faults.items():
			next_remaining = remaining - 1
			self.active_faults[fault] = next_remaining
			if next_remaining <= 0:
				expired.append(fault)

		for fault in expired:
			del self.active_faults[fault]
			if fault == "traffic_spike":
				self.load_multiplier = 1.0
			if fault == "network_degradation":
				self.degradation = 0.0

	def step(self, timestamp: int) -> Dict:
		base_latency = 20.0
		base_throughput = 120.0
		base_loss = 0.01
		base_jitter = 2.0
		base_queue_delay = 5.0

		if not self.node_up:
			latency = 220.0 + self.random.uniform(-10.0, 10.0)
			throughput = self.random.uniform(0.0, 0.6)
			packet_loss = 0.92 + self.random.uniform(0.0, 0.03)
			jitter = 25.0 + self.random.uniform(-2.0, 2.0)
			queue_delay = 45.0 + self.random.uniform(-4.0, 4.0)
		else:
			load_penalty = max(0.0, self.load_multiplier - 1.0)
			latency = base_latency * (1 + 1.2 * load_penalty + 3.0 * self.degradation)
			latency += self.random.uniform(-2.0, 2.0)
			throughput = base_throughput / (1 + 0.9 * load_penalty + 2.2 * self.degradation)
			throughput += self.random.uniform(-3.0, 3.0)
			packet_loss = base_loss + 0.04 * load_penalty + 0.20 * self.degradation
			packet_loss += self.random.uniform(0.0, 0.01)
			jitter = base_jitter + 5.5 * load_penalty + 12.0 * self.degradation
			jitter += self.random.uniform(-0.8, 0.8)
			queue_delay = base_queue_delay + 10.0 * load_penalty + 15.0 * self.degradation
			queue_delay += self.random.uniform(-1.5, 1.5)

		packet_loss = max(0.0, min(packet_loss, 1.0))
		throughput = max(0.0, throughput)

		snapshot = {
			"timestamp": timestamp,
			"latency": round(latency, 3),
			"throughput": round(throughput, 3),
			"packet_loss": round(packet_loss, 5),
			"jitter": round(jitter, 3),
			"queue_delay": round(queue_delay, 3),
			"node_id": self.node_id,
			"node_up": self.node_up,
		}
		self._tick_fault_decay()
		return snapshot


class ScenarioRunner:
	def __init__(self, scenario_path: str, seed: int = 7) -> None:
		self.scenario_path = scenario_path
		self.scenario_data = load_scenario_file(scenario_path)
		self.controller = SimulationController(seed=seed)
		self.duration = int(self.scenario_data.get("duration", 120))
		self.events = parse_fault_events(self.scenario_data)

	def iter_raw_metrics(self) -> Iterator[Dict]:
		schedule = defaultdict(list)
		for event in self.events:
			schedule[event.time].append(event)

		for timestamp in range(self.duration):
			for event in schedule.get(timestamp, []):
				self.controller.apply_fault_event(event)
			yield self.controller.step(timestamp)


def run_scenario_file(scenario_path: str) -> List[Dict]:
	runner = ScenarioRunner(scenario_path=scenario_path)
	return list(runner.iter_raw_metrics())


if __name__ == "__main__":
	import argparse

	parser = argparse.ArgumentParser(description="Run a simulation scenario.")
	parser.add_argument("--scenario", default="scenarios/combo.json", help="Path to scenario JSON")
	args = parser.parse_args()

	records = run_scenario_file(args.scenario)
	print(f"Generated {len(records)} raw metric records from {args.scenario}")
