"""Tests for src/collector/parser.py — metric validation and normalisation."""
import pytest

from src.collector.parser import parse_raw_record


def _valid_raw(**overrides):
    base = {
        "timestamp": 10,
        "latency": 20.0,
        "throughput": 55.0,
        "packet_loss": 0.01,
        "jitter": 2.5,
        "node_id": "node-1",
        "node_up": True,
    }
    base.update(overrides)
    return base


class TestParseRawRecordHappyPath:
    def test_returns_normalized_keys(self):
        result = parse_raw_record(_valid_raw())
        assert result["timestamp"] == 10
        assert result["latency_ms"] == 20.0
        assert result["throughput_mbps"] == 55.0
        assert result["packet_loss"] == 0.01
        assert result["jitter"] == 2.5
        assert result["node_id"] == "node-1"
        assert result["node_up"] is True

    def test_defaults_node_id_and_node_up(self):
        raw = {k: v for k, v in _valid_raw().items() if k not in ("node_id", "node_up")}
        result = parse_raw_record(raw)
        assert result["node_id"] == "node-1"
        assert result["node_up"] is True

    def test_packet_loss_boundaries(self):
        r0 = parse_raw_record(_valid_raw(packet_loss=0.0))
        assert r0["packet_loss"] == 0.0
        r1 = parse_raw_record(_valid_raw(packet_loss=1.0))
        assert r1["packet_loss"] == 1.0

    def test_zero_latency_accepted(self):
        result = parse_raw_record(_valid_raw(latency=0.0))
        assert result["latency_ms"] == 0.0

    def test_zero_throughput_accepted(self):
        result = parse_raw_record(_valid_raw(throughput=0.0))
        assert result["throughput_mbps"] == 0.0


class TestParseRawRecordMissingKeys:
    @pytest.mark.parametrize("missing_key", ["timestamp", "latency", "throughput", "packet_loss", "jitter"])
    def test_raises_on_missing_required_key(self, missing_key):
        raw = _valid_raw()
        del raw[missing_key]
        with pytest.raises(ValueError, match=missing_key):
            parse_raw_record(raw)


class TestParseRawRecordOutOfRange:
    def test_negative_packet_loss_raises(self):
        with pytest.raises(ValueError, match="packet_loss"):
            parse_raw_record(_valid_raw(packet_loss=-0.001))

    def test_packet_loss_above_one_raises(self):
        with pytest.raises(ValueError, match="packet_loss"):
            parse_raw_record(_valid_raw(packet_loss=1.001))

    def test_negative_latency_raises(self):
        with pytest.raises(ValueError, match="latency"):
            parse_raw_record(_valid_raw(latency=-1.0))

    def test_negative_throughput_raises(self):
        with pytest.raises(ValueError, match="throughput"):
            parse_raw_record(_valid_raw(throughput=-0.5))

    def test_negative_jitter_raises(self):
        with pytest.raises(ValueError, match="jitter"):
            parse_raw_record(_valid_raw(jitter=-0.1))
