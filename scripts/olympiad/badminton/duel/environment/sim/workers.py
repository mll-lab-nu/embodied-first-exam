"""Per-seat worker processes of the badminton duel: the stroke planner and the renderer. No worker owns the shared
world; MuJoCo work never runs in the world thread's process."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from ipc import _Conn

HERE = Path(__file__).resolve().parent


def affinity(name, all_threads=False):
    value = os.environ.get(name, "")
    if value:
        cpus = set()
        for part in value.split(','):
            ends = part.split('-')
            cpus.update(range(int(ends[0]), int(ends[-1]) + 1))
        if all_threads:
            # Mesa can override the inherited mask when it creates native threads.
            for path in Path('/proc/self/task').iterdir():
                try: os.sched_setaffinity(int(path.name), cpus)
                except ProcessLookupError: pass
        else:
            os.sched_setaffinity(0, cpus)


class ProcessWorker:
    def __init__(self, kind, side, timeout=60):
        self.timeout = timeout
        self.lock = threading.Lock()
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), kind, side],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=HERE)
        self.conn = _Conn(self.proc.stdout, self.proc.stdin)
        try:
            if self.conn.recv(time.monotonic() + 120) != 'ready':
                raise RuntimeError('worker startup failed')
        except Exception:
            self.close()
            raise

    def call(self, payload):
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('one request per seat and worker may be in flight')
        try:
            deadline = time.monotonic() + self.timeout
            self.conn.send(payload, deadline)
            ok, value = self.conn.recv(deadline)
            if not ok:
                raise RuntimeError(value)
            return value
        except BlockingIOError:
            raise
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=1)
        self.proc.stdin.close(); self.proc.stdout.close()


def plan(model, job):
    """Advance an exact copy of the seat's robot from the queue step to the act's effect step with the command in
    force, then plan the act there (bduel.plan_on): the same result as planning in the world thread at that step."""
    import bduel
    side = bduel.restore(job['snap'], model)
    t0 = time.monotonic()
    while side.k < job['k_e']:
        side.solo_step()
    t1 = time.monotonic()
    key = side.state_key()
    res = bduel.plan_on(side, job['decision'])
    return dict(key=key, res=res, fork_s=t1-t0, plan_s=time.monotonic()-t1)


def main(kind, side):
    affinity(f'DUEL_{kind.upper()}_{side}_CPUS')
    import bduel
    import bm
    if kind == 'plan':
        model = bm.Phys().m
    elif kind == 'render':
        obj = bduel.Renderer(side)
        obj.views([bduel.World().snap()] * 4)   # create Mesa/LLVM threads before the ready handshake
    else:
        raise ValueError(kind)
    affinity(f'DUEL_{kind.upper()}_{side}_CPUS', all_threads=True)
    proto = os.fdopen(os.dup(1), 'wb')
    os.dup2(2, 1); sys.stdout = sys.stderr
    conn = _Conn(sys.stdin.buffer, proto)
    conn.send('ready')
    while True:
        try: job = conn.recv()
        except EOFError: return
        try:
            t0 = time.monotonic()
            if kind == 'plan':
                out = plan(model, job)
            else:
                out = dict(png=obj.views(job['snapshots']))
            out['worker_s'] = time.monotonic()-t0
            conn.send((True, out))
        except Exception as exc:
            import traceback; traceback.print_exc()
            conn.send((False, repr(exc)))


if __name__ == '__main__':
    main(*sys.argv[1:])
