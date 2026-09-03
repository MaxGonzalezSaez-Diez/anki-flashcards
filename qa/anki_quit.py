import subprocess
import time

def quit_anki(
    *,
    graceful_wait_s: float = 25.0,
    poll_interval_s: float = 0.35,
) -> None:
    def pids():
        result = subprocess.run(
            ["pgrep", "-f", "aqt.run"],
            capture_output=True,
            text=True
        )
        out = result.stdout.strip()
        return [int(x) for x in out.split()] if out else []

    # Step 1: check if running
    running = pids()
    if not running:
        return

    # Step 2: graceful shutdown (SIGTERM)
    for pid in running:
        try:
            subprocess.run(["kill", str(pid)])
        except Exception:
            pass

    # Step 3: wait for graceful exit
    start = time.time()
    while time.time() - start < graceful_wait_s:
        if not pids():
            return
        time.sleep(poll_interval_s)

    # Step 5: force kill remaining processes
    running = pids()
    for pid in running:
        try:
            subprocess.run(["kill", "-9", str(pid)])
        except Exception:
            pass