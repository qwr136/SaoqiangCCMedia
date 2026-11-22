#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$#" -le 1 ] && [ "${1:-roothide}" = roothide ] || { echo 'Only the original RootHide scheme is supported.' >&2; exit 1; }
python3 scripts/toolchain.py verify --output reports/toolchain-before-build.json
python3 scripts/check_apple_compiler.py
export THEOS_PACKAGE_SCHEME=roothide
make clean THEOS_PACKAGE_SCHEME=roothide
make package THEOS_PACKAGE_SCHEME=roothide FINALPACKAGE=1 DEBUG=0 PACKAGE_VERSION="$(python3 scripts/package_version.py)"
python3 scripts/normalize_package.py
python3 tests/verify_deb.py --project . --scheme roothide --expected-version "$(python3 scripts/package_version.py)" packages/*.deb
