from typing import Dict

from src.agent.confidence import ConfidenceModel
from src.agent.diagnoser import Diagnoser
from src.agent.observer import Observer
from src.agent.planner import Planner


class AgentCore:
	def __init__(self) -> None:
		self.observer = Observer()
		self.diagnoser = Diagnoser()
		self.confidence_model = ConfidenceModel()
		self.planner = Planner()

	def evaluate(self, snapshot: Dict) -> Dict:
		observation = self.observer.observe(snapshot)
		diagnosis = self.diagnoser.diagnose(observation)
		confidence = self.confidence_model.compute(observation, diagnosis)
		decision = self.planner.plan(diagnosis, confidence)
		return {
			"observation": observation,
			"diagnosis": diagnosis,
			"decision": decision,
		}
