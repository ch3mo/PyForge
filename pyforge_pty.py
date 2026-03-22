"""Interactive shell: pywinpty on Windows; pty + subprocess on Unix (no fork in Tk thread)."""
import os
import subprocess
import sys
import threading


class PtySession:
    """Background reader posts decoded text to out_queue (ends with None). write() sends to shell."""

    def __init__(self, cwd, out_queue, cols=120, rows=32):
        self.cwd = cwd or os.getcwd()
        self.out_q = out_queue
        self.cols = cols
        self.rows = rows
        self._win_proc = None
        self._unix_master = None
        self._unix_pid = None
        self._subproc = None
        self._alive = threading.Event()
        self._alive.set()

    def start(self):
        if sys.platform == "win32":
            return self._start_win()
        return self._start_unix()

    def _start_win(self):
        try:
            from pywinpty import PtyProcess
        except ImportError as e:
            self.out_q.put(f"[Install pywinpty for an embedded shell: pip install pywinpty]\n{e}\n")
            self.out_q.put(None)
            return False
        env = os.environ.copy()
        try:
            self._win_proc = PtyProcess.spawn(
                r"C:\Windows\System32\cmd.exe",
                cwd=self.cwd,
                env=env,
                dimensions=(self.rows, self.cols),
            )
        except Exception as e:
            self.out_q.put(f"[pywinpty: {e}]\n")
            self.out_q.put(None)
            return False
        threading.Thread(target=self._read_win, daemon=True).start()
        return True

    def _read_win(self):
        while self._alive.is_set() and self._win_proc:
            try:
                chunk = self._win_proc.read(4096)
                if not chunk:
                    break
                self.out_q.put(chunk.decode("utf-8", errors="replace"))
            except Exception:
                break
        self.out_q.put(None)

    def _start_unix(self):
        import pty

        master_fd, slave_fd = pty.openpty()
        try:
            self._subproc = subprocess.Popen(
                ["/bin/bash", "-l"],
                cwd=self.cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                close_fds=True,
            )
        except (OSError, FileNotFoundError) as e:
            try:
                os.close(master_fd)
            except OSError:
                pass
            self.out_q.put(f"[shell: {e}]\n")
            self.out_q.put(None)
            return False
        os.close(slave_fd)
        self._unix_master = master_fd
        threading.Thread(target=self._read_unix, daemon=True).start()
        return True

    def _read_unix(self):
        while self._alive.is_set() and self._unix_master is not None:
            try:
                data = os.read(self._unix_master, 4096)
                if not data:
                    break
                self.out_q.put(data.decode("utf-8", errors="replace"))
            except OSError:
                break
        self.out_q.put(None)

    def write(self, data: str):
        if not data:
            return
        b = data.replace("\n", "\r\n") if sys.platform == "win32" else data
        if sys.platform == "win32" and self._win_proc:
            try:
                self._win_proc.write(b.encode("utf-8", errors="replace"))
            except Exception:
                pass
        elif self._unix_master is not None:
            try:
                os.write(self._unix_master, b.encode("utf-8", errors="replace"))
            except OSError:
                pass

    def resize(self, cols, rows):
        if sys.platform == "win32" and self._win_proc:
            try:
                self._win_proc.setwinsize(rows, cols)
            except Exception:
                pass

    def close(self):
        self._alive.clear()
        if sys.platform == "win32" and self._win_proc:
            try:
                self._win_proc.close()
            except Exception:
                pass
            self._win_proc = None
        if self._subproc:
            try:
                self._subproc.terminate()
            except Exception:
                pass
            self._subproc = None
        if self._unix_master is not None:
            try:
                os.close(self._unix_master)
            except OSError:
                pass
            self._unix_master = None
