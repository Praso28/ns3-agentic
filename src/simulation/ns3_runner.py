import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from src.simulation.fault_profiles import load_scenario_file


@dataclass(frozen=True)
class Ns3RuntimeConfig:
    command: str
    workdir: Optional[str] = None
    control_channel: Optional[str] = None


class Ns3Controller:
    def __init__(self, control_channel: str) -> None:
        self.control_channel = control_channel
        parent = os.path.dirname(control_channel)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _emit(self, action: str, target: str, payload: Optional[Dict] = None) -> None:
        record = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "payload": payload or {},
        }
        with open(self.control_channel, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    def restart_node(self, target: str) -> None:
        self._emit("restart_node", target)

    def reduce_load(self, factor: float = 0.30, target: str = "node-1") -> None:
        self._emit("reduce_load", target, payload={"factor": factor})


class Ns3Runner:
    def __init__(self, runtime: Ns3RuntimeConfig) -> None:
        self.runtime = runtime
        self.controller = Ns3Controller(runtime.control_channel) if runtime.control_channel else None

    @staticmethod
    def from_scenario(scenario_path: str, command_override: Optional[str] = None) -> "Ns3Runner":
        scenario = load_scenario_file(scenario_path)
        ns3_conf = scenario.get("ns3", {})

        command = command_override or ns3_conf.get("command")
        if not command:
            raise ValueError(
                "Real ns-3 mode requires command. Set scenario.ns3.command or pass --ns3-command."
            )

        runtime = Ns3RuntimeConfig(
            command=command,
            workdir=ns3_conf.get("workdir"),
            control_channel=ns3_conf.get("control_channel"),
        )
        return Ns3Runner(runtime=runtime)

    def iter_raw_metrics(self) -> Iterator[Dict]:
        proc = subprocess.Popen(
            shlex.split(self.runtime.command),
            cwd=self.runtime.workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            candidate = line
            if line.startswith("METRIC "):
                candidate = line[len("METRIC ") :]

            try:
                metric = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            yield metric

        return_code = proc.wait()
        if return_code != 0:
            stderr = proc.stderr.read() if proc.stderr is not None else ""
            raise RuntimeError(f"ns-3 process failed with code {return_code}: {stderr.strip()}")