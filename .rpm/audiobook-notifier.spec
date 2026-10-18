Name:          audiobook-notifier
Summary:       Track Audible audiobook series and get notified about new releases
Version:       %{appversion}
Release:       1
License:       MIT
BuildArch:     noarch

Source0:       %{name}.container
Source1:       .env.example
URL:           https://github.com/lkiesow/%{name}
BuildRoot:     %{_tmppath}/%{name}-root

Requires:      podman
Requires(post):    systemd
Requires(preun):   systemd
Requires(postun):  systemd


%description
Runs the Audiobook Notifier container image with Podman as a systemd service
(Quadlet). The web UI listens on 127.0.0.1:5000.


%prep

%build

%install
rm -rf %{buildroot}

# install Quadlet unit, systemd generates audiobook-notifier.service from it
install -p -D -m 0644 \
   %{SOURCE0} \
   %{buildroot}%{_datadir}/containers/systemd/%{name}.container

# install configuration, readable by root only since it holds secrets
install -p -D -m 0600 \
   %{SOURCE1} \
   %{buildroot}%{_sysconfdir}/%{name}.conf
sed -i '1i # DATABASE_PATH, HOST and PORT are set by the container and ignored here.\n' \
   %{buildroot}%{_sysconfdir}/%{name}.conf

# create database directory
install -p -d -m 0750 \
   %{buildroot}%{_sharedstatedir}/%{name}

%clean
rm -rf %{buildroot}


# The %%systemd_* macros cannot preset a generated unit, so reload and
# restart by hand. Restarting pulls the image of the new version.
%post
systemctl daemon-reload >/dev/null 2>&1 || :


%preun
if [ $1 -eq 0 ]; then
   systemctl stop %{name}.service >/dev/null 2>&1 || :
fi


%postun
systemctl daemon-reload >/dev/null 2>&1 || :
if [ $1 -ge 1 ]; then
   systemctl try-restart %{name}.service >/dev/null 2>&1 || :
fi


%files
%defattr(-,root,root,-)
%{_datadir}/containers/systemd/%{name}.container
%config(noreplace) %attr(0600,root,root) %{_sysconfdir}/%{name}.conf
%dir %attr(0750,root,root) %{_sharedstatedir}/%{name}
%license LICENSE
%doc README.md


%changelog
* Sun Oct 18 2026 Lars Kiesow <lkiesow@uos.de> - 0.1.0-1
- Initial build
