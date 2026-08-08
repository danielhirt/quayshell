# Platform support

Quayshell supports Linux on Wayland. It requires GTK4, VTE 0.78 or newer, and the layer-shell protocol.

## Feature levels

| Feature | Hyprland | Sway | Generic layer-shell compositor |
|---|---:|---:|---:|
| Terminal and shell activity | Yes | Yes | Yes |
| Same-output movement and resizing | Yes | Yes | Yes |
| Magnetic edge docking | Yes | Yes | Yes |
| Output selection | Yes | Yes | GDK output data |
| Reserved-edge placement | Yes | No | No |
| Cross-output dragging | Yes | No | No |
| Summon to pointer | Yes | No | No |
| Bottom-dock tracking | Yes | No | No |

The generic backend covers KDE Plasma, COSMIC, and other compositors that implement layer-shell. These compositors can expose more features through future adapters.

GNOME does not implement layer-shell. Quayshell does not currently run on GNOME. A future regular-window mode could provide fewer features.

Flatpak can also hide layer-shell from sandboxed clients. The included manifest builds, but it cannot display a panel on the tested Hyprland session. `quayshell --diagnose` now checks the protocol itself instead of checking only the installed library.

## Why features differ

Wayland does not give clients global pointer coordinates. GTK drag offsets permit movement and resizing on the current output. Cross-output dragging and summon-to-pointer require a compositor-specific API.

Quayshell selects a backend in this order:

1. Hyprland when `HYPRLAND_INSTANCE_SIGNATURE` and `hyprctl` are available.
2. Sway when `SWAYSOCK` and `swaymsg` are available.
3. Generic GDK output data for other Wayland compositors.

Run this command to see the selected support level:

```sh
quayshell --diagnose
```

A warning means that an optional feature is unavailable. An error means that a required runtime component is unavailable.
