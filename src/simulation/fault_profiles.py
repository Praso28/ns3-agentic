import json
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class FaultEvent:
	time: int
	event_type: str
	target: str = "node-1"
	severity: float = 1.0
	duration: int = 10


def load_scenario_file(file_path: str) -> Dict:
	with open(file_path, "r", encoding="utf-8") as handle:
		return json.load(handle)


def parse_fault_events(scenario_data: Dict) -> List[FaultEvent]:
	events = []
	for item in scenario_data.get("events", []):
		events.append(
			FaultEvent(
				time=int(item["time"]),
				event_type=str(item["type"]),
				target=str(item.get("target", "node-1")),
				severity=float(item.get("severity", 1.0)),
				duration=int(item.get("duration", 10)),
			)
		)
	events.sort(key=lambda event: event.time)
	return events
