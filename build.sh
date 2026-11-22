#!/bin/sh
set -eu
cd "$(dirname "$0")"
scheme=${1:-roothide}
case "$scheme" in
 roothide) test -n "${THEOS:-}"; test -f "$THEOS/vendor/mod/roothide/package/deb.mk" || { echo 'RootHide Theos required; do not relabel an ordinary package.' >&2; exit 1; };;
 rootless) echo 'Building ROOTLESS artifact. This is NOT a native RootHide package.';;
 *) echo 'Usage: sh build.sh roothide|rootless' >&2; exit 1;;
esac
make clean THEOS_PACKAGE_SCHEME="$scheme"
make package THEOS_PACKAGE_SCHEME="$scheme" FINALPACKAGE=1
