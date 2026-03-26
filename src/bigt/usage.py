"""Claude Max plan usage meter – talks to bigt-usaged daemon, falls back to direct fetch."""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from colorama import Fore, Style


KEYCHAIN_SERVICE = "Claude Code-credentials"
API_URL = "https://api.anthropic.com/api/oauth/usage"
BETA_HEADER = "oauth-2025-04-20"

SOCK_PATH = Path.home() / ".cache" / "bigt" / "usage.sock"
PID_PATH = Path.home() / ".cache" / "bigt" / "usaged.pid"


def get_oauth_token():
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


# ---------------------------------------------------------------------------
# Daemon client
# ---------------------------------------------------------------------------

def _fetch_from_daemon():
    """Connect to usaged socket and get cached usage data. Returns dict or None."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(str(SOCK_PATH))
        sock.sendall(b'{"cmd": "get_usage"}\n')
        raw = sock.recv(65536).decode("utf-8", errors="ignore").strip()
        sock.close()
        resp = json.loads(raw)
        return resp.get("data")
    except Exception:
        return None


def _is_daemon_alive():
    """Check if usaged is running."""
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def _ensure_daemon():
    """Start usaged if it isn't running. Wait for socket to appear."""
    if _is_daemon_alive():
        # Already running – just wait for socket if it's not there yet
        for _ in range(15):
            if SOCK_PATH.exists():
                return
            time.sleep(0.2)
        return

    # Clean up stale files
    for p in (PID_PATH, SOCK_PATH):
        try:
            p.unlink()
        except OSError:
            pass

    # Spawn daemon
    subprocess.Popen(
        [sys.executable, "-m", "bigt.usaged"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for socket to appear (up to 3s)
    for _ in range(15):
        if SOCK_PATH.exists():
            return
        time.sleep(0.2)


# ---------------------------------------------------------------------------
# Direct fetch fallback (kept for resilience)
# ---------------------------------------------------------------------------

_direct_cache = {"data": None, "fetched_at": 0}
DIRECT_CACHE_TTL = 120


def _fetch_direct(token):
    """Fetch directly from API. Used as fallback when daemon is unavailable."""
    now = time.time()
    if _direct_cache["data"] and (now - _direct_cache["fetched_at"]) < DIRECT_CACHE_TTL:
        return _direct_cache["data"]

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
            if _direct_cache["data"]:
                return _direct_cache["data"]
            err = data["error"]
            return {"_error": f"{err.get('type', 'error')}: {err.get('message', 'Unknown')}"}
        _direct_cache["data"] = data
        _direct_cache["fetched_at"] = now
        return data
    except Exception:
        if _direct_cache["data"]:
            return _direct_cache["data"]
        return {}


# ---------------------------------------------------------------------------
# Public API (unchanged signatures)
# ---------------------------------------------------------------------------

def fetch_usage(token):
    """Get usage data: try daemon first, auto-start it, fall back to direct."""
    # 1. Try daemon
    data = _fetch_from_daemon()
    if data:
        return data

    # 2. Auto-start daemon and retry
    _ensure_daemon()
    data = _fetch_from_daemon()
    if data:
        return data

    # 3. Fallback to direct fetch
    return _fetch_direct(token)


def time_remaining(reset_at):
    """Format time remaining from ISO 8601 timestamp as H:MM."""
    if not reset_at or reset_at == "null":
        return "--"
    try:
        reset_dt = datetime.fromisoformat(reset_at)
        now = datetime.now(timezone.utc)
        diff = int((reset_dt - now).total_seconds())
        if diff <= 0:
            return "0:00"
        hours = diff // 3600
        mins = (diff % 3600) // 60
        return f"{hours}:{mins:02d}"
    except Exception:
        return "--"


def draw_bar(pct, width=15, scheme=None):
    """Return a colored progress bar string."""
    pct = int(pct)
    filled = pct * width // 100
    empty = width - filled

    if pct >= 80:
        color = Fore.RED
    elif pct >= 60:
        color = Fore.YELLOW
    elif scheme == "matrix":
        color = Fore.GREEN
    elif scheme == "ocean":
        color = Fore.CYAN
    elif scheme == "fire":
        color = Fore.RED
    elif scheme == "purple":
        color = Fore.MAGENTA
    else:
        color = Fore.BLUE

    bar = color + "█" * filled + Style.DIM + "░" * empty + Style.RESET_ALL
    return f"{bar} {pct:3d}%"


def render_usage_line(scheme=None):
    """Fetch usage and return a single formatted line for display."""
    token = get_oauth_token()
    if not token:
        return f"{Style.DIM}(Claude usage: not logged in){Style.RESET_ALL}"

    data = fetch_usage(token)
    if not data:
        return f"{Style.DIM}(Claude usage: fetch failed){Style.RESET_ALL}"
    if "_error" in data:
        return f"{Style.DIM}(Claude usage: {data['_error']}){Style.RESET_ALL}"

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    sonnet = data.get("seven_day_sonnet") or {}

    five_pct = five.get("utilization", 0) or 0
    seven_pct = seven.get("utilization", 0) or 0
    sonnet_pct = sonnet.get("utilization", 0) or 0

    five_reset = time_remaining(five.get("resets_at", ""))
    seven_reset = time_remaining(seven.get("resets_at", ""))
    sonnet_reset = time_remaining(sonnet.get("resets_at", ""))

    parts = [
        f"{Style.DIM}Sess{Style.RESET_ALL} {draw_bar(five_pct, scheme=scheme)} {Style.DIM}{five_reset}{Style.RESET_ALL}",
        f"{Style.DIM}Wkly{Style.RESET_ALL} {draw_bar(seven_pct, scheme=scheme)} {Style.DIM}{seven_reset}{Style.RESET_ALL}",
        f"{Style.DIM}Son{Style.RESET_ALL} {draw_bar(sonnet_pct, scheme=scheme)} {Style.DIM}{sonnet_reset}{Style.RESET_ALL}",
    ]
    return "  ".join(parts)


def render_usage_full(scheme=None):
    """Render a full multi-line usage display."""
    token = get_oauth_token()
    if not token:
        print(f"{Style.DIM}Not logged into Claude Code.{Style.RESET_ALL}")
        return

    data = fetch_usage(token)
    if not data:
        print(f"{Style.DIM}Could not fetch usage data.{Style.RESET_ALL}")
        return
    if "_error" in data:
        print(f"{Style.DIM}{data['_error']}{Style.RESET_ALL}")
        return

    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    sonnet = data.get("seven_day_sonnet") or {}
    extra = data.get("extra_usage") or {}

    # Theme-aware header color
    header_colors = {"matrix": Fore.GREEN, "fire": Fore.RED, "purple": Fore.MAGENTA, "ocean": Fore.CYAN}
    header_color = header_colors.get(scheme, Fore.CYAN)

    print()
    print(f"  {Style.BRIGHT}{header_color}Claude Max Usage{Style.RESET_ALL}")
    print()
    print(f"  Session (5hr)  {draw_bar(five.get('utilization', 0) or 0, 30, scheme=scheme)}  {Style.DIM}{time_remaining(five.get('resets_at', ''))}{Style.RESET_ALL}")
    print(f"  Weekly (all)   {draw_bar(seven.get('utilization', 0) or 0, 30, scheme=scheme)}  {Style.DIM}{time_remaining(seven.get('resets_at', ''))}{Style.RESET_ALL}")
    print(f"  Weekly (Son)   {draw_bar(sonnet.get('utilization', 0) or 0, 30, scheme=scheme)}  {Style.DIM}{time_remaining(sonnet.get('resets_at', ''))}{Style.RESET_ALL}")
    print()

    if extra.get("is_enabled"):
        limit = int(extra.get("monthly_limit", 0)) // 100
        used = int(extra.get("used_credits", 0))
        print(f"  {Style.DIM}Extra usage: ${used} / ${limit} monthly{Style.RESET_ALL}")
    print()
