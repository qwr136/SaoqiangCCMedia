#!/usr/bin/env python3
"""Reject custom compilers/linkers before Theos runs; do not alter the host."""
from pathlib import Path
import json,os,platform,subprocess

def checked(command):return subprocess.check_output(command,text=True,stderr=subprocess.STDOUT).strip()
def main():
    if platform.system()!='Darwin':raise SystemExit('Release builds require verified Apple Xcode on macOS; no Linux ABI guessing.')
    bad=[key for key in ('CC','CXX','LD','CLANG','SDKROOT','LD_COMMAND','EXTRA_CFLAGS','EXTRA_LDFLAGS','TARGET_CC','TARGET_CXX','TARGET_LD') if os.environ.get(key)]
    if bad:raise SystemExit('Reject unverified compiler/SDK overrides: '+', '.join(bad))
    dev=Path(os.environ['DEVELOPER_DIR']).resolve()
    tools={}
    for name in ('clang','ld'):
        p=Path(checked(['xcrun','--find',name])).resolve()
        if not p.is_relative_to(dev):raise SystemExit('Tool outside selected Xcode: '+name)
        tools[name]=str(p)
    version=checked([tools['clang'],'--version'])
    if not version.startswith('Apple clang version'):raise SystemExit('Only Apple clang is permitted')
    probe=Path('reports/apple-arm64e-probe.m');probe.parent.mkdir(exist_ok=True)
    probe.write_text('#if !__has_feature(ptrauth_calls)\n#error arm64e pointer authentication unavailable\n#endif\nconst char *sqccm_probe = "abi";\n')
    sdk=Path(os.environ['THEOS'])/'sdks/iPhoneOS16.5.sdk'
    checked([tools['clang'],'-target','arm64e-apple-ios15.0','-isysroot',str(sdk),'-fsyntax-only',str(probe)])
    result={'status':'passed','developer_dir':str(dev),'tools':tools,'clang_version':version,'probe':'actual Apple arm64e target accepts ptrauth_calls; final CFString ISA is verified separately'}
    Path('reports/apple-compiler.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS verified Apple clang/ld and arm64e compiler target')
if __name__=='__main__':main()
