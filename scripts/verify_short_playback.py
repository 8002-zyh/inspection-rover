"""Single attended playback of a freshly recorded <=3s straight pulse route.

Use only after human confirms the same clear test area; no loop or retry.
Rejects older routes, long routes, steering, larger duties and nonzero endpoints.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import requests


def main():
    p=argparse.ArgumentParser();p.add_argument('--route-id',required=True)
    p.add_argument('--attended-clear-path',action='store_true',required=True)
    args=p.parse_args()
    rid=args.route_id
    if not rid.startswith('route-') or not rid.replace('-','').isalnum():
        raise RuntimeError('Invalid route ID')
    doc=json.loads((Path('runtime/robot/routes')/(rid+'.json')).read_text())
    samples=doc['samples']
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(doc['created_at'])).total_seconds()
    if (not 0<=age<=900 or doc['notes']!='现场录制' or samples[-1]['t']>3
        or samples[0]['duty']!=0 or samples[-1]['duty']!=0
        or any(abs(s['steering'])>.001 or not -.08<=s['duty']<=.07 for s in samples)):
        raise RuntimeError('Route outside fresh short straight attended-test envelope')
    http=requests.Session();http.trust_env=False
    http.headers['X-Device-Token']=json.loads(Path('.local-access/patrol-secrets.json').read_text())['device_token']
    def api(path,body=None):
        url='http://127.0.0.1:8766'+path
        r=http.get(url,timeout=(.3,.4)) if body is None else http.post(url,json=body,timeout=(.3,.4))
        r.raise_for_status();return r.json()
    initial=api('/status');ctrl=initial['control']
    if (ctrl['enabled'] or ctrl['duty']!=0 or not ctrl['transport_ok'] or ctrl['driver_error']
        or ctrl['feedback_rpm']!=0 or initial['route']['mode']!='idle'):
        raise RuntimeError('Require stationary unarmed healthy vehicle')
    report=dict(test='single_attended_short_signed_playback',route_id=rid,
                position_tracking=False,started_at=time.time(),telemetry=[])
    started=False
    try:
        response=api('/routes/play',{'route_id':rid});started=True
        watch_token=response.pop('watch_token',None)
        report['play_response']=response
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            state=api('/status')
            report['telemetry'].append(dict(at=time.time(),control=state['control'],
                                            route_mode=state['route']['mode'],error=state['route']['error']))
            if state['route']['mode']=='idle':break
            if watch_token:api('/routes/watch',{'watch_token':watch_token})
            time.sleep(.06)
        else:raise RuntimeError('Short playback deadline exceeded')
        time.sleep(.3);final=api('/status')
        report['final_control']=final['control'];report['route_error']=final['route']['error']
        report['passed']=(not final['control']['enabled'] and final['control']['duty']==0
                          and final['control']['feedback_rpm']==0 and not final['route']['error']
                          and final['control']['reason']=='路线回放结束')
    except Exception as e:report.update(passed=False,error=str(e))
    finally:
        if started:
            try:
                if api('/routes/status')['mode']!='idle':api('/routes/stop',{})
                api('/control/stop',{})
            except Exception as e:report['cleanup_error']=type(e).__name__
        report['finished_at']=time.time()
        path=Path('runtime/evidence')/('short-route-play-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
        path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        output={k:v for k,v in report.items() if k!='telemetry'}
        output['observed_duties']=sorted({t['control']['duty'] for t in report['telemetry']})
        output['observed_rpm']=sorted({t['control']['feedback_rpm'] for t in report['telemetry'] if t['control']['feedback_rpm'] is not None})
        output['evidence']=str(path);print(json.dumps(output,ensure_ascii=False),flush=True)
    if not report.get('passed') or report.get('cleanup_error'):raise SystemExit(1)


if __name__=='__main__':main()
