"""Run pdb under subprocess with stdin/stdout wired for a GUI (step/continue buttons)."""
import queue
import subprocess
import sys
import threading


class PdbPipeSession:
    """pdb with pipes; reader thread -> out_queue; send_cmd writes to stdin."""

    def __init__(self, script_path, cwd, out_queue):
        self.script_path = script_path
        self.cwd = cwd
        self.out_q = out_queue
        self.proc = None
        self._reader = None

    def start(self):
        kw = {}
        if sys.platform.startswith("win"):
            cf = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if cf:
                kw["creationflags"] = cf
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "pdb", self.script_path],
                cwd=self.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **kw,
            )
        except OSError as e:
            self.out_q.put(f"Could not start pdb: {e}\n")
            self.out_q.put(None)
            return False

        def reader():
            for line in iter(self.proc.stdout.readline, ""):
                self.out_q.put(line)
            self.out_q.put(None)

        self._reader = threading.Thread(target=reader, daemon=True)
        self._reader.start()
        return True

    def send(self, line: str):
        if not self.proc or not self.proc.stdin:
            return
        if not line.endswith("\n"):
            line += "\n"
        try:
            self.proc.stdin.write(line)
            self.proc.stdin.flush()
        except OSError:
            pass

    def close(self):
        if self.proc:
            try:
                self.proc.terminate()
            except Exception:
                pass
            self.proc = None
