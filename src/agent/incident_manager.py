from typing import Dict
from uuid import uuid4


class IncidentManager:
	def __init__(self) -> None:
		self.active_incident_id = None

	def open_incident(self, fault: str, target: str) -> Dict:
		if self.active_incident_id is None:
			self.active_incident_id = f"inc-{uuid4().hex[:10]}"
		return {
			"incident_id": self.active_incident_id,
			"fault": fault,
			"target": target,
		}

	def close_incident(self) -> None:
		self.active_incident_id = None
