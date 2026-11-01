"""Isolated AI connection-failure/restart acceptance, never controls the robot.

Injects a real refused TCP connection with a dummy key, then uses the configured
vision API once after manual retry. Does not disconnect the hotspot or modify
production jobs, configuration, images or tasks. Run from the project root.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from patrol.analysis import AnalysisService
from patrol.store import Store


def fail_once(root, eid):
    # Dummy credentials must never be replaced by the actual API key here.
    service = AnalysisService(Store(root), dict(
        api_key='fault-injection-dummy', model='diagnostic', base_url='http://127.0.0.1:9'))
    with service.store.connect() as c:
        c.execute('UPDATE analysis_jobs SET next_at=0 WHERE event_id=?', (eid,))
    if not service.run_once():
        raise RuntimeError('Expected one pending diagnostic job')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--event-id', required=True)
    p.add_argument('--source', default='runtime/server')
    p.add_argument('--vision-config', default='.local-access/vision-api.json')
    p.add_argument('--fail-once-root')
    p.add_argument('--resume-root', help='Explicit manual retry of a prior failed diagnostic')
    args = p.parse_args()
    if args.fail_once_root:
        fail_once(args.fail_once_root, args.event_id)
        return
    if not (Path(args.source)/'patrol.sqlite3').is_file():
        raise RuntimeError('Existing source database required')
    source = Store(args.source)
    with source.connect() as c:
        row = c.execute('SELECT payload,image FROM events WHERE id=?', (args.event_id,)).fetchone()
    if row is None:
        raise RuntimeError('Source event not found')
    data = (source.images/row['image']).read_bytes()
    cfg = json.loads(Path(args.vision_config).read_text(encoding='utf-8'))
    report = dict(test='ai_connection_failure_process_restart_manual_retry',
                  real_hotspot_disconnected=False, event_id=args.event_id,
                  source_image_sha256=hashlib.sha256(data).hexdigest(), phases=[])
    root = Path(args.resume_root) if args.resume_root else Path('runtime/evidence')/('ai-recovery-'+str(time.time_ns()))
    if args.resume_root:
        report = json.loads((root/'report.json').read_text(encoding='utf-8'))
        assert report['event_id'] == args.event_id
        report.setdefault('recovery_failures', []).append(report.pop('error', 'previous attempt failed'))
    report['evidence_directory'] = str(root)
    diagnostic = Store(root)
    diagnostic.put(json.loads(row['payload']), data)
    service = AnalysisService(diagnostic, cfg)
    service.enqueue(args.event_id)
    try:
        # A fresh process handles every attempt: verify persistence across exits.
        for attempt in ([] if args.resume_root else range(1, 4)):
            subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            '--event-id', args.event_id, '--fail-once-root', str(root)],
                           check=True, timeout=15)
            state = AnalysisService(diagnostic, cfg).results()[args.event_id]
            expected = 'pending' if attempt < 3 else 'failed'
            assert state['state'] == expected and state['attempts'] == attempt, state
            report['phases'].append(dict(attempt=attempt, state=state['state'], error=state['error']))
        service = AnalysisService(diagnostic, cfg)
        service.enqueue(args.event_id)  # Explicit manual retry after attempts exhausted.
        assert service.results()[args.event_id]['attempts'] == 0
        service.run_once()
        state = service.results()[args.event_id]
        assert state['state'] == 'succeeded', state['error']
        assert state['result']['source_image_sha256'] == report['source_image_sha256']
        report.update(passed=True, recovered_state=state['state'],
                      recovered_model=state['result']['model'], evidence_directory=str(root))
    except Exception as e:
        report.update(passed=False, error=str(e))
        raise
    finally:
        report['finished_at'] = time.time()
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
