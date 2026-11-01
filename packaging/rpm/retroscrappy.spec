# Built by packaging/build-rpm.sh from a staged tree; not a source RPM.
%global appid io.github.retroboxproject.retroscrappy
%global prefix /opt/retroscrappy
# Python files live in /opt: skip Fedora's automatic Python handling.
%global __requires_exclude_from ^%{prefix}/.*$
%global __provides_exclude_from ^%{prefix}/.*$
%global __brp_python_bytecompile %{nil}
%global __brp_mangle_shebangs %{nil}
%global debug_package %{nil}

Name:           retroscrappy
Version:        %{pkg_version}
Release:        %{pkg_release}
Summary:        Metadata and artwork scraper for EmulationStation
License:        GPL-3.0-only
URL:            https://github.com/RetroboxProject/retroscrappy
Packager:       %{pkg_packager}
BuildArch:      noarch

Requires:       python3 >= 3.11
Requires:       python3-requests
Requires:       python3-pyside6
Recommends:     qt6-qtwayland

%description
Retroscrappy fills the gamelist.xml files of EmulationStation, as used by
Batocera, RetroBat and Retrobox, with descriptions, box art, logos,
screenshots and videos from ScreenScraper, SteamGridDB and IGDB.

It provides a Qt graphical interface (retroscrappy-gui) and a command line
tool (retroscrappy).

%install
cp -a %{stage_dir}/. %{buildroot}/
install -Dm0644 %{license_file} %{buildroot}%{_datadir}/licenses/%{name}/LICENSE

%post
python3 -m compileall -q %{prefix}/lib > /dev/null 2>&1 || :

%preun
if [ "$1" -eq 0 ]; then
    find %{prefix}/lib -type d -name __pycache__ -prune -exec rm -rf {} + 2> /dev/null || :
fi

%files
%{prefix}
%{_bindir}/%{name}
%{_bindir}/%{name}-gui
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/metainfo/%{appid}.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/%{appid}.*
%{_datadir}/licenses/%{name}/LICENSE
