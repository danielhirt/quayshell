# Installation

Quayshell needs system GTK and VTE libraries. Create the virtual environment with `--system-site-packages` so Python can load their GObject typelibs.

After you install the system packages, use the same application steps on each distribution:

```sh
git clone https://github.com/danielhirt/quayshell.git
cd quayshell
python3 -m venv --system-site-packages .venv
.venv/bin/pip install .
.venv/bin/quayshell --diagnose
.venv/bin/quayshell
```

## Arch Linux

```sh
sudo pacman -S --needed python python-gobject gtk4 gtk4-layer-shell vte4
```

The repository also contains `packaging/arch/PKGBUILD` for release builds.

## Fedora

```sh
sudo dnf install python3 python3-gobject gtk4 vte291 gtk4-layer-shell
```

Use `packaging/fedora/quayshell.spec` as the RPM source-package template.

## Ubuntu and Debian

Ubuntu 25.10 and newer provide `libgtk4-layer-shell0`. Ubuntu 24.04 does not provide this library in its standard repository.

```sh
sudo apt install python3 python3-venv python3-gi gir1.2-gtk-4.0 \
  gir1.2-vte-3.91 libgtk4-layer-shell0
```

On a release without `libgtk4-layer-shell0`, build gtk4-layer-shell from its official source or use a native package from a trusted repository. Do not install Quayshell until `quayshell --diagnose` can find the library.

The `packaging/debian/` directory contains Debian source-package metadata.

## openSUSE

On openSUSE Tumbleweed:

```sh
sudo zypper install python313 python313-gobject libgtk-4-1 \
  libgtk4-layer-shell0 typelib-1_0-Gtk-4_0 \
  typelib-1_0-Gtk4LayerShell-1_0 typelib-1_0-Vte-3_91
```

Other openSUSE releases can use a different Python package suffix. Use `packaging/opensuse/quayshell.spec` as the RPM source-package template. Run `quayshell --diagnose` before you start the application.

## NixOS and Nix

The repository contains a flake:

```sh
nix run github:danielhirt/quayshell
```

For a local checkout:

```sh
nix run .
```

Add the package to the user or system profile if you want a persistent installation.

## Flatpak evaluation

The manifest builds against GNOME 50 and includes VTE and gtk4-layer-shell. It runs the login shell on the host through `flatpak-spawn`. The build completes, but a current Hyprland session hides the privileged layer-shell protocol from Flatpak clients. Quayshell cannot show its panel in that sandbox. Do not publish this build until supported compositors expose a safe way to grant layer-shell access.

Other Flatpak compositors can behave differently. Run the diagnostic command after installation. An error for `layer-shell protocol` confirms that the sandbox blocks the required protocol.

Build it with Flatpak Builder:

```sh
flatpak-builder --user --install --force-clean build-dir \
  packaging/flatpak/dev.danielh.quayshell.yml
flatpak run dev.danielh.quayshell --diagnose
```

## Shell integration

Quayshell includes tested Bash and Zsh integration. Other shells use VTE's standard shell properties and can provide less activity data.
