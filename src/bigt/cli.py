"""BigT - Big terminal banners for workspace identification."""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import termios
import tty
from pathlib import Path

import pyfiglet
from colorama import Fore, Style, init

init()

CONFIG_PATH = Path.home() / ".bigt" / "config.json"


def load_config():
    """Load user config from ~/.bigt/config.json."""
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_config(config):
    """Save user config to ~/.bigt/config.json."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")

# Color map for --color flag
COLORS = {
    "red": Fore.RED,
    "green": Fore.GREEN,
    "yellow": Fore.YELLOW,
    "blue": Fore.BLUE,
    "magenta": Fore.MAGENTA,
    "cyan": Fore.CYAN,
    "white": Fore.WHITE,
}

# Curated fonts for the interactive picker
PICKER_FONTS = [
    "slant", "big", "standard", "doom", "block",
    "banner3", "banner3-D", "banner", "banner4",
    "larry3d", "starwars", "epic", "ogre",
    "poison", "graffiti", "impossible",
    "small", "smslant", "digital",
]


def _render_simple(text, font, color="cyan"):
    """Render figlet text with color, no scaling or fitting. Returns list of lines."""
    ansi_color = COLORS.get(color, Fore.CYAN)
    try:
        rendered = pyfiglet.figlet_format(text, font=font)
    except pyfiglet.FontNotFound:
        rendered = pyfiglet.figlet_format(text, font="standard")
    lines = rendered.rstrip("\n").split("\n")
    return ["%s%s%s" % (ansi_color, line, Style.RESET_ALL) for line in lines]


def _center_block(lines, target_w, target_h):
    """Center a block of lines within target_w x target_h, trimming if needed."""
    # Trim height if too tall
    if len(lines) > target_h:
        lines = lines[:target_h]

    # Center vertically
    if len(lines) < target_h:
        pad_top = (target_h - len(lines)) // 2
        pad_bottom = target_h - len(lines) - pad_top
        lines = [""] * pad_top + lines + [""] * pad_bottom

    return lines


def _read_key():
    """Read a single keypress, handling arrow key escape sequences."""
    fd = sys.stdin.fileno()
    ch = os.read(fd, 1)
    if ch == b"\x1b":
        seq = os.read(fd, 2)
        if seq == b"[A":
            return "up"
        elif seq == b"[B":
            return "down"
        elif seq == b"[C":
            return "right"
        elif seq == b"[D":
            return "left"
        return "esc"
    elif ch in (b"\r", b"\n"):
        return "enter"
    elif ch == b"q" or ch == b"Q":
        return "quit"
    return ch.decode("utf-8", errors="ignore")


def run_font_picker(text, color):
    """Interactive font picker: up/down to browse, enter to select."""
    cols, rows = shutil.get_terminal_size()

    available = pyfiglet.FigletFont.getFonts()
    fonts = []
    seen = set()
    for f in PICKER_FONTS:
        if f in available and f not in seen:
            seen.add(f)
            fonts.append(f)
    if not fonts:
        fonts = sorted(available)[:20]

    idx = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    sys.stdout.write("\033[?25l")
    sys.stdout.write("\033[?1049h")
    sys.stdout.flush()

    try:
        tty.setraw(fd)

        while True:
            current_font = fonts[idx]

            # Just render the font naturally
            banner_lines = _render_simple(text, current_font, color)

            # Center in available space (leave 2 rows for status)
            display = _center_block(banner_lines, cols, rows - 2)

            sys.stdout.write("\033[2J\033[H")
            for line in display:
                sys.stdout.write(line + "\r\n")

            # Status line at bottom
            sep = "─" * max(0, cols - 55)
            status = (
                "%s─── %s%s%s%s%s (%d/%d) "
                "│ ↑↓ browse │ Enter = select │ q = quit %s%s"
            ) % (
                Style.DIM, Style.RESET_ALL,
                Fore.YELLOW, current_font, Style.RESET_ALL,
                Style.DIM, idx + 1, len(fonts),
                sep, Style.RESET_ALL,
            )
            sys.stdout.write(status)
            sys.stdout.flush()

            key = _read_key()
            if key in ("up", "left"):
                idx = (idx - 1) % len(fonts)
            elif key in ("down", "right"):
                idx = (idx + 1) % len(fonts)
            elif key == "enter":
                selected = fonts[idx]
                break
            elif key in ("quit", "esc"):
                selected = None
                break

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\033[?1049l")
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    return selected


def run_persistent_synthwave(text, color, shell, scheme="synthwave", scale=1):
    """Run with synthwave text at top and interactive shell below."""
    cols, rows = shutil.get_terminal_size()

    # Render using block character font
    lines = render_block_text(text, scale=scale)

    # Determine colors
    if scheme == "random":
        colors_to_use = get_random_scheme()
    elif scheme in COLOR_SCHEMES:
        colors_to_use = COLOR_SCHEMES[scheme]
    else:
        colors_to_use = COLOR_SCHEMES["synthwave"]

    # Color the text with alternating colors
    colored_lines = []
    for i, line in enumerate(lines):
        color_choice = colors_to_use[i % len(colors_to_use)]
        colored_lines.append(f"{color_choice}{line}{Style.RESET_ALL}")

    banner_height = len(colored_lines) + 2  # +2 for top/bottom borders

    if banner_height >= rows - 3:
        print("Terminal too small for persistent mode.", file=sys.stderr)
        sys.exit(1)

    dim = Style.DIM
    max_width = max(len(line) for line in lines) if lines else 40
    sep = "─" * cols

    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J")
    sys.stdout.write("\033[H")

    # Print banner (compact)
    border_color = Fore.GREEN if scheme == "matrix" else Fore.MAGENTA
    print(f"{border_color}╔{'═' * (max_width + 2)}╗")
    for line in colored_lines:
        print(f"{border_color}║{Fore.RESET} {line} {border_color}║{Fore.RESET}")
    print(f"{border_color}╚{'═' * (max_width + 2)}╝")

    sys.stdout.write("%s%s%s\n" % (dim, sep, Style.RESET_ALL))

    shell_top = banner_height + 1
    sys.stdout.write("\033[%d;%dr" % (shell_top, rows))
    sys.stdout.write("\033[%d;1H" % shell_top)
    sys.stdout.flush()

    shell_cmd = shell or os.environ.get("SHELL", "/bin/zsh")
    try:
        proc = subprocess.Popen([shell_cmd, "-i"])

        def _handle_sigwinch(signum, frame):
            if proc.poll() is None:
                proc.send_signal(signal.SIGWINCH)

        signal.signal(signal.SIGWINCH, _handle_sigwinch)
        proc.wait()
    finally:
        sys.stdout.write("\033[r")
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()


def run_persistent(text, font, color, height, shell):
    """Run with a fixed banner at the top and an interactive shell below."""
    cols, rows = shutil.get_terminal_size()

    if height is None:
        height = rows // 2

    # Render banner at natural size
    banner_lines = _render_simple(text, font, color)

    # If banner is shorter than requested height, center it
    if len(banner_lines) < height:
        banner_lines = _center_block(banner_lines, cols, height)
    elif len(banner_lines) > height:
        banner_lines = banner_lines[:height]

    banner_height = len(banner_lines) + 1  # +1 for separator

    if banner_height >= rows - 3:
        print("Terminal too small for persistent mode.", file=sys.stderr)
        sys.exit(1)

    dim = Style.DIM
    sep = "─" * cols

    sys.stdout.write("\033[?1049h")
    sys.stdout.write("\033[2J")
    sys.stdout.write("\033[H")

    for line in banner_lines:
        sys.stdout.write(line + "\n")

    sys.stdout.write("%s%s%s\n" % (dim, sep, Style.RESET_ALL))

    shell_top = banner_height + 1
    sys.stdout.write("\033[%d;%dr" % (shell_top, rows))
    sys.stdout.write("\033[%d;1H" % shell_top)
    sys.stdout.flush()

    shell_cmd = shell or os.environ.get("SHELL", "/bin/zsh")
    try:
        proc = subprocess.Popen([shell_cmd, "-i"])

        def _handle_sigwinch(signum, frame):
            if proc.poll() is None:
                proc.send_signal(signal.SIGWINCH)

        signal.signal(signal.SIGWINCH, _handle_sigwinch)
        proc.wait()
    finally:
        sys.stdout.write("\033[r")
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()


# Color schemes for synthwave rendering
COLOR_SCHEMES = {
    "synthwave": [Fore.CYAN, Fore.LIGHTBLUE_EX, Fore.BLUE, Fore.LIGHTMAGENTA_EX, Fore.MAGENTA, Fore.LIGHTMAGENTA_EX],
    "cyberpunk": [Fore.LIGHTCYAN_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTRED_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX],
    "ocean": [Fore.BLUE, Fore.LIGHTBLUE_EX, Fore.CYAN, Fore.LIGHTCYAN_EX, Fore.LIGHTBLUE_EX, Fore.BLUE],
    "fire": [Fore.RED, Fore.LIGHTRED_EX, Fore.LIGHTYELLOW_EX, Fore.YELLOW, Fore.LIGHTRED_EX, Fore.RED],
    "forest": [Fore.GREEN, Fore.LIGHTGREEN_EX, Fore.GREEN, Fore.LIGHTGREEN_EX, Fore.GREEN, Fore.LIGHTGREEN_EX],
    "pastel": [Fore.LIGHTCYAN_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTCYAN_EX, Fore.LIGHTGREEN_EX],
    "purple": [Fore.MAGENTA, Fore.LIGHTMAGENTA_EX, Fore.MAGENTA, Fore.LIGHTMAGENTA_EX, Fore.MAGENTA, Fore.LIGHTMAGENTA_EX],
    "matrix": ["\033[38;5;22m", "\033[38;5;28m", "\033[38;5;34m", "\033[38;5;40m", "\033[38;5;46m", "\033[38;5;82m"],
}

import random as random_module

def get_random_scheme():
    """Generate a random color scheme."""
    colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN,
              Fore.LIGHTRED_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX,
              Fore.LIGHTBLUE_EX, Fore.LIGHTMAGENTA_EX, Fore.LIGHTCYAN_EX]
    return [random_module.choice(colors) for _ in range(6)]


# Custom block character font (6 rows per glyph)
BLOCK_FONT = {
    'A': [' █████╗ ', '██╔══██╗', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'],
    'B': ['██████╗ ', '██╔══██╗', '██████╔╝', '██╔══██╗', '██████╔╝', '╚═════╝ '],
    'C': [' ██████╗', '██╔════╝', '██║     ', '██║     ', '╚██████╗', ' ╚═════╝'],
    'D': ['██████╗ ', '██╔══██╗', '██║  ██║', '██║  ██║', '██████╔╝', '╚═════╝ '],
    'E': ['███████╗', '██╔════╝', '█████╗  ', '██╔══╝  ', '███████╗', '╚══════╝'],
    'F': ['███████╗', '██╔════╝', '█████╗  ', '██╔══╝  ', '██║     ', '╚═╝     '],
    'G': [' ██████╗ ', '██╔════╝ ', '██║  ███╗', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '],
    'H': ['██╗  ██╗', '██║  ██║', '███████║', '██╔══██║', '██║  ██║', '╚═╝  ╚═╝'],
    'I': ['██╗', '██║', '██║', '██║', '██║', '╚═╝'],
    'J': ['    ██╗', '    ██║', '    ██║', '██╗ ██║', '╚████╔╝', ' ╚═══╝ '],
    'K': ['██╗  ██╗', '██║ ██╔╝', '█████╔╝ ', '██╔═██╗ ', '██║  ██╗', '╚═╝  ╚═╝'],
    'L': ['██╗     ', '██║     ', '██║     ', '██║     ', '███████╗', '╚══════╝'],
    'M': ['███╗   ███╗', '████╗ ████║', '██╔████╔██║', '██║╚██╔╝██║', '██║ ╚═╝ ██║', '╚═╝     ╚═╝'],
    'N': ['███╗   ██╗', '████╗  ██║', '██╔██╗ ██║', '██║╚██╗██║', '██║ ╚████║', '╚═╝  ╚═══╝'],
    'O': [' ██████╗ ', '██╔═══██╗', '██║   ██║', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '],
    'P': ['██████╗ ', '██╔══██╗', '██████╔╝', '██╔═══╝ ', '██║     ', '╚═╝     '],
    'Q': [' ██████╗ ', '██╔═══██╗', '██║   ██║', '██║▄▄ ██║', '╚██████╔╝', ' ╚══▀▀═╝ '],
    'R': ['██████╗  ', '██╔══██╗ ', '██████╔╝ ', '██╔══██╗ ', '██║  ╚██╗', '╚═╝   ╚═╝'],
    'S': ['███████╗', '██╔════╝', '███████╗', '╚════██║', '███████║', '╚══════╝'],
    'T': ['████████╗', '╚══██╔══╝', '   ██║   ', '   ██║   ', '   ██║   ', '   ╚═╝   '],
    'U': ['██╗   ██╗', '██║   ██║', '██║   ██║', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '],
    'V': ['██╗   ██╗', '██║   ██║', '╚██╗ ██╔╝', ' ╚████╔╝ ', '  ╚██╔╝  ', '   ╚═╝   '],
    'W': ['██╗    ██╗', '██║    ██║', '██║ █╗ ██║', '██║███╗██║', '╚███╔███╔╝', ' ╚══╝╚══╝ '],
    'X': ['██╗   ██╗', '╚██╗ ██╔╝', ' ╚████╔╝ ', ' ██╔═██╗ ', '██╔╝ ╚██╗', '╚═╝   ╚═╝'],
    'Y': ['██╗   ██╗', '╚██╗ ██╔╝', ' ╚████╔╝ ', '  ╚██╔╝  ', '   ██║   ', '   ╚═╝   '],
    'Z': ['███████╗', '╚════██║', '  ███╔╝ ', ' ██╔══╝ ', '███████╗', '╚══════╝'],
    ' ': ['    ', '    ', '    ', '    ', '    ', '    '],
    '0': [' ██████╗ ', '██╔═══██╗', '██║   ██║', '██║   ██║', '╚██████╔╝', ' ╚═════╝ '],
    '1': [' ██╗', '███║', '╚██║', ' ██║', ' ██║', ' ╚═╝'],
    '2': ['██████╗ ', '╚════██╗', ' █████╔╝', '██╔═══╝ ', '███████╗', '╚══════╝'],
    '3': ['██████╗ ', '╚════██╗', ' █████╔╝', '╚════██╗', '██████╔╝', '╚═════╝ '],
    '4': ['██╗  ██╗', '██║  ██║', '███████║', '╚════██║', '     ██║', '     ╚═╝'],
    '5': ['███████╗', '██╔════╝', '███████╗', '╚════██║', '███████║', '╚══════╝'],
    '6': [' ██████╗ ', '██╔════╝ ', '███████╗ ', '██╔═══██╗', '╚██████╔╝', ' ╚═════╝ '],
    '7': ['███████╗', '╚════██║', '    ██╔╝', '   ██╔╝ ', '  ██╔╝  ', '  ╚═╝   '],
    '8': [' ██████╗ ', '██╔═══██╗', '╚██████╔╝', '██╔═══██╗', '╚██████╔╝', ' ╚═════╝ '],
    '9': [' ██████╗ ', '██╔═══██╗', '╚███████║', ' ╚════██║', ' ██████╔╝', ' ╚═════╝ '],
}


def render_block_text(text, scale=1):
    """Render text using custom block character font. Returns list of lines.

    Args:
        text: Text to render
        scale: Size tier (1=small/6 rows, 2=medium/8 rows, 3=large/10 rows)
    """
    scale = max(1, min(scale, 3))  # Clamp between 1-3
    text = text.upper()
    chars = [BLOCK_FONT.get(c, BLOCK_FONT[' ']) for c in text]

    base_height = 6  # 6 rows per glyph
    lines = [''] * base_height
    for char_blocks in chars:
        for i, line in enumerate(char_blocks):
            lines[i] += line + ' '

    # Scale using nearest-neighbor to target heights: 6, 8, or 10
    target_heights = {1: 6, 2: 8, 3: 10}
    target = target_heights[scale]

    if target != base_height:
        scaled_lines = []
        for i in range(target):
            src = int(i * base_height / target)
            scaled_lines.append(lines[src])
        return [line.rstrip() for line in scaled_lines]

    return [line.rstrip() for line in lines]


def display_synthwave_text(text, color="cyan", scheme="synthwave", scale=1):
    """Render text in synthwave solid-block style with border.

    Args:
        text: Text to display
        color: Single color override (overrides scheme)
        scheme: Color scheme name (synthwave, cyberpunk, ocean, fire, forest, pastel, purple, matrix, random)
        scale: Height scale factor (1-3)
    """
    # Render using block character font
    lines = render_block_text(text, scale=scale)

    # Determine colors
    if scheme == "random":
        colors_to_use = get_random_scheme()
    elif scheme in COLOR_SCHEMES:
        colors_to_use = COLOR_SCHEMES[scheme]
    else:
        colors_to_use = COLOR_SCHEMES["synthwave"]

    # Color the text with alternating colors
    colored_lines = []
    for i, line in enumerate(lines):
        color_choice = colors_to_use[i % len(colors_to_use)]
        colored_lines.append(f"{color_choice}{line}{Style.RESET_ALL}")

    # Calculate width for border
    max_width = max(len(line) for line in lines) if lines else 40

    # Print with border (compact - no empty padding rows)
    border_color = Fore.GREEN if scheme == "matrix" else Fore.MAGENTA
    print(f"{border_color}╔{'═' * (max_width + 2)}╗")
    for line in colored_lines:
        print(f"{border_color}║{Fore.RESET} {line} {border_color}║{Fore.RESET}")
    print(f"{border_color}╚{'═' * (max_width + 2)}╝")


def display_bigt_banner():
    """Display the synthwave-style BIGT banner with solid letters."""
    print(f"{Fore.MAGENTA}╔══════════════════════════════════════════════════════════════════╗")
    print(f"{Fore.MAGENTA}║{Fore.RESET}                                                                  {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.CYAN}    ██████╗ ██╗ ██████╗ ████████╗                             {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.LIGHTBLUE_EX}    ██╔══██╗██║██╔════╝ ╚══██╔══╝                             {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.BLUE}    ██████╔╝██║██║  ███╗   ██║                                {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.LIGHTBLUE_EX}    ██╔══██╗██║██║   ██║   ██║                                {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.CYAN}    ██████╔╝██║╚██████╔╝   ██║                                {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.BLUE}    ╚═════╝ ╚═╝ ╚═════╝    ╚═╝                                {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.RESET}                                                                  {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.LIGHTMAGENTA_EX}              BIG Terminal Banners for Workspace                {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}║{Fore.LIGHTMAGENTA_EX}                    Synthwave Aesthetic Edition                  {Fore.MAGENTA}║")
    print(f"{Fore.MAGENTA}╚══════════════════════════════════════════════════════════════════╝")
    print()


def show_all_themes():
    """Display all available color themes with samples."""
    sample_text = "THEMES"

    print(f"{Fore.WHITE}Available Color Themes:{Style.RESET_ALL}\n")

    for theme_name in COLOR_SCHEMES.keys():
        print(f"{Fore.WHITE}─ {theme_name.upper()}{Style.RESET_ALL}")
        lines = render_block_text(sample_text, scale=1)
        colors_to_use = COLOR_SCHEMES[theme_name]

        for i, line in enumerate(lines):
            color_choice = colors_to_use[i % len(colors_to_use)]
            print(f"  {color_choice}{line}{Style.RESET_ALL}")
        print()


def list_fonts():
    """Print available figlet fonts."""
    fonts = sorted(pyfiglet.FigletFont.getFonts())
    print("Available fonts (%d):\n" % len(fonts))
    for f in fonts:
        print("  %s" % f)


def run_tmux_top_pane(text, scheme, scale, refresh):
    """Render banner + usage in a loop (meant for tmux top pane)."""
    import time
    from .usage import render_usage_line

    # Target height: text rows + 2 borders + 2 info lines
    target_height = {1: 11, 2: 13, 3: 15}.get(scale, 11)

    # Track whether we need to re-render (on SIGWINCH or timer)
    needs_render = [True]

    def _handle_resize(signum, frame):
        needs_render[0] = True

    signal.signal(signal.SIGWINCH, _handle_resize)

    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

    def render():
        # Resize pane to target height
        subprocess.run(
            ["tmux", "resize-pane", "-t", "0", "-y", str(target_height)],
            capture_output=True,
        )
        sys.stdout.write("\033[2J\033[H")  # Clear pane
        display_synthwave_text(text, scheme=scheme, scale=scale)
        home = os.path.expanduser("~")
        cwd = os.getcwd()
        smart_cwd = cwd.replace(home, "~", 1) if cwd.startswith(home) else cwd
        print(f"  {render_usage_line(scheme=scheme)}")
        print(f"  {Style.DIM}{time.strftime('%H:%M:%S')}  {smart_cwd}{Style.RESET_ALL}")
        sys.stdout.flush()

    try:
        last_render = 0
        while True:
            now = time.time()
            if needs_render[0] or (now - last_render >= refresh):
                render()
                needs_render[0] = False
                last_render = now
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def launch_tmux(text, scheme, scale, refresh, project_path):
    """Launch a tmux session with banner+usage top pane and shell bottom."""
    project_path = os.path.abspath(project_path)
    # tmux session names can't have periods — replace with underscores
    safe_name = text.lower().replace(' ', '-').replace('.', '_')
    session_name = f"bigt-{safe_name}"

    if not shutil.which("tmux"):
        print("Error: tmux is required. Install with: brew install tmux", file=sys.stderr)
        sys.exit(1)

    # Kill existing session
    subprocess.run(["tmux", "kill-session", "-t", session_name],
                   capture_output=True)

    # Build the top pane command - re-invoke bigt with --_tmux-top (internal flag)
    bigt_cmd = sys.argv[0]
    top_cmd = (
        f"{bigt_cmd} {text} -s {scheme} --refresh {refresh} --_tmux-top"
    )

    # Determine top pane height based on scale: text rows + 2 borders + 2 info lines
    top_height = {1: 10, 2: 12, 3: 14}.get(scale, 10)

    # Create session with top pane running the banner loop
    subprocess.run([
        "tmux", "new-session", "-d", "-s", session_name,
        "-c", project_path,
        top_cmd,
    ])

    # Split: bottom pane gets the shell
    subprocess.run([
        "tmux", "split-window", "-v", "-t", session_name,
        "-c", project_path,
    ])

    # Select bottom pane
    subprocess.run(["tmux", "select-pane", "-t", f"{session_name}:0.1"])

    # Session options
    subprocess.run(["tmux", "set-option", "-t", session_name, "mouse", "on"],
                   capture_output=True)
    tmux_fg_colors = {"matrix": "green", "fire": "red", "purple": "magenta", "ocean": "cyan", "forest": "green"}
    tmux_fg = tmux_fg_colors.get(scheme, "cyan")
    subprocess.run(["tmux", "set-option", "-t", session_name, "status-style", f"bg=black,fg={tmux_fg}"],
                   capture_output=True)
    subprocess.run(["tmux", "set-option", "-t", session_name, "status-left", f" {text} "],
                   capture_output=True)
    subprocess.run(["tmux", "set-option", "-t", session_name, "status-right", " %H:%M "],
                   capture_output=True)

    # Attach
    os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])


def main():
    parser = argparse.ArgumentParser(
        prog="bigt",
        description="Display big ASCII art banners in synthwave style. Persists with shell by default.",
        add_help=False,
    )
    parser.add_argument("text", nargs="*", default=["BigT"], help="Text to display (default: BigT). Use + for size 2, ++ for size 3")
    parser.add_argument("-c", "--color", default="cyan", choices=COLORS.keys(), help="Text color (default: cyan)")
    parser.add_argument("-s", "--scheme", default=None,
                       choices=["synthwave", "cyberpunk", "ocean", "fire", "forest", "pastel", "purple", "matrix", "random"],
                       help="Color scheme (default from ~/.bigt/config.json)")
    parser.add_argument("--set-default", default=None,
                       choices=["synthwave", "cyberpunk", "ocean", "fire", "forest", "pastel", "purple", "matrix"],
                       help="Set default color scheme in ~/.bigt/config.json")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive font picker (old figlet style)")
    parser.add_argument("--no-persist", action="store_true", help="Just print the banner and exit")
    parser.add_argument("--shell", default=None, help="Shell to use in persist mode (default: $SHELL)")
    parser.add_argument("-f", "--font", default=None, help="Use classic figlet font instead of synthwave block style")
    parser.add_argument("--themes", action="store_true", help="Show all available color themes")
    parser.add_argument("--list-fonts", action="store_true", help="List available figlet fonts")
    parser.add_argument("--tmux", nargs="?", const=".", metavar="PATH",
                       help="Launch tmux session at PATH (default: cwd). This is the default mode.")
    parser.add_argument("--no-tmux", action="store_true", help="Disable tmux, use legacy persistent shell mode")
    parser.add_argument("--usage", action="store_true", help="Show Claude Max plan usage")
    parser.add_argument("--refresh", type=int, default=120, help="Refresh interval for tmux top pane (default: 120s)")
    parser.add_argument("--_tmux-top", dest="tmux_top", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--help", action="help", help="Show this help message and exit")

    args = parser.parse_args()

    # Load config for defaults
    config = load_config()
    config_scheme = config.get("scheme", "synthwave")

    if args.set_default:
        config["scheme"] = args.set_default
        save_config(config)
        print(f"Default scheme set to: {args.set_default}")
        print(f"Config saved to: {CONFIG_PATH}")
        return

    if args.usage:
        from .usage import render_usage_full
        scheme = args.scheme if args.scheme else config_scheme
        render_usage_full(scheme=scheme)
        return

    if args.themes:
        show_all_themes()
        return

    if args.list_fonts:
        list_fonts()
        return

    # Parse text and extract size modifier
    text_parts = args.text
    scale = 1  # Default size
    scheme = args.scheme if args.scheme else config_scheme

    # Check if last element is a size modifier (+ or ++)
    if text_parts and len(text_parts[-1]) > 0 and all(c == '+' for c in text_parts[-1]):
        modifier = text_parts[-1]
        text_parts = text_parts[:-1]  # Remove modifier from text
        if modifier == "+":
            scale = 2
        elif modifier == "++":
            scale = 3

    text = " ".join(text_parts) if text_parts else "BigT"

    # tmux top pane mode (internal - called by launch_tmux)
    if args.tmux_top:
        run_tmux_top_pane(text, scheme, scale, args.refresh)
        return

    if args.interactive:
        display_bigt_banner()
        selected = run_font_picker(text, args.color)
        if selected is None:
            print("No font selected.")
            return
        print("Selected: %s" % selected)
        print("Usage: bigt %r -f %s" % (text, selected))
        return

    # --no-persist: just print banner and exit
    if args.no_persist:
        if args.font:
            banner_lines = _render_simple(text, args.font, args.color)
            for line in banner_lines:
                print(line)
        else:
            display_synthwave_text(text, color=args.color, scheme=scheme, scale=scale)
        return

    # --no-tmux or --font: use legacy persistent shell mode
    if args.no_tmux or args.font:
        if args.font:
            run_persistent(text, args.font, args.color, height=None, shell=args.shell)
        else:
            run_persistent_synthwave(text, args.color, args.shell, scheme=scheme, scale=scale)
        return

    # Default: tmux mode (banner + usage top pane, shell bottom pane)
    tmux_path = args.tmux if args.tmux is not None else "."
    launch_tmux(text, scheme, scale, args.refresh, tmux_path)


if __name__ == "__main__":
    main()
