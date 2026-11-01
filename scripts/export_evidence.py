"""Export task-linked evidence to a private offline HTML/JSON bundle; no secrets.

Run from car project root: python3 scripts/export_evidence.py
Output stays under ignored runtime/. No upload, motion or database mutation.
"""
import argparse
import hashlib
import html
import json
import shutil
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path


def display_time(value):
    raw=str(value)
    try:
        stamp=datetime.fromisoformat(raw.replace('Z','+00:00'))
        if stamp.tzinfo is None:return raw+'（未注明时区）'
        return stamp.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')+'（UTC+08:00）'
    except ValueError:return raw+'（原始时间值）'


def export_evidence(source, output, reports=None):
    source=Path(source).resolve();output=Path(output).resolve()
    db=source/'patrol.sqlite3'
    if not db.is_file():raise ValueError('Existing server database required')
    with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
        c.row_factory=sqlite3.Row
        # One consistent read transaction for metadata. Images are atomically
        # written before the corresponding row is committed and never modified.
        c.execute('BEGIN')
        tasks=[dict(r) for r in c.execute('''SELECT t.*,e.payload,e.image,e.digest,e.received
            FROM tasks t JOIN events e ON e.id=t.event_id ORDER BY t.created''')]
        audit=[dict(r) for r in c.execute('SELECT task_id,action,at FROM audit ORDER BY id')]
        has_ai=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='analysis_jobs'").fetchone()
        analyses={r['event_id']:dict(r) for r in c.execute('SELECT * FROM analysis_jobs')} if has_ai else {}
    output.mkdir(parents=True,exist_ok=False);(output/'images').mkdir()
    hashes={}
    def copy_image(name, expected=None):
        path=(source/'images'/name).resolve()
        if path.parent!=(source/'images').resolve() or path.name!=name:
            raise ValueError('Invalid evidence image path')
        data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if expected and digest!=expected:raise ValueError('Source evidence digest mismatch')
        (output/'images'/name).write_bytes(data);hashes['images/'+name]=digest
        return 'images/'+name
    records=[];cards=[];esc=lambda value:html.escape(str(value),quote=True)
    states={'pending':'待处理','working':'处理中','review':'待复核','closed':'已关闭'}
    categories={'manual_capture':'人工留证','obstacle':'距离障碍','inspection_sample':'巡检采样',
                'litter_bottle':'疑似垃圾 · 瓶子','litter_cup':'疑似垃圾 · 杯子',
                'vegetation_candidate':'绿化候选区域','pending_inference':'待识别采样'}
    assessments={'normal':'未见明确异常','suspected_anomaly':'疑似异常','uncertain':'无法确定'}
    sources={'manual_checkpoint':'人工检查点','unavailable':'位置未确认','odometry':'里程计'}
    ai_states={'pending':'等待分析/重试','running':'分析中','succeeded':'分析完成','failed':'分析失败'}
    for task in tasks:
        event=json.loads(task.pop('payload'));task['event']=event
        before=copy_image(task['image'],task['digest']);after=None
        if task['result_image']:after=copy_image(task['result_image'])
        analysis=analyses.get(task['event_id'])
        if analysis:
            analysis['result']=json.loads(analysis['result']) if analysis['result'] else None
        task['analysis']=analysis;records.append(task)
        loc=event.get('location') or {}
        bits=['<article><h2>'+esc(categories.get(event['category'],event['category']))+' · '+esc(states.get(task['state'],task['state']))+'</h2>',
              '<p>任务 '+esc(task['id'])+'</p><p>采集时间：'+esc(display_time(event['captured_at']))+'</p>',
              '<p>位置来源：'+esc(sources.get(loc.get('source'),loc.get('source')))+'；检查点：'+esc(loc.get('checkpoint'))+'</p>',
              '<div class="photos"><figure><img loading="lazy" src="'+esc(before)+'"><figcaption>采集证据</figcaption></figure>']
        if after:bits.append('<figure><img loading="lazy" src="'+esc(after)+'"><figcaption>手机提交照片</figcaption></figure>')
        bits.append('</div><p>处理说明：'+esc(task['note'])+'</p>')
        if event.get('distance_m') is not None:bits.append('<p>传感器测距：'+esc(event['distance_m'])+'米</p>')
        if analysis:
            bits.append('<h3>AI辅助审核 · '+esc(ai_states.get(analysis['state'],analysis['state']))+'</h3>')
            result=analysis.get('result') or {}
            for key,label in [('scene_summary','场景'),('assessment','判断'),('evidence','依据'),
                              ('recommendation','建议'),('limitations','限制'),('model','模型')]:
                if key in result:
                    value=assessments.get(result[key],result[key]) if key=='assessment' else result[key]
                    bits.append('<p>'+label+'：'+esc(value)+'</p>')
            bits.append('<p>AI结果需人工确认，不能证明通路安全。</p>')
        bits.append('</article>');cards.append(''.join(bits))
    bundle=dict(exported_at=datetime.now(timezone.utc).isoformat(),tasks=records,audit=audit,
                scope='Task-linked evidence only; does not certify untested requirements.',
                image_sha256=hashes)
    (output/'records.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
    copied=[]
    if reports and Path(reports).is_dir():
        (output/'tests').mkdir()
        patterns=('versions-*.json','backend-outage-*.json','restart-*.json','proximity-*.json',
                  'short-route-record-*.json','short-route-play-*.json','ai-recovery-*.json',
                  'cold-boot-*.json','phone-mode-*.json','autostart-*.json')
        paths={path for pattern in patterns for path in Path(reports).glob(pattern)}
        for path in sorted(paths):
            if path.is_file():shutil.copy2(path,output/'tests'/path.name);copied.append(path.name)
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>巡检原型 · 任务验收证据</title><style>*{box-sizing:border-box}body{font:16px/1.6 system-ui;max-width:1100px;margin:auto;padding:20px;background:#eef3f5;color:#17303a}article{background:white;padding:20px;margin:20px 0;border-radius:12px}.photos{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;flex:1 1 240px;min-width:0}img{width:100%;max-height:460px;object-fit:contain;background:#dce4e8}p{overflow-wrap:anywhere}</style><h1>任务验收证据</h1><p>此包含真实现场照片，请私密保管。室内样张不代表户外夜巡；指令回放不代表定位导航。</p>'''
    document+='<p>导出时间（UTC）：'+esc(bundle['exported_at'])+'；任务数：'+str(len(records))+'</p>'
    document+=''.join(cards)+'</html>'
    (output/'index.html').write_text(document,encoding='utf-8')
    summary=dict(output=str(output),tasks=len(records),closed=sum(t['state']=='closed' for t in records),
                 images=len(hashes),test_reports=copied,credential_files_included=False)
    (output/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',default='runtime/server')
    p.add_argument('--output',default='runtime/delivery-'+str(time.time_ns()))
    p.add_argument('--reports',default='runtime/evidence')
    args=p.parse_args();print(json.dumps(export_evidence(args.source,args.output,args.reports),ensure_ascii=False))
