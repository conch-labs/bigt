# Installing bigt

## Requirements

- macOS or Linux
- Python 3.9+
- [tmux](https://github.com/tmux/tmux) — required for the default launch mode
- [WezTerm](https://wezfurlong.org/wezterm/) — recommended terminal

The Claude usage meter reads its OAuth token from the macOS Keychain on
macOS, and from `~/.claude/.credentials.json` on Linux.

## Step 1: Install system dependencies

macOS:

```bash
brew install tmux
brew install --cask wezterm
```

> If you don't have Homebrew: https://brew.sh

Linux (Debian/Ubuntu):

```bash
sudo apt install tmux
```

WezTerm on Linux: see https://wezfurlong.org/wezterm/install/linux.html

## Step 2: Install bigt

From inside the `bigt/` directory:

```bash
pipx install .
```

Or if you don't have `pipx`:

```bash
pip install .
```

## Step 3: Run it

```bash
bigt "your project name"
```

This opens a tmux session with a big synthwave banner at the top and a shell below.

---

## Optional: Claude usage meter

If you have [Claude Code](https://claude.ai/code) installed and are logged in, bigt will show your Claude Max usage in the top pane automatically. No extra setup needed.

---

## Quick usage

```bash
bigt "my project"         # default synthwave style
bigt "my project" +       # bigger
bigt "my project" ++      # biggest
bigt "my project" -s fire # different color scheme (synthwave, cyberpunk, ocean, fire, forest, pastel, purple)
bigt "my project" --no-persist  # just print the banner and exit
bigt --themes             # preview all color schemes
```
