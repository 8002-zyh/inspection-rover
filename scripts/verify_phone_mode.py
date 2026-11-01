"""Live API checks using a newly constructed ZERO-DUTY route only. No movement.

Verifies application watcher timeout, not physical braking or hotspot loss.
"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from patrol.common import now
from patrol.route import RouteLibrary,SCHEMA


def main():
    http=requests.Session();http.trust_env=False
    http.headers['X-Device-Token']=json.loads(Path('.local-access/patrol-secrets.json').read_text())['device_token']
    def api(path,body=None):
        url='http://127.0.0.1:8766'+path
        r=http.get(url,timeout=(.3,.4)) if body is None else http.post(url,json=body,timeout=(.3,.4))
        r.raise_for_status();return r.json()
    before=api('/status')
    if before['control']['enabled'] or before['control']['feedback_rpm']!=0 or before['route']['mode']!='idle':
        raise RuntimeError('Require stationary unarmed vehicle')
    rid='zero-watch-check'
    RouteLibrary('runtime/robot/routes').save(dict(schema=SCHEMA,id=rid,name='零动力监护自检（不行驶）',
        created_at=now(),sample_hz=10,max_duty=.03,notes='全部指令为0，仅作软件监护链路自检',
        samples=[dict(t=0,duty=0,steering=0),dict(t=2,duty=0,steering=0)]))
    report=dict(test='phone_monitor_zero_duty_api_check',physical_braking_test=False,cases=[])
    try:
        for watched,expected in [(False,'路线监护连接超时'),(True,'路线回放结束')]:
            started=api('/routes/play',{'route_id':rid});token=started['watch_token']
            t0=time.monotonic();states=[]
            while time.monotonic()-t0<4:
                state=api('/status');states.append(state['control'])
                if state['route']['mode']=='idle':break
                if watched:api('/routes/watch',{'watch_token':token})
                time.sleep(.06)
            else:raise RuntimeError('Zero route deadline exceeded')
            final=api('/status')
            case=dict(watched=watched,duration_s=time.monotonic()-t0,reason=final['control']['reason'],
                      route_error=final['route']['error'],all_duties_zero=all(s['duty']==0 for s in states),
                      all_feedback_zero=all(s['feedback_rpm']==0 for s in states),
                      final_control=final['control'])
            case['passed']=expected in case['reason'] and case['all_duties_zero'] and case['all_feedback_zero'] and not final['control']['enabled']
            report['cases'].append(case)
            if not case['passed']:raise RuntimeError('Monitor case failed')
        report['passed']=True
    except Exception as e:report.update(passed=False,error=str(e))
    finally:
        api('/control/stop',{})
        Path('runtime/evidence/phone-mode-20261101.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
    if not report.get('passed'):raise SystemExit(1)


if __name__=='__main__':main()
