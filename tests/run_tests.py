#!/usr/bin/env python3
"""Discover the complete source regression suite; zero/all-skipped is failure."""
import argparse,datetime,json,sys,unittest
from pathlib import Path
TESTS=Path(__file__).resolve().parent
class SQCCMCaseResult(unittest.TextTestResult):
    def __init__(self,*a,**kw):
        super().__init__(*a,**kw);self.passed=set();self.failed=set()
    def addSuccess(self,t):super().addSuccess(t);self.passed.add(t.id())
    def addFailure(self,t,e):super().addFailure(t,e);self.failed.add(t.id())
    def addError(self,t,e):super().addError(t,e);self.failed.add(t.id())
    def addUnexpectedSuccess(self,t):super().addUnexpectedSuccess(t);self.failed.add(t.id())
    def addSubTest(self,t,sub,e):
        super().addSubTest(t,sub,e)
        if e is not None:self.failed.add(t.id())
def main():
    p=argparse.ArgumentParser();p.add_argument('-v',action='store_true');a=p.parse_args()
    suite=unittest.TestLoader().discover(str(TESTS),pattern='test_*.py',top_level_dir=str(TESTS))
    with (TESTS/'report.txt').open('w') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2 if a.v else 1,resultclass=SQCCMCaseResult).run(suite)
    ok=result.wasSuccessful() and result.testsRun>0 and len(result.passed)>0 and not result.skipped and not result.expectedFailures
    report={'status':'passed' if ok else 'failed','total':result.testsRun,'passed':len(result.passed),'failed':len(result.failed),'skipped':len(result.skipped),'expected_failures':len(result.expectedFailures),'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'source tests; not device acceptance'}
    (TESTS/'report.json').write_text(json.dumps(report,indent=2)+'\n');print((TESTS/'report.txt').read_text());print(json.dumps(report));return 0 if ok else 1
if __name__=='__main__':sys.exit(main())
