"""Monitor host memory/CPU and stop owned workers at the memory limit."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def run_guarded(command, output, *, cwd, env, memory_limit_percent=90.):
    import psutil
    output = Path(output)
    peak_memory = peak_cpu = 0.
    def sample():
        nonlocal peak_memory, peak_cpu
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=.2)
        peak_memory, peak_cpu = max(peak_memory, mem.percent), max(peak_cpu, cpu)
        return dict(time=time.time(), memory_percent=mem.percent, available_bytes=mem.available,
                    cpu_percent=cpu)
    def exceeded(row):
        # AGENTS.md 2026-09-30: CPU is diagnostic only; memory is the stop gate.
        return row["memory_percent"] >= memory_limit_percent
    initial = sample()
    if exceeded(initial):
        (output/"resource_pause.json").write_text(json.dumps(initial, indent=2)+"\n")
        return 90
    with (output/"runtime.log").open("x") as log, (output/"resource_usage.jsonl").open("x") as usage:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                row = sample()
                usage.write(json.dumps(row)+"\n")
                usage.flush()
                if exceeded(row):
                    (output/"resource_pause.json").write_text(json.dumps(row, indent=2)+"\n")
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    return 90
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            return process.returncode
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            (output/"resource_summary.json").write_text(json.dumps(dict(
                peak_memory_percent=peak_memory, peak_cpu_percent=peak_cpu,
                worker_exit_code=process.returncode), indent=2)+"\n")
