"""Attended, stationary backend-outage acceptance test. Never enables motion.

Run on car with --server-pid and --robot-pid matching current service processes.
It stops only those verified processes, collects >=20 frames, restarts robot while
backend is down, waits a real 300 seconds, then restores and checks exact IDs.
This does not simulate hotspot/internet loss; both apps are colocated on the car.
"""
import argparse
import json
import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
import requests

def rows(path, sql, values=()):
    with sqlite3.connect(str(path), timeout=15) as c:
        c.row_factory=sqlite3.Row
        return [dict(r) for r in c.execute(sql,values)]

def stop_process(pid, module):
    cmd=Path('/proc/%d/cmdline'%pid).read_bytes().replace(b'\0',b' ').decode()
    if ('-m '+module) not in cmd:raise RuntimeError('PID does not match '+module)
    os.kill(pid,signal.SIGTERM)
    for _ in range(150):
        if not Path('/proc/%d'%pid).exists():return
        time.sleep(.1)
    raise RuntimeError('Service did not exit: '+module)

def start(module,logname):
    env=os.environ.copy();env.pop('PATROL_CONFIG_JSON',None)
    with open('runtime/'+logname,'ab') as log:
        p=subprocess.Popen(['python3','-m',module],stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                           env=env,start_new_session=True)
    return p.pid

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--server-pid',type=int,required=True);parser.add_argument('--robot-pid',type=int,required=True)
    args=parser.parse_args()
    cfg=json.loads(Path('config.json').read_text());secret=json.loads(Path('.local-access/patrol-secrets.json').read_text())
    http=requests.Session();http.trust_env=False;headers={'X-Device-Token':secret['device_token']}
    def api(path,body=None):
        url='http://127.0.0.1:8766'+path
        r=http.get(url,headers=headers,timeout=5) if body is None else http.post(url,headers=headers,json=body,timeout=5)
        r.raise_for_status();return r.json()
    initial=api('/status')
    if initial['control']['enabled'] or initial['route']['mode']!='idle':raise RuntimeError('Require stationary locked car and idle route')
    if cfg['server_url']!='http://127.0.0.1:8765':raise RuntimeError('Expected colocated backend')
    rb=Path('runtime/robot/patrol.sqlite3');sb=Path('runtime/server/patrol.sqlite3')
    report=dict(test='backend_unavailable_300s',started_at=time.time(),simulates_hotspot=False)
    baseline={r['id'] for r in rows(rb,'SELECT id FROM events')}
    backend_down=False;robot_down=False;server_pid=args.server_pid
    try:
        stop_process(args.server_pid,'patrol.server');backend_down=True;t0=time.monotonic()
        report['outage_started_at']=time.time()
        api('/sampling',{'enabled':True})
        while time.monotonic()-t0<55:
            new=rows(rb,'SELECT id,uploaded FROM events')
            pending=[r['id'] for r in new if r['id'] not in baseline and not r['uploaded']]
            if len(pending)>=20:break
            time.sleep(1)
        api('/sampling',{'enabled':False})
        if len(pending)<20:raise RuntimeError('Fewer than 20 persisted samples')
        report['pending_ids_before_restart']=pending
        print('PERSISTED',len(pending),'pending images; restarting robot while backend remains down',flush=True)
        stop_process(args.robot_pid,'patrol.robot');robot_down=True
        report['robot_restart_pid']=start('patrol.robot','robot-phone.log');robot_down=False
        kept={r['id'] for r in rows(rb,'SELECT id FROM events WHERE uploaded=0')}
        if not set(pending)<=kept:raise RuntimeError('Queue did not survive restart')
        report['queue_survived_restart']=True
        last_notice=0
        while time.monotonic()-t0<300:
            elapsed=time.monotonic()-t0
            if elapsed-last_notice>=30:
                print('OUTAGE_SECONDS',round(elapsed,1),'pending',rows(rb,'SELECT count(*) n FROM events WHERE uploaded=0')[0]['n'],flush=True)
                last_notice=elapsed
            time.sleep(1)
        report['outage_seconds']=time.monotonic()-t0
        server_pid=start('patrol.server','server.log');backend_down=False;report['restored_server_pid']=server_pid
        print('BACKEND_RESTORED after',round(report['outage_seconds'],1),'seconds',flush=True)
        deadline=time.monotonic()+100
        while time.monotonic()<deadline:
            state=rows(rb,'SELECT id,uploaded FROM events')
            done={r['id'] for r in state if r['uploaded']}
            if set(pending)<=done:break
            time.sleep(1)
        else:raise RuntimeError('Recovery uploads did not complete')
        stored={r['id']:r for r in rows(sb,'SELECT id,image FROM events')}
        if not set(pending)<=set(stored):raise RuntimeError('Server missing event IDs')
        if any(not (Path('runtime/server/images')/stored[e]['image']).is_file() for e in pending):raise RuntimeError('Server missing image evidence')
        report['recovered_count']=len(pending)
        report['duplicate_ids']=rows(sb,'SELECT count(*) total,count(DISTINCT id) unique_ids FROM events')[0]
        # Re-post exactly one already acknowledged event; it must not create a duplicate.
        event=rows(rb,'SELECT * FROM events WHERE id=?',(pending[0],))[0]
        with (Path('runtime/robot/images')/event['image']).open('rb') as f:
            response=http.post(cfg['server_url']+'/api/events',headers=headers,data={'metadata':event['payload']},files={'image':('evidence.jpg',f,'image/jpeg')},timeout=10)
        response.raise_for_status();report['duplicate_upload_created']=response.json()['created']
        if report['duplicate_upload_created']:raise RuntimeError('Duplicate upload recreated event')
        report['final_control']=api('/status')['control']
        if report['final_control']['enabled'] or report['final_control']['duty']!=0:raise RuntimeError('Car unexpectedly armed')
        report['passed']=True
    except Exception as e:
        report['passed']=False;report['error']=str(e)
        raise
    finally:
        if robot_down:report['cleanup_robot_pid']=start('patrol.robot','robot-phone.log')
        try:api('/sampling',{'enabled':False});api('/control/stop',{})
        except requests.RequestException:pass
        if backend_down:report['cleanup_server_pid']=start('patrol.server','server.log')
        report['finished_at']=time.time()
        Path('runtime/evidence').mkdir(exist_ok=True)
        Path('runtime/evidence/backend-outage-20261101.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('pending_ids_before_restart','final_control')},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
