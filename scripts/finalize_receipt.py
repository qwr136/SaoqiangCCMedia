#!/usr/bin/env python3
"""Bind verified package and real UIKit output to the current GitHub run."""
from pathlib import Path
import hashlib,json,os,subprocess
P=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    report=P/'reports';build=json.loads((report/'build-receipt.json').read_text());pkg=json.loads((report/'package-verification.json').read_text());ui=json.loads((report/'uikit/result.json').read_text())
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=P,text=True).strip()
    assert build['source_sha']==commit==os.environ['GITHUB_SHA']
    assert str(build['run_id'])==os.environ['GITHUB_RUN_ID'] and str(build['run_attempt'])==os.environ['GITHUB_RUN_ATTEMPT']
    assert pkg['status']=='passed' and len(pkg['binaries'])==7
    assert ui['status']=='PASS' and ui['checks']>0 and ui['completedCases']>=8 and ui['failures']==[]
    debs=list((P/'packages').glob('*.deb'));assert len(debs)==1
    assert digest(debs[0])==pkg['sha256']==build['packages'][0]['sha256']
    source=subprocess.check_output(['git','ls-files','-z'],cwd=P).split(b'\0')
    files={}
    for raw in source:
        if not raw:continue
        name=os.fsdecode(raw);data=(P/name).read_bytes();blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        expected=subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=P,text=True).strip();assert blob==expected,name
        files[name]={'sha256':hashlib.sha256(data).hexdigest(),'git_blob':blob,'size':len(data)}
    receipt={'status':'verified','source_sha':commit,'repository':os.environ['GITHUB_REPOSITORY'],'run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'version':pkg['version'],'artifacts':{str(x.relative_to(P)):{'sha256':digest(x),'size':x.stat().st_size} for x in [debs[0],report/'SaoqiangCCMedia-source.zip',report/'build-receipt.json',report/'package-verification.json',report/'uikit/result.json']},'tracked_files':files,'UIKit':{'checks':ui['checks'],'completedCases':ui['completedCases'],'mode':ui['mode']},'device_verified':False}
    (report/'delivery-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print('PASS current run/commit/package/source/UIKit binding')
if __name__=='__main__':main()
