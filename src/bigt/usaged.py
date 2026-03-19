"""bigt usage daemon – fetches Claude usage every 5 min, serves via Unix socket."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "bigt"
SOCK_PATH = CACHE_DIR / "usage.sock"
PID_PATH = CACHE_DIR / "usaged.pid"
LOG_PATH = Path(__file__).resolve().parent.parent.parent / "usaged.log"
FETCH_INTERVAL = 300  # 5 minutes
IDLE_TIMEOUT = 1800   # 30 minutes
BACKOFF_BASE = 60     # 1 minute base backoff
BACKOFF_MAX = 900     # 15 minute max backoff

# Reuse auth constants from usage module
KEYCHAIN_SERVICE = "Claude Code-credentials"
API_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"


def _get_oauth_token():
    """Read Claude Code OAuth token from macOS Keychain."""
    try:
        raw = subprocess.check_output(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        creds = json.loads(raw)
        return creds["claudeAiOauth"]["accessToken"]
    except Exception:
        return None


def _do_fetch(token):
    """Hit the Anthropic usage API. Returns (data_dict, None) or (None, error_string)."""
    try:
        result = subprocess.check_output(
            [
                "curl", "-s",
                "-H", f"Authorization: Bearer {token}",
                "-H", "Content-Type: application/json",
                "-H", f"anthropic-beta: {BETA_HEADER}",
                API_URL,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        data = json.loads(result)
        if "error" in data:
            err = data["error"]
            msg = f"{err.get('type', 'unknown')}: {err.get('message', 'no message')}"
            return None, msg
        return data, None
    except Exception as e:
        return None, str(e)


class UsageDaemon:
    def __init__(self, foreground=False):
        self.cached_data = None
        self.fetched_at = 0.0
        self.last_client_time = time.time()
        self.running = True
        self.foreground = foreground
        self.server_sock = None
        self.consecutive_failures = 0

    def log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        if self.foreground:
            print(f"[usaged] {msg}", file=sys.stderr, flush=True)
        try:
            with open(LOG_PATH, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def setup(self):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Clean up stale socket
        if SOCK_PATH.exists():
            try:
                SOCK_PATH.unlink()
            except OSError:
                pass

        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(str(SOCK_PATH))
        self.server_sock.listen(5)
        self.server_sock.settimeout(10.0)

        PID_PATH.write_text(str(os.getpid()))

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.log(f"listening on {SOCK_PATH} (pid {os.getpid()})")

    def _handle_signal(self, signum, frame):
        self.log(f"received signal {signum}, shutting down")
        self.running = False

    def _sleep(self, seconds):
        """Sleep in 1s chunks so we can exit promptly."""
        for _ in range(int(seconds)):
            if not self.running:
                return
            time.sleep(1)

    def fetch_loop(self):
        """Background thread: fetch usage data every FETCH_INTERVAL seconds."""
        while self.running:
            token = _get_oauth_token()
            if token:
                data, err = _do_fetch(token)
                if data:
                    self.cached_data = data
                    self.fetched_at = time.time()
                    self.consecutive_failures = 0
                    self.log("fetched usage data OK")
                else:
                    self.consecutive_failures += 1
                    self.log(f"fetch failed: {err}")
            else:
                self.consecutive_failures += 1
                self.log("no oauth token available")

            # On failure, use exponential backoff: 1m, 2m, 4m, 8m, capped at 15m
            if self.consecutive_failures > 0:
                backoff = min(BACKOFF_BASE * (2 ** (self.consecutive_failures - 1)), BACKOFF_MAX)
                self.log(f"backing off {int(backoff)}s (failure #{self.consecutive_failures})")
                self._sleep(backoff)
            else:
                self._sleep(FETCH_INTERVAL)

    def serve(self):
        """Main thread: accept client connections and serve cached data."""
        while self.running:
            try:
                conn, _ = self.server_sock.accept()
            except socket.timeout:
                # Check idle timeout
                if time.time() - self.last_client_time > IDLE_TIMEOUT:
                    self.log("idle timeout, shutting down")
                    self.running = False
                continue
            except OSError:
                break

            self.last_client_time = time.time()
            try:
                self.handle_client(conn)
            except Exception:
                pass
            finally:
                conn.close()

    def handle_client(self, conn):
        conn.settimeout(5.0)
        raw = conn.recv(4096).decode("utf-8", errors="ignore").strip()
        if not raw:
            return

        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            return

        if req.get("cmd") == "get_usage":
            resp = json.dumps({
                "data": self.cached_data,
                "fetched_at": self.fetched_at,
            }) + "\n"
            conn.sendall(resp.encode())
            self.log("served cached data to client")

    def cleanup(self):
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
        for p in (SOCK_PATH, PID_PATH):
            try:
                p.unlink()
            except OSError:
                pass
        self.log("cleaned up")

    def run(self):
        self.setup()
        fetch_thread = threading.Thread(target=self.fetch_loop, daemon=True)
        fetch_thread.start()
        try:
            self.serve()
        finally:
            self.running = False
            fetch_thread.join(timeout=5)
            self.cleanup()


def _daemonize():
    """Double-fork to fully detach from the calling process."""
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    # Redirect std streams
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)


def _is_daemon_alive():
    """Check if a daemon is already running via PID file."""
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        # Stale PID file – clean up
        for p in (PID_PATH, SOCK_PATH):
            try:
                p.unlink()
            except OSError:
                pass
        return False


def main():
    parser = argparse.ArgumentParser(prog="bigt-usaged", description="bigt usage daemon")
    parser.add_argument("--foreground", action="store_true", help="Run in foreground (for debugging)")
    parser.add_argument("--stop", action="store_true", help="Stop a running daemon")
    args = parser.parse_args()

    if args.stop:
        if PID_PATH.exists():
            try:
                pid = int(PID_PATH.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"Sent SIGTERM to daemon (pid {pid})")
            except (ValueError, OSError) as e:
                print(f"Could not stop daemon: {e}")
        else:
            print("No daemon running")
        return

    if _is_daemon_alive():
        if args.foreground:
            print("Daemon already running", file=sys.stderr)
        sys.exit(0)

    if not args.foreground:
        _daemonize()

    daemon = UsageDaemon(foreground=args.foreground)
    daemon.run()


if __name__ == "__main__":
    main()
