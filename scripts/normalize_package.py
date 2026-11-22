#!/usr/bin/env python3
"""Normalize archive ownership only; never patch binaries, plists or scripts."""
from pathlib import Path,PurePosixPath
import gzip,hashlib,io,json,subprocess,tarfile

def normalize_tar(raw):
    out=io.BytesIO();before={};after={};owners=[]
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as source,tarfile.open(fileobj=out,mode='w',format=tarfile.GNU_FORMAT) as dest:
        for item in source:
            path=PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isdir() or item.isfile()):raise ValueError('Unsafe package member')
            if item.name in before:raise ValueError('Duplicate package member')
            payload=source.extractfile(item).read() if item.isfile() else b''
            before[item.name]=(item.type,item.mode,payload)
            owners.append({'path':item.name,'uid':item.uid,'gid':item.gid})
            item.uid=item.gid=0;item.uname=item.gname='root';item.pax_headers={}
            dest.addfile(item,io.BytesIO(payload) if item.isfile() else None)
    result=out.getvalue()
    with tarfile.open(fileobj=io.BytesIO(result),mode='r:') as check:
        for item in check:
            assert item.uid==0 and item.gid==0
            after[item.name]=(item.type,item.mode,check.extractfile(item).read() if item.isfile() else b'')
    if before!=after:raise ValueError('Payload or mode changed during ownership normalization')
    return result,owners

def make_ar(entries):
    result=bytearray(b'!<arch>\n')
    for name,data in entries:
        header=f'{name+"/":<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(data):<10}`\n'.encode('ascii')
        assert len(header)==60;result.extend(header);result.extend(data)
        if len(data)%2:result.extend(b'\n')
    return bytes(result)

def main():
    root=Path(__file__).resolve().parents[1];packages=list((root/'packages').glob('*.deb'));assert len(packages)==1
    package=packages[0];original=package.read_bytes();entries=[('debian-binary',b'2.0\n')];records={}
    for name,flag in [('control','--ctrl-tarfile'),('data','--fsys-tarfile')]:
        raw=subprocess.check_output(['dpkg-deb',flag,str(package)])
        normalized,owners=normalize_tar(raw);entries.append((name+'.tar.gz',gzip.compress(normalized,mtime=0)));records[name]=owners
    signed=make_ar(entries)
    tmp=package.with_suffix('.normalized.tmp');tmp.write_bytes(signed);tmp.replace(package)
    out=root/'reports/package-ownership.json';out.write_text(json.dumps({'input_sha256':hashlib.sha256(original).hexdigest(),'output_sha256':hashlib.sha256(signed).hexdigest(),'payload_and_modes_unchanged':True,'original_owners':records},indent=2)+'\n')
    print('PASS normalized all archive owners to root:root; every payload byte and mode preserved')
if __name__=='__main__':main()
