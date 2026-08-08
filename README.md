# Quayshell

Quayshell is a persistent terminal for Wayland desktops. It appears above normal windows and can move between connected outputs.

The application does not request keyboard focus when it starts. Click the terminal when you want to type.

## Features

- Runs one login shell in a VTE pseudo-terminal.
- Appears on every workspace, including above full-screen windows.
- Uses layer-shell keyboard focus on demand.
- Shows a resize handle when the pointer approaches the top left.
- Shows a move handle when the pointer approaches the top center.
- Moves between connected Hyprland outputs while you drag it.
- Shows a close button when the pointer approaches the top right.
- Expands from a short panel to the usable screen height.
- Shows the running command, elapsed time, and last exit status.
- Includes a small status mascot that reacts to shell activity.
- Collapses an expanded panel when a command starts and reopens it after a failure.
- Sends a desktop notification when a long command finishes.
- Supports terminal selection, scrollback, ANSI colors, and clipboard actions.
- Can track a bottom dock through Hyprland IPC.
- Uses fixed bottom-right placement when dock data is unavailable.

## Requirements

You need a Wayland compositor that supports the layer-shell protocol. Hyprland, Sway, KDE Plasma, and COSMIC support it. GNOME does not support it.

Install these packages on Arch Linux:

```sh
sudo pacman -S --needed python python-gobject gtk4 gtk4-layer-shell vte4
```

See [Installation](docs/install.md) for Fedora, Ubuntu, Debian, openSUSE, NixOS, and Flatpak instructions.

## Run from the repository

```sh
python -m quayshell
```

Select the startup output when you use more than one monitor:

```sh
python -m quayshell --monitor HDMI-A-1
```

If you omit `--monitor`, Quayshell uses the focused Hyprland output at startup.

## Install for the current user

Create a virtual environment that can read the system GTK bindings:

```sh
python -m venv --system-site-packages .venv
.venv/bin/pip install -e .
.venv/bin/quayshell
```

## Move, resize, or close the panel

The controls use separate pointer zones. Moving through the terminal body does not show them.

- Move near the top left to show the resize handle. Drag it up and left to grow the collapsed panel.
- Move near the top center to show the move handle. Drag it anywhere in the connected monitor layout.
- Move near the top right to show the close button. Select it to quit Quayshell.

The resize keeps the bottom-right corner fixed. The default maximum is 2.5 times the startup width and height. The selected output also limits the size.

GTK drag offsets provide same-output movement and resizing on supported layer-shell compositors. Hyprland adds global cursor and monitor data. When the pointer enters another Hyprland output, Quayshell moves the layer surface to that output. The panel stays within the usable bounds of its current output and does not span outputs. The new output, position, and size last until Quayshell exits.

Set `cross_monitor = false` in the configuration or use `--no-cross-monitor` to keep the panel on its startup output.

Magnetic docking snaps the panel to nearby usable output edges and corners. Set `magnetic_docking = false` to disable it. Change `snap_distance` to control the capture distance.

## Command activity

Quayshell includes shell integration for Bash and Zsh. The integration emits OSC 133 command markers and private VTE properties. Quayshell uses these signals to track command start, completion, and exit status. It reads the foreground process from the pseudo-terminal to show the command name.

If you run a command while the panel is expanded, smart collapse returns it to its short size. A failed command expands the panel again. Commands that exceed `notification_after_seconds` send a desktop notification. Select the notification to summon Quayshell.

The status mascot is optional. Set `mascot = false` to hide it.

## Summon Quayshell

Move a running Quayshell to the pointer:

```sh
quayshell --summon
```

Return it to its configured startup output and position:

```sh
quayshell --home
```

You can bind these commands in Hyprland:

```ini
bind = SUPER, grave, exec, quayshell --summon
bind = SUPER SHIFT, grave, exec, quayshell --home
```

## Configuration

Quayshell reads `$XDG_CONFIG_HOME/quayshell/config.toml` at startup. It uses `~/.config` when `XDG_CONFIG_HOME` is not set.

All startup settings are available in the configuration:

```toml
[window]
width = 380
height = 72
margin = 8
monitor = "HDMI-A-1"
dock_namespace = "nwg-dock"
max_scale = 4.0
cross_monitor = true

[terminal]
font = "Monospace 11"
shell = "/bin/bash"

[compositor]
backend = "auto"

[behavior]
smart_collapse = true
expand_on_failure = true
notify_on_completion = true
notification_after_seconds = 5.0
result_seconds = 8.0
mascot = true
magnetic_docking = true
snap_distance = 24
```

Omit `monitor`, `dock_namespace`, or `shell` to use automatic values. Command-line options override matching file settings. See `config.example.toml` for the default configuration.

`max_scale` must be `1.0` or greater. A value of `4.0` permits up to four times the startup width and height.

## Dock tracking on Hyprland

First, find the dock layer namespace:

```sh
hyprctl layers
```

Then pass the exact namespace:

```sh
quayshell --monitor HDMI-A-1 --dock-namespace nwg-dock
```

Quayshell checks the dock geometry once per second. It matches the dock height. It fills the space to the right screen edge. It uses fixed placement if the layer is absent or is not a bottom dock.

A manual move, resize, or summon stops dock tracking until Quayshell restarts.

## Options

```text
--width PIXELS          Collapsed fallback width. Default: 380.
--height PIXELS         Collapsed fallback height. Default: 72.
--margin PIXELS         Fallback screen margin. Default: 8.
--monitor OUTPUT        Startup Wayland output name.
--dock-namespace NAME   Hyprland namespace for a bottom dock.
--font DESCRIPTION      Pango font description. Default: Monospace 11.
--shell PATH            Login shell path. Default: $SHELL.
--max-scale SCALE       Maximum resize scale. Default: 2.5.
--backend NAME          auto, generic, hyprland, or sway.
--[no-]cross-monitor    Allow or prevent dragging between outputs.
--summon                 Move a running Quayshell to the pointer.
--home                   Return a running Quayshell home.
--diagnose               Report runtime support and optional features.
```

## Shortcuts

| Shortcut | Action |
|---|---|
| `F11` or `Ctrl+Shift+E` | Expand or collapse |
| `Ctrl+Shift+C` | Copy selected text |
| `Ctrl+Shift+V` | Paste text |
| `Ctrl+Shift+Q` | Quit |

## Hyprland appearance

The layer namespace is `quayshell`. Add a Hyprland layer rule for this namespace if you want compositor blur. Check the [current layer-rule syntax](https://wiki.hypr.land/Configuring/Window-Rules/#layer-rules) first.

The GTK style is in `quayshell/style.css`.

## Linux support

Quayshell selects a Hyprland, Sway, or generic Wayland backend at runtime. Unsupported optional features remain disabled while the terminal, shell activity, movement, and resizing continue to work.

Run the diagnostic report before you report a platform problem:

```sh
quayshell --diagnose
```

See [Platform support](docs/support.md) for the feature matrix and current limits. GNOME remains unsupported because it does not implement layer-shell.

The repository contains package templates for Arch, Fedora, Debian, openSUSE, Nix, and Flatpak. Clean container builds pass for the native package templates. The Flatpak build also passes, but current Hyprland security filters its required layer-shell protocol. CI tests Python 3.11 through 3.13 on two Ubuntu releases. It also checks shell hooks, formatting, package builds, and Nix evaluation.

## Test

```sh
pytest
```

## License

MIT
