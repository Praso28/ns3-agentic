"""Tests for src/agent/diagnoser.py — fault classification logic."""
import pytest

from src.agent.diagnoser import Diagnoser


def _obs(anomaly=True, signals=None, throughput=50.0, node_up=True, node_id="node-1"):
    return {
        "anomaly": anomaly,
        "signals": signals or {},
        "severity": 0.5,
        "persistence": 0.5,
        "latest": {
            "throughput_mbps": throughput,
            "node_up": node_up,
            "node_id": node_id,
        },
    }


class TestDiagnoserNoAnomaly:
    def test_no_anomaly_returns_none_fault(self):
        diagnoser = Diagnoser()
        obs = _obs(anomaly=False)
        result = diagnoser.diagnose(obs)
        assert result["fault"] == "NONE"

    def test_no_anomaly_preserves_node_id(self):
        diagnoser = Diagnoser()
        obs = _obs(anomaly=False, node_id="node-7")
        result = diagnoser.diagnose(obs)
        assert result["target"] == "node-7"


class TestDiagnoserF1:
    def test_node_down_signal_triggers_f1(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={"node_down": True})
        assert diagnoser.diagnose(obs)["fault"] == "F1"

    def test_node_up_false_triggers_f1(self):
        diagnoser = Diagnoser()
        obs = _obs(node_up=False)
        assert diagnoser.diagnose(obs)["fault"] == "F1"

    def test_near_zero_throughput_triggers_f1(self):
        diagnoser = Diagnoser()
        obs = _obs(throughput=0.3)
        assert diagnoser.diagnose(obs)["fault"] == "F1"

    def test_f1_boundary_exactly_half_mbps(self):
        diagnoser = Diagnoser()
        obs = _obs(throughput=0.5)
        assert diagnoser.diagnose(obs)["fault"] == "F1"


class TestDiagnoserF2:
    def test_latency_and_throughput_drop_gives_f2(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={"latency_spike": True, "throughput_drop": True})
        assert diagnoser.diagnose(obs)["fault"] == "F2"

    def test_latency_spike_alone_gives_f2(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={"latency_spike": True})
        assert diagnoser.diagnose(obs)["fault"] == "F2"

    def test_throughput_drop_alone_gives_f2(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={"throughput_drop": True})
        assert diagnoser.diagnose(obs)["fault"] == "F2"


class TestDiagnoserF3:
    def test_loss_and_jitter_gives_f3(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={"packet_loss_increase": True, "jitter_high": True})
        assert diagnoser.diagnose(obs)["fault"] == "F3"

    def test_generic_anomaly_without_signals_falls_through_to_f3(self):
        diagnoser = Diagnoser()
        obs = _obs(signals={})
        assert diagnoser.diagnose(obs)["fault"] == "F3"


class TestDiagnoserPriority:
    def test_f1_takes_priority_over_f2_signals(self):
        """Node down should win even when congestion signals also present."""
        diagnoser = Diagnoser()
        obs = _obs(node_up=False, signals={"latency_spike": True, "throughput_drop": True})
        assert diagnoser.diagnose(obs)["fault"] == "F1"

    def test_f2_takes_priority_over_f3(self):
        """Latency+throughput congestion wins over loss+jitter."""
        diagnoser = Diagnoser()
        obs = _obs(signals={
            "latency_spike": True,
            "throughput_drop": True,
            "packet_loss_increase": True,
            "jitter_high": True,
        })
        assert diagnoser.diagnose(obs)["fault"] == "F2"
