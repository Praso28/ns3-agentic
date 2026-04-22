import json
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from src.simulation.fault_profiles import load_scenario_file

logger = logging.getLogger(__name__)

_CONTROL_CHANNEL_DEFAULT = "/tmp/ai5g-control.jsonl"


@dataclass(frozen=True)
class Ns3RuntimeConfig:
    command: str
    workdir: Optional[str] = None
    control_channel: Optional[str] = None


class Ns3Controller:
    """Writes JSONL control commands to the shared channel consumed by ai5g-metrics.cc."""

    def __init__(self, control_channel: str) -> None:
        self.control_channel = control_channel
        parent = os.path.dirname(control_channel)
        if parent:
            os.makedirs(parent, exist_ok=True)
        logger.info("ns3_controller: control_channel=%s", control_channel)

    def _emit(self, action: str, target: str, payload: Optional[Dict] = None) -> None:
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "payload": payload or {},
        }
        line = json.dumps(record)
        try:
            with open(self.control_channel, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            logger.info(
                "control_channel_emit action=%s target=%s payload=%s channel=%s",
                action, target, payload, self.control_channel,
            )
        except OSError as exc:
            logger.error("control_channel_emit_failed action=%s error=%s", action, exc)
            raise

    def restart_node(self, target: str) -> None:
        self._emit("restart_node", target)

    def reduce_load(self, factor: float = 0.30, target: str = "node-1") -> None:
        self._emit("reduce_load", target, payload={"factor": round(factor, 4)})


class Ns3Runner:
    """Manages the ns-3 subprocess and provides a metric iterator over its stdout."""

    def __init__(self, runtime: Ns3RuntimeConfig) -> None:
        self.runtime = runtime
        if runtime.control_channel:
            self.controller: Optional[Ns3Controller] = Ns3Controller(runtime.control_channel)
        else:
            self.controller = Ns3Controller(_CONTROL_CHANNEL_DEFAULT)
            logger.warning(
                "ns3_runner: no control_channel in config; defaulting to %s", _CONTROL_CHANNEL_DEFAULT
            )

    @staticmethod
    def from_scenario(scenario_path: str, command_override: Optional[str] = None) -> "Ns3Runner":
        scenario = load_scenario_file(scenario_path)
        ns3_conf = scenario.get("ns3", {})

        command = command_override or ns3_conf.get("command")
        if not command:
            raise ValueError(
                "Real ns-3 mode requires a command. Set scenario.ns3.command or pass --ns3-command."
            )

        runtime = Ns3RuntimeConfig(
            command=command,
            workdir=ns3_conf.get("workdir"),
            control_channel=ns3_conf.get("control_channel", _CONTROL_CHANNEL_DEFAULT),
        )
        logger.info(
            "ns3_runner: workdir=%s control_channel=%s command=%s",
            runtime.workdir, runtime.control_channel, command[:80],
        )
        return Ns3Runner(runtime=runtime)

    def iter_raw_metrics(self) -> Iterator[Dict]:
        """Spawn ns-3, stream its stdout as parsed JSON metric dicts."""
        logger.info("ns3_runner: starting subprocess command=%s", self.runtime.command[:120])
        proc = subprocess.Popen(
            shlex.split(self.runtime.command),
            cwd=self.runtime.workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        parsed_count = 0
        skip_count = 0

        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue

                candidate = line[len("METRIC "):] if line.startswith("METRIC ") else line

                try:
                    metric = json.loads(candidate)
                    parsed_count += 1
                    yield metric
                except json.JSONDecodeError:
                    skip_count += 1
                    logger.debug("ns3_runner: skipping non-JSON line: %s", line[:120])
        finally:
            return_code = proc.wait()
            logger.info(
                "ns3_runner: subprocess exited code=%d parsed=%d skipped=%d",
                return_code, parsed_count, skip_count,
            )
            if return_code != 0:
                stderr_text = proc.stderr.read().strip() if proc.stderr is not None else ""
                raise RuntimeError(
                    f"ns-3 process failed with code {return_code}: {stderr_text}"
                )