"""Attended short straight forward/reverse recording; no automatic playback.

REQUIRES current human confirmation of clear >=1m path and nearby power cut-off.
Does not change limits, disable protection, retry arming or replay old routes.
Run from car project root after arranging the scene. Wheel RPM is not position.
"""
import argparse
import json
import time
from pathlib import Path
import requests


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--attended-clear-path', action='store_true', required=True)
    args=p.parse_args()
    http=requests.Session();http.trust_env=False
    secret=json.loads(Path('.local-access/patrol-secrets.json').read_text())
    http.headers['X-Device-Token']=secret['device_token']
    def api(path,body=None):
        url='http://127.0.0.1:8766'+path
        r=http.get(url,timeout=(.3,.4)) if body is None else http.post(url,json=body,timeout=(.3,.4))
        r.raise_for_status();return r.json()
    initial=api('/status')
    ctrl=initial['control']
    if (ctrl['enabled'] or ctrl['duty']!=0 or not ctrl['hardware_enabled']
        or not ctrl['transport_ok'] or ctrl['driver_error']
        or ctrl['feedback_rpm']!=0 or initial['route']['mode']!='idle'):
        raise RuntimeError('Require idle route, unarmed zero output and fresh healthy zero RPM')
    report=dict(test='attended_indoor_short_signed_record',started_at=time.time(),
                position_tracking=False,automatic_playback=False,samples=[])
    recording=False
    try:
        api('/routes/record/start',{'name':'indoor-night-signed-'+time.strftime('%H%M%S')});recording=True
        lease=api('/control/enable',{})['lease'];seq=0
        for phase,duty,seconds in [('initial_stop',0,.2),('forward',.07,.35),
                                   ('pause',0,.4),('reverse',-.08,.35),('final_stop',0,.5)]:
            t0=time.monotonic()
            while time.monotonic()-t0<seconds:
                seq+=1
                response=api('/control/heartbeat',dict(lease=lease,seq=seq,duty=duty,steering=0))
                sample=dict(phase=phase,elapsed=time.monotonic()-t0,
                            command_duty=duty,control=response)
                report['samples'].append(sample)
                if not response['enabled']:
                    raise RuntimeError('Protection stopped test: '+response['reason'])
                time.sleep(.075)
        report['saved_route']=api('/routes/record/stop',{});recording=False
        report['completed_sequence']=True
    except Exception as e:
        report['error']=str(e)
        report['completed_sequence']=False
    finally:
        if recording:
            try:report['partial_route']=api('/routes/record/stop',{})
            except Exception:pass
        try:
            api('/control/stop',{})
            time.sleep(.3)
            report['final_control']=api('/status')['control']
        except Exception as e:report['stop_request_error']=type(e).__name__
        report['finished_at']=time.time()
        path=Path('runtime/evidence')/('short-route-record-'+time.strftime('%Y%m%d-%H%M%S')+'.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        summary={k:v for k,v in report.items() if k!='samples'}
        summary['observed_rpm']={phase:[s['control']['feedback_rpm'] for s in report['samples'] if s['phase']==phase]
                                 for phase in ('forward','reverse','final_stop')}
        summary['evidence']=str(path)
        print(json.dumps(summary,ensure_ascii=False),flush=True)
    final=report.get('final_control',{})
    if (not report.get('completed_sequence') or final.get('enabled',True)
        or final.get('duty')!=0 or final.get('feedback_rpm')!=0 or final.get('driver_error')):
        raise SystemExit(1)


if __name__=='__main__':main()
