import json
from typing import Dict, Iterable, Iterator

from src.collector.parser import parse_raw_record


class Ns3Bridge:
	def iter_metrics(self, raw_stream: Iterable[Dict]) -> Iterator[Dict]:
		for raw in raw_stream:
			yield parse_raw_record(raw)

	def iter_metrics_from_jsonl(self, trace_file_path: str) -> Iterator[Dict]:
		with open(trace_file_path, "r", encoding="utf-8") as handle:
			for line in handle:
				line = line.strip()
				if not line:
					continue
				raw = json.loads(line)
				yield parse_raw_record(raw)
