from typing import Dict


REQUIRED_KEYS = (
	"timestamp",
	"latency",
	"throughput",
	"packet_loss",
	"jitter",
)


def parse_raw_record(raw: Dict) -> Dict:
	"""Parse and validate a raw metric record from ns-3 or the simulation bridge.

	Raises ValueError for missing required keys or out-of-range values so the
	caller can discard the record rather than propagate invalid data.
	"""
	for key in REQUIRED_KEYS:
		if key not in raw:
			raise ValueError(f"Missing required key: {key}")

	latency_ms = float(raw["latency"])
	if latency_ms < 0:
		raise ValueError(f"latency out of range (must be >= 0): {latency_ms}")

	throughput_mbps = float(raw["throughput"])
	if throughput_mbps < 0:
		raise ValueError(f"throughput out of range (must be >= 0): {throughput_mbps}")

	packet_loss = float(raw["packet_loss"])
	if not (0.0 <= packet_loss <= 1.0):
		raise ValueError(f"packet_loss out of range [0, 1]: {packet_loss}")

	jitter = float(raw["jitter"])
	if jitter < 0:
		raise ValueError(f"jitter out of range (must be >= 0): {jitter}")

	timestamp = int(raw["timestamp"])

	return {
		"timestamp": timestamp,
		"latency_ms": latency_ms,
		"throughput_mbps": throughput_mbps,
		"packet_loss": packet_loss,
		"jitter": jitter,
		"node_id": str(raw.get("node_id", "node-1")),
		"node_up": bool(raw.get("node_up", True)),
	}
