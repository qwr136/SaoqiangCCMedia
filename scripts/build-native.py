#!/usr/bin/env python3
"""Compatibility entry: the unverified Linux linker pipeline is retired.
Original implementation: docs/legacy-build-native.py.txt (historical only).
"""
from pathlib import Path
import os,sys
if len(sys.argv)>1:raise SystemExit('Use sh build.sh roothide; legacy split-phase/override builds are intentionally disabled.')
os.execv('/bin/sh',['/bin/sh',str(Path(__file__).resolve().parents[1]/'build.sh'),'roothide'])
