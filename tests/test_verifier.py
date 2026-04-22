"""Tests for src/agent/verifier.py — recovery verification logic."""
import pytest

from src.agent.verifier import Verifier
from src.utils.config import VerifyCriteria


def _snap(latency_ms=20.0, throughput_mbps=55.0, packet_loss=0.01, jitter=2.0, ts=0):
    return {
        "timestamp": ts,
        "latency_ms": latency_ms,
        "throughput_mbps": throughput_mbps,
        "packet_loss": packet_loss,
        "jitter": jitter,
        "node_id": "node-1",
        "node_up": True,
    }


def _window(n=5, **kw):
    return [_snap(**kw, ts=i) for i in range(n)]


class TestVerifierEmptyWindows:
    def test_empty_pre_window_escalates(self):
        v = Verifier()
        result = v.verify([], _window(), fault="F2", action="reduce_load")
        assert result["state"] == "ESCALATE"

    def test_empty_post_window_escalates(self):
        v = Verifier()
        result = v.verify(_window(), [], fault="F2", action="reduce_load")
        assert result["state"] == "ESCALATE"


class TestVerifierF2ReduceLoad:
    def test_clear_improvement_resolves(self):
        """Post latency and throughput much better than pre → RESOLVED."""
        v = Verifier()
        pre = _window(latency_ms=90.0, throughput_mbps=20.0, packet_loss=0.08)
        post = _window(latency_ms=25.0, throughput_mbps=55.0, packet_loss=0.01)
        result = v.verify(pre, post, fault="F2", action="reduce_load")
        assert result["state"] == "RESOLVED"
        assert result["score"] > result["target_score"]

    def test_no_improvement_escalates(self):
        """Metrics stay the same → should ESCALATE."""
        v = Verifier()
        snap = _window(latency_ms=90.0, throughput_mbps=20.0, packet_loss=0.08)
        result = v.verify(snap, list(snap), fault="F2", action="reduce_load")
        assert result["state"] == "ESCALATE"

    def test_score_above_target_resolves_even_without_hard_checks(self):
        """If composite score clears the F2 gate, it should resolve."""
        criteria = VerifyCriteria(
            resolve_score_f2=0.10,   # very low gate
            latency_improve_ratio=0.99,  # hard to satisfy
            throughput_improve_ratio=0.99,
        )
        v = Verifier(criteria=criteria)
        pre = _window(latency_ms=80.0, throughput_mbps=20.0, packet_loss=0.10)
        post = _window(latency_ms=65.0, throughput_mbps=25.0, packet_loss=0.07)
        result = v.verify(pre, post, fault="F2", action="reduce_load")
        # Score-based OR path should fire.
        assert result["state"] == "RESOLVED"


class TestVerifierF1RestartNode:
    def test_latency_improvement_alone_resolves(self):
        """After restart, latency recovers; throughput may still be ramping."""
        criteria = VerifyCriteria(latency_tolerance_ms=4.0, latency_improve_ratio=0.10)
        v = Verifier(criteria=criteria)
        pre = _window(latency_ms=200.0, throughput_mbps=0.2, packet_loss=0.90)
        post = _window(latency_ms=22.0, throughput_mbps=40.0, packet_loss=0.02)
        result = v.verify(pre, post, fault="F1", action="restart_node")
        assert result["state"] == "RESOLVED"

    def test_no_recovery_after_restart_escalates(self):
        pre = _window(latency_ms=200.0, throughput_mbps=0.1, packet_loss=0.95)
        post = _window(latency_ms=195.0, throughput_mbps=0.2, packet_loss=0.90)
        v = Verifier()
        result = v.verify(pre, post, fault="F1", action="restart_node")
        assert result["state"] == "ESCALATE"


class TestVerifierNoAction:
    def test_healthy_baseline_no_change_escalates(self):
        v = Verifier()
        snap = _window()
        result = v.verify(snap, list(snap), fault="NONE", action="no_action")
        assert result["state"] == "ESCALATE"


class TestVerifierReturnShape:
    def test_result_has_all_keys(self):
        v = Verifier()
        pre = _window(latency_ms=80.0, throughput_mbps=20.0, packet_loss=0.08)
        post = _window(latency_ms=25.0, throughput_mbps=55.0, packet_loss=0.01)
        result = v.verify(pre, post, fault="F2", action="reduce_load")
        for key in ("state", "score", "target_score", "checks", "deltas"):
            assert key in result
        for ck in ("latency_ok", "throughput_ok", "loss_ok"):
            assert ck in result["checks"]
        for dk in ("latency_ms", "throughput_mbps", "packet_loss"):
            assert dk in result["deltas"]
