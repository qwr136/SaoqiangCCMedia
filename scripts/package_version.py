#!/usr/bin/env python3
from pathlib import Path
import json
p=Path(__file__).resolve().parents[1]
version=json.loads((p/'tweak.json').read_text())['package_version']
control=dict(line.split(': ',1) for line in (p/'control').read_text().splitlines() if ': ' in line)
if control['Version'] != version: raise SystemExit('Version mismatch')
print(version)
