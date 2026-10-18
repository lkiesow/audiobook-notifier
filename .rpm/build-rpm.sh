#!/bin/bash

set -eux

dnf install -y rpmdevtools
rpmdev-setuptree

echo "%appversion ${1}" >>~/.rpmmacros
sed "s/@VERSION@/${1}/" /rpmbuild/.rpm/audiobook-notifier.container \
   > ~/rpmbuild/SOURCES/audiobook-notifier.container
cp /rpmbuild/.env.example ~/rpmbuild/SOURCES/
cp /rpmbuild/.rpm/audiobook-notifier.spec ~/rpmbuild/SPECS/
cp /rpmbuild/LICENSE ~/rpmbuild/BUILD/
cp /rpmbuild/README.md ~/rpmbuild/BUILD/

rpmbuild -ba ~/rpmbuild/SPECS/audiobook-notifier.spec

cp ~/rpmbuild/RPMS/noarch/audiobook-notifier*.rpm /rpmbuild/
# Also published on its own for systems without RPM
cp ~/rpmbuild/SOURCES/audiobook-notifier.container /rpmbuild/
