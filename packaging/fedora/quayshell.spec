Name:           quayshell
Version:        0.3.0
Release:        1%{?dist}
Summary:        Persistent Wayland terminal
License:        MIT
URL:            https://github.com/danielhirt/quayshell
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  python3-pytest
BuildRequires:  python3-setuptools >= 68
BuildRequires:  zsh
Requires:       gtk4
Requires:       gtk4-layer-shell
Requires:       python3-gobject
Requires:       vte291

%description
Quayshell is a persistent GTK4 and VTE terminal for Wayland layer-shell
compositors.

%prep
%autosetup

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files quayshell

%check
%pytest

%files -f %{pyproject_files}
%license LICENSE
%doc README.md config.example.toml docs/install.md docs/support.md
%{_bindir}/quayshell
%{_datadir}/applications/dev.danielh.quayshell.desktop
%{_datadir}/icons/hicolor/scalable/apps/dev.danielh.quayshell.svg
%{_datadir}/metainfo/dev.danielh.quayshell.metainfo.xml

%changelog
* Sat Aug 08 2026 Daniel Hirt <danielhirt@users.noreply.github.com> - 0.3.0-1
- Initial package template
