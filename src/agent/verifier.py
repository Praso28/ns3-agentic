import logging
from typing import Dict, List

from src.utils.config import VerifyCriteria

logger = logging.getLogger(__name__)


class Verifier:
	"""Fault-aware, threshold-driven post-action recovery verifier.

	Uses weighted normalized KPI improvements anchored to the pre-incident
	rolling window (the baseline) and the fault-specific score gates from
	:class:`~src.utils.config.VerifyCriteria`.

	Acceptance rules per action type
	---------------------------------
	* ``reduce_load``  — latency AND throughput must improve, OR the weighted
	  composite score must exceed the fault target.  Requiring both hard-check
	  AND score would be too strict given real-network noise.
	* ``restart_node`` — latency improvement OR the composite score must exceed
	  the F1 target; after a node restart the network can take several seconds
	  to rebuild flow statistics, so we accept a strong score as an alternative.
	* ``no_action``    — score-based gate with at least one KPI improving.
	"""

	def __init__(self, criteria: VerifyCriteria = VerifyCriteria()) -> None:
		self.criteria = criteria

	def _avg(self, data: List[Dict], key: str) -> float:
		if not data:
			return 0.0
		return sum(item[key] for item in data) / len(data)

	@staticmethod
	def _norm_positive(delta: float, baseline: float, eps: float = 1e-6) -> float:
		"""Normalised positive gain: 0 when no improvement, 1 when delta == baseline."""
		return max(0.0, delta / max(abs(baseline), eps))

	def verify(
		self,
		pre_window: List[Dict],
		post_window: List[Dict],
		fault: str = "NONE",
		action: str = "no_action",
	) -> Dict:
		"""Compare pre- and post-action metric windows and decide RESOLVED / ESCALATE.

		Parameters
		----------
		pre_window:
			Metric snapshots collected *before* the action was executed.
		post_window:
			Metric snapshots collected *after* the action was executed.
		fault:
			Diagnosed fault type (F1 / F2 / F3 / NONE).
		action:
			The action that was executed.

		Returns
		-------
		dict with keys: state, score, target_score, checks, deltas.
		"""
		if not pre_window or not post_window:
			logger.warning(
				"verifier: empty window(s) pre=%d post=%d — defaulting to ESCALATE",
				len(pre_window), len(post_window),
			)
			return {
				"state": "ESCALATE",
				"score": 0.0,
				"target_score": 0.0,
				"checks": {"latency_ok": False, "throughput_ok": False, "loss_ok": False},
				"deltas": {"latency_ms": 0.0, "throughput_mbps": 0.0, "packet_loss": 0.0},
			}

		pre_latency = self._avg(pre_window, "latency_ms")
		pre_throughput = self._avg(pre_window, "throughput_mbps")
		pre_loss = self._avg(pre_window, "packet_loss")

		post_latency = self._avg(post_window, "latency_ms")
		post_throughput = self._avg(post_window, "throughput_mbps")
		post_loss = self._avg(post_window, "packet_loss")

		latency_gain = pre_latency - post_latency       # positive = improvement
		throughput_gain = post_throughput - pre_throughput  # positive = improvement
		loss_gain = pre_loss - post_loss                # positive = improvement

		latency_norm = self._norm_positive(latency_gain, pre_latency)
		throughput_norm = self._norm_positive(throughput_gain, pre_throughput)
		loss_norm = self._norm_positive(loss_gain, pre_loss)

		# Weighted composite score (matches PROJECT_STATE formula).
		score = (
			0.45 * min(latency_norm, 1.0)
			+ 0.35 * min(throughput_norm, 1.0)
			+ 0.20 * min(loss_norm, 1.0)
		)

		# Fault-specific target score from VerifyCriteria (config.py).
		if fault == "F1":
			target_score = self.criteria.resolve_score_f1
		elif fault == "F2":
			target_score = self.criteria.resolve_score_f2
		elif fault == "F3":
			target_score = self.criteria.resolve_score_f3
		else:
			target_score = self.criteria.resolve_score_f2

		# Per-KPI hard checks with tolerances from VerifyCriteria.
		latency_ok = latency_gain >= max(
			self.criteria.latency_tolerance_ms,
			self.criteria.latency_improve_ratio * max(pre_latency, 1e-6),
		)
		throughput_ok = throughput_gain >= max(
			self.criteria.throughput_tolerance_mbps,
			self.criteria.throughput_improve_ratio * max(pre_throughput, 1e-6),
		)
		loss_ok = loss_gain >= max(
			self.criteria.loss_tolerance,
			self.criteria.loss_improve_ratio * max(pre_loss, 1e-6),
		)

		# Action-specific acceptance rules.
		if action == "reduce_load":
			# F2: congestion relief must show latency + throughput both moving, OR
			# the composite score is above target (handles noisy single-KPI windows).
			improved = (latency_ok and throughput_ok) or (score >= target_score)
		elif action == "restart_node":
			# F1: after restart latency must improve OR score must cross the F1 gate.
			# Using OR here because throughput needs ~2 s to ramp up after restart.
			improved = latency_ok or (score >= target_score)
		else:
			# no_action / F3 advisory: score-based gate with at least one KPI signal.
			improved = score >= target_score and (latency_ok or throughput_ok or loss_ok)

		state = "RESOLVED" if improved else "ESCALATE"

		logger.info(
			"verifier: fault=%s action=%s state=%s score=%.4f target=%.4f "
			"lat_ok=%s tput_ok=%s loss_ok=%s",
			fault, action, state, score, target_score,
			latency_ok, throughput_ok, loss_ok,
		)

		return {
			"state": state,
			"score": round(score, 4),
			"target_score": round(target_score, 4),
			"checks": {
				"latency_ok": latency_ok,
				"throughput_ok": throughput_ok,
				"loss_ok": loss_ok,
			},
			"deltas": {
				"latency_ms": round(post_latency - pre_latency, 4),
				"throughput_mbps": round(post_throughput - pre_throughput, 4),
				"packet_loss": round(post_loss - pre_loss, 6),
			},
		}
