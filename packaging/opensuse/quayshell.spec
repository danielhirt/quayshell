Name:           quayshell
Version:        0.3.0
Release:        0
Summary:        Persistent Wayland terminal
License:        MIT
URL:            https://github.com/danielhirt/quayshell
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python313-build
BuildRequires:  python313-installer
BuildRequires:  python313-pytest
BuildRequires:  python313-wheel
BuildRequires:  zsh
Requires:       libgtk-4-1
Requires:       libgtk4-layer-shell0
Requires:       python313-gobject
Requires:       typelib-1_0-Gtk-4_0
Requires:       typelib-1_0-Gtk4LayerShell-1_0
Requires:       typelib-1_0-Vte-3_91

%description
Quayshell is a persistent GTK4 and VTE terminal for Wayland layer-shell
compositors.

%prep
%autosetup

%build
python3.13 -m build --wheel --no-isolation

%install
python3.13 -m installer --destdir=%{buildroot} dist/*.whl

%check
python3.13 -m pytest

%files
%license LICENSE
%doc README.md config.example.toml docs/install.md docs/support.md
%{_bindir}/quayshell
%{_datadir}/applications/dev.danielh.quayshell.desktop
%{_datadir}/icons/hicolor/scalable/apps/dev.danielh.quayshell.svg
%{_datadir}/metainfo/dev.danielh.quayshell.metainfo.xml
%{python313_sitelib}/quayshell
%{python313_sitelib}/quayshell-%{version}.dist-info

%changelog
