import json
import logging
from typing import Dict, Iterable, Iterator

from src.collector.parser import parse_raw_record

logger = logging.getLogger(__name__)


class Ns3Bridge:
	"""Translates raw metric dicts from any source into validated, normalized records.

	Invalid records are logged and discarded rather than propagating downstream
	so a single malformed line from ns-3 stdout does not abort the pipeline.
	"""

	def iter_metrics(self, raw_stream: Iterable[Dict]) -> Iterator[Dict]:
		"""Iterate over a stream of raw dicts, parsing and validating each one."""
		for raw in raw_stream:
			try:
				yield parse_raw_record(raw)
			except (ValueError, KeyError, TypeError) as exc:
				logger.warning("ns3_bridge: discarding invalid record error=%s record=%s", exc, raw)

	def iter_metrics_from_jsonl(self, trace_file_path: str) -> Iterator[Dict]:
		"""Iterate over a JSONL trace file, parsing and validating each line."""
		with open(trace_file_path, "r", encoding="utf-8") as handle:
			for lineno, line in enumerate(handle, start=1):
				line = line.strip()
				if not line:
					continue
				try:
					raw = json.loads(line)
					yield parse_raw_record(raw)
				except json.JSONDecodeError as exc:
					logger.warning("ns3_bridge: JSON decode error line=%d error=%s", lineno, exc)
				except (ValueError, KeyError, TypeError) as exc:
					logger.warning("ns3_bridge: invalid record line=%d error=%s", lineno, exc)
