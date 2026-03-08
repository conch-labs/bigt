# Installing bigt

## Requirements

- macOS (the usage meter relies on the macOS Keychain)
- Python 3.9+
- [tmux](https://github.com/tmux/tmux) — required for the default launch mode
- [WezTerm](https://wezfurlong.org/wezterm/) — recommended terminal

## Step 1: Install system dependencies

```bash
brew install tmux
brew install --cask wezterm
```

> If you don't have Homebrew: https://brew.sh

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
