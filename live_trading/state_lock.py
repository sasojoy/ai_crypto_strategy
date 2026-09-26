"""
Cross-process lock for live_v7_state.json (2026-09-26). Needed once
ws_entry_detector.py (long-running WebSocket daemon, opens new positions
the instant a real-time signal fires) and live_v7.py (still runs on its
existing 1-minute Task Scheduler poll, reconciling/closing positions) both
read-modify-write the same state file concurrently -- without a lock, an
interleaved write from one process could silently clobber the other's
update (e.g. the daemon appends a brand-new position at the same moment
the poller is writing back a state with that position already closed).

Plain, dependency-free implementation (no `fcntl` on Windows): a lock is a
sibling `<path>.lock` file, created with the OS-level exclusive-create flag
so only one process can succeed at a time; the loser retries with a short
sleep until it gets the lock or times out. Whoever holds a lock file
after a process died without releasing it (crash, kill, power loss) would
block everyone forever, so a lock older than STALE_SECONDS is treated as
abandoned and stolen.
"""
import os
import time

STALE_SECONDS = 30  # generous vs. how long a state read-modify-write should ever take


class StateLock:
    def __init__(self, path, timeout=15, poll_interval=0.2):
        self.lock_path = path + '.lock'
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._fd = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self._fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(self._fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(self.lock_path)
                    if age > STALE_SECONDS:
                        os.remove(self.lock_path)  # abandoned by a dead process -- steal it
                        continue
                except FileNotFoundError:
                    continue  # the other holder released it between our stat and remove -- retry immediately
                if time.time() >= deadline:
                    raise TimeoutError(f"Could not acquire {self.lock_path} within {self.timeout}s "
                                        f"-- another process is holding it unusually long.")
                time.sleep(self.poll_interval)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._fd is not None:
            os.close(self._fd)
            try:
                os.remove(self.lock_path)
            except FileNotFoundError:
                pass  # already gone (e.g. stolen as stale by someone else) -- fine, nothing to clean up
        return False


def state_lock(path, timeout=15):
    return StateLock(path, timeout=timeout)
