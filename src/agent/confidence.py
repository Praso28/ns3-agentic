import math
from typing import Dict

from src.utils.config import ConfidenceCoefficients


def sigmoid(value: float) -> float:
	return 1.0 / (1.0 + math.exp(-value))


class ConfidenceModel:
	def __init__(self, coeffs: ConfidenceCoefficients = ConfidenceCoefficients()) -> None:
		self.coeffs = coeffs

	def compute(self, observation: Dict, diagnosis: Dict) -> float:
		if diagnosis.get("fault") == "NONE":
			return 0.0

		l_val = 1.0 if observation.get("anomaly", False) else 0.0
		m_val = float(observation.get("severity", 0.0))
		h_val = float(observation.get("persistence", 0.0))

		score = 0.5 * l_val + 0.3 * m_val + 0.2 * h_val
		confidence = sigmoid(self.coeffs.a * score + self.coeffs.b)
		return max(0.0, min(confidence, 1.0))
