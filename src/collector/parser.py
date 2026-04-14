from typing import Dict


REQUIRED_KEYS = (
	"timestamp",
	"latency",
	"throughput",
	"packet_loss",
	"jitter",
)


def parse_raw_record(raw: Dict) -> Dict:
	for key in REQUIRED_KEYS:
		if key not in raw:
			raise ValueError(f"Missing required key: {key}")

	packet_loss = float(raw["packet_loss"])
	if packet_loss < 0 or packet_loss > 1:
		raise ValueError(f"packet_loss out of range: {packet_loss}")

	return {
		"timestamp": int(raw["timestamp"]),
		"latency_ms": float(raw["latency"]),
		"throughput_mbps": float(raw["throughput"]),
		"packet_loss": packet_loss,
		"jitter": float(raw["jitter"]),
		"node_id": str(raw.get("node_id", "node-1")),
		"node_up": bool(raw.get("node_up", True)),
	}
