import io
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from patrol.store import Store
from patrol.analysis import AnalysisService
from scripts.export_evidence import export_evidence


class ExportTests(unittest.TestCase):
    def test_task_evidence_integrity_escaping_and_no_private_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=Store(root/'server');raw=io.BytesIO()
            Image.new('RGB',(12,10),'red').save(raw,format='JPEG')
            event=dict(event_id='export-event-001',device_id='test',captured_at='2026-11-01T00:00:00Z',
                       category='manual_capture',location={'source':'manual_checkpoint','checkpoint':'B'})
            store.put(event,raw.getvalue());tid=store.task_create(event['event_id'])
            store.transition(tid,'claim');store.transition(tid,'submit','<script>do not execute</script>',raw.getvalue())
            store.transition(tid,'close');AnalysisService(store,{})
            (root/'server'/'private-key.txt').write_text('private-sentinel')
            before=store.tasks();summary=export_evidence(root/'server',root/'bundle')
            self.assertEqual(summary['closed'],1);self.assertEqual(summary['images'],2)
            records=json.loads((root/'bundle'/'records.json').read_text(encoding='utf-8'))
            self.assertEqual(records['tasks'][0]['state'],'closed')
            self.assertEqual(len(records['audit']),4)
            page=(root/'bundle'/'index.html').read_text(encoding='utf-8')
            self.assertIn('&lt;script&gt;',page);self.assertNotIn('<script>',page)
            self.assertIn('人工留证 · 已关闭',page)
            self.assertIn('2026-11-01 08:00:00（UTC+08:00）',page)
            self.assertNotIn('private-sentinel',page)
            self.assertFalse((root/'bundle'/'private-key.txt').exists())
            self.assertEqual(store.tasks(),before)


if __name__=='__main__':unittest.main()
