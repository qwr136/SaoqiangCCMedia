#!/usr/bin/env python3
"""Validate actual RootHide deb without installing or extracting into system paths."""
import argparse,hashlib,io,json,os,plistlib,subprocess,tarfile,tempfile
from pathlib import Path,PurePosixPath
from macho_pac import inspect_macho

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def archive(deb,control=False):
    raw=subprocess.check_output(['dpkg-deb','--ctrl-tarfile' if control else '--fsys-tarfile',str(deb)])
    files={}; modes={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
        for item in tf:
            name=item.name.removeprefix('./'); p=PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts,'Unsafe package path')
            if item.isdir():continue
            require(item.isfile(),'Unexpected link/device in deb: '+name)
            require(name not in files and item.size<16*1024*1024,'Duplicate or oversized member')
            require(item.uid==0 and item.gid==0,'Package files must be root:root')
            files[name]=tf.extractfile(item).read();modes[name]=item.mode
    return files,modes

def verify(deb,project,version):
    control,_=archive(deb,True);require(set(control)=={'control'},'Unexpected maintainer scripts/control members')
    fields=dict(line.split(': ',1) for line in control['control'].decode().splitlines() if ': ' in line)
    for k,v in {'Package':'com.saoqiang.ccmedia','Version':version,'Architecture':'iphoneos-arm64e','Author':'Xiaofei','Maintainer':'Xiaofei'}.items():require(fields.get(k)==v,'Control mismatch: '+k)
    dependencies={x.strip() for x in fields['Depends'].split(',')}
    require(dependencies=={'com.opa334.ccsupport','preferenceloader','roothide','firmware (>= 15.0)'},'Unexpected package dependencies')
    data,modes=archive(deb);expected=set();binaries=[];resources={}
    loader='Library/PreferenceLoader/Preferences/SaoqiangCCMedia.plist'
    for n in (loader,loader.replace('.plist','.png')):resources[n]=project/'layout'/n
    for i in range(1,8):
        prefs=i==7;suffix='' if i==1 else str(i)
        name='SaoqiangCCMediaPrefs' if prefs else 'SaoqiangCCMedia'+suffix
        src=project/('Preferences/Resources' if prefs else 'Module/Resources'+suffix)
        folder=('Library/PreferenceBundles/' if prefs else 'Library/ControlCenter/Bundles/')+name+'.bundle/'
        path=folder+name;expected.add(path)
        info=plistlib.loads(data[folder+'Info.plist']);source_info=plistlib.loads((src/'Info.plist').read_bytes())
        # Theos may add build metadata; all upstream identity/resources remain authoritative.
        for k,v in source_info.items():require(info.get(k)==v,'Bundle identity changed '+name+':'+k)
        expected.add(folder+'Info.plist')
        for res in ([] if not prefs else ['Root.plist','Icon.png','ListIcon.png','ListIcon@2x.png','ListIcon@3x.png']):resources[folder+res]=src/res
        require(modes[path]&0o111,'Binary not executable: '+name)
        with tempfile.TemporaryDirectory(prefix='sqccm-verify-') as td:
            p=Path(td)/name;p.write_bytes(data[path]);binary=inspect_macho(p)
        binaries.append({'path':path,'sha256':sha(data[path]),'size':len(data[path]),'macho':binary})
        # inspect_macho proves CFString PAC/signature; independently inspect platform/dependencies.
        import struct
        raw=data[path];ncmds=struct.unpack_from('<I',raw,16)[0];off=32;deps=[];build=[]
        require(struct.unpack_from('<I',raw,12)[0]==8,'Expected MH_BUNDLE')
        for _ in range(ncmds):
            cmd,size=struct.unpack_from('<II',raw,off)
            if cmd in (0xc,0x80000018,0x8000001f,0x80000023):
                start=struct.unpack_from('<I',raw,off+8)[0];dep=raw[off+start:off+size].split(b'\0')[0].decode();deps.append(dep)
            if cmd==0x32:build.append(struct.unpack_from('<III',raw,off+8))
            off+=size
        require(build==[(2,0x0f0000,0x100400)],'Expected iOS min15/SDK16.4: '+name)
        require('@loader_path/.jbroot/usr/lib/libroothide.dylib' in deps,'Missing strong RootHide dependency: '+name)
        require('/usr/lib/libSystem.B.dylib' in deps,'Missing libSystem')
        for dep in deps:require(dep.startswith(('/System/Library/','/usr/lib/','@loader_path/.jbroot/usr/lib/')) and '/var/jb/' not in dep,'Unresolved dependency '+dep)
    for name,src in resources.items():
        expected.add(name);require(data.get(name)==src.read_bytes(),'Resource changed: '+name)
    require(set(data)==expected,'Unexpected package layout: '+repr(sorted(set(data)^expected)))
    entry=plistlib.loads(data[loader])['entry'];require(entry['detail']=='SQCCMPreferencesController' and entry['bundle']=='SaoqiangCCMediaPrefs','Loader mismatch')
    return {'status':'passed','version':version,'sha256':sha(deb.read_bytes()),'size':deb.stat().st_size,'control':fields,'binaries':binaries,'files':{n:{'sha256':sha(v),'size':len(v)} for n,v in sorted(data.items())},'device_verified':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--project',default='.');p.add_argument('--scheme',choices=['roothide'],required=True);p.add_argument('--expected-version',required=True);p.add_argument('deb',nargs='+');a=p.parse_args()
    require(len(a.deb)==1,'Exactly one actual deb required')
    project=Path(a.project).resolve();result=verify(Path(a.deb[0]),project,a.expected_version)
    out=project/'reports/package-verification.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS actual deb: 7 bundles, authenticated CFString ISA, signed pages, package identity/resources')
if __name__=='__main__':main()
