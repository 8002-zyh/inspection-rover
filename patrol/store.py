import hashlib
import io
import json
import logging
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from PIL import Image
from .common import now


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.images = self.root / 'images'
        self.images.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'patrol.sqlite3'
        with self.connect() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, image TEXT NOT NULL,
                digest TEXT NOT NULL, received TEXT NOT NULL,
                uploaded INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL,
                state TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
                result_image TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY, task_id TEXT, action TEXT, at TEXT);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(str(self.db), timeout=15)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def save_image(self, data, name):
        if len(data) > 10 * 1024 * 1024:
            raise ValueError('图片超过10MB')
        try:
            with Image.open(io.BytesIO(data)) as im:
                if im.width * im.height > 24000000:
                    raise ValueError('图片分辨率过大')
                if im.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('仅支持JPEG、PNG或WEBP图片')
                im.verify()
        except (OSError, SyntaxError, Image.DecompressionBombError) as e:
            raise ValueError('图片损坏或格式不支持') from e
        target = self.images / name
        tmp = self.images / (name + '.' + uuid.uuid4().hex + '.tmp')
        with tmp.open('wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(target))
        return name

    def put(self, payload, data):
        if not isinstance(payload, dict):
            raise ValueError('事件元数据必须为对象')
        eid = payload.get('event_id', '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', eid):
            raise ValueError('无效事件ID')
        for key in ('captured_at', 'category', 'location', 'device_id'):
            if key not in payload:
                raise ValueError('缺少字段: ' + key)
        digest = hashlib.sha256(data).hexdigest()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT digest,payload FROM events WHERE id=?', (eid,)).fetchone()
            if row:
                if row['digest'] != digest or row['payload'] != encoded:
                    raise ValueError('事件ID内容冲突')
                return False
            name = self.save_image(data, eid + '.jpg')
            c.execute('INSERT INTO events(id,payload,image,digest,received) VALUES(?,?,?,?,?)',
                      (eid, encoded, name, digest, now()))
        return True

    def events(self, pending=False):
        with self.connect() as c:
            rows = c.execute('SELECT * FROM events ' + ('WHERE uploaded=0 ' if pending else '') +
                             'ORDER BY received ' + ('ASC' if pending else 'DESC') + ' LIMIT 200').fetchall()
        result = []
        for r in rows:
            item = json.loads(r['payload'])
            item.update(image=r['image'], received_at=r['received'], uploaded=r['uploaded'] == 1)
            result.append(item)
        return result

    def ack(self, eid):
        with self.connect() as c:
            c.execute('UPDATE events SET uploaded=1 WHERE id=?', (eid,))

    def fail(self, eid, reason=''):
        """Permanent upload rejection: uploaded=2 leaves the pending queue but keeps evidence."""
        with self.connect() as c:
            c.execute('UPDATE events SET uploaded=2, attempts=attempts+1 WHERE id=?', (eid,))
        logging.warning('Event %s rejected permanently: %s', eid, reason)

    def counts(self):
        with self.connect() as c:
            return dict(c.execute('SELECT count(*) AS total, sum(CASE WHEN uploaded=0 THEN 1 ELSE 0 END) AS pending, sum(CASE WHEN uploaded=2 THEN 1 ELSE 0 END) AS failed FROM events').fetchone())

    def task_create(self, eid):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT id FROM events WHERE id=?', (eid,)).fetchone():
                raise ValueError('异常不存在')
            old = c.execute('SELECT id FROM tasks WHERE event_id=?', (eid,)).fetchone()
            if old:
                return old['id']
            tid = uuid.uuid4().hex
            c.execute('INSERT INTO tasks(id,event_id,state,created,updated) VALUES(?,?,?,?,?)',
                      (tid, eid, 'pending', now(), now()))
            c.execute('INSERT INTO audit(task_id,action,at) VALUES(?,?,?)', (tid, 'create', now()))
            return tid

    def tasks(self):
        with self.connect() as c:
            rows = c.execute('SELECT t.*, e.payload,e.image FROM tasks t JOIN events e ON e.id=t.event_id ORDER BY t.created DESC').fetchall()
        return [dict(r, event=json.loads(r['payload'])) for r in rows]

    def transition(self, tid, action, note='', photo=None):
        transitions = {'claim': ('pending', 'working'), 'submit': ('working', 'review'),
                       'close': ('review', 'closed'), 'return': ('review', 'working')}
        if action not in transitions:
            raise ValueError('未知操作')
        before, after = transitions[action]
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM tasks WHERE id=?', (tid,)).fetchone()
            if not row:
                raise ValueError('任务不存在')
            if row['state'] == after:
                return  # repeated request is idempotent
            if row['state'] != before:
                raise ValueError('状态已变化，请刷新')
            image = row['result_image']
            if action == 'submit':
                if not note.strip() or not photo:
                    raise ValueError('请填写处理说明并上传照片')
                image = self.save_image(photo, 'result-' + uuid.uuid4().hex + '.jpg')
            c.execute('UPDATE tasks SET state=?,note=?,result_image=?,updated=? WHERE id=?',
                      (after, note[:2000] if action == 'submit' else row['note'], image, now(), tid))
            c.execute('INSERT INTO audit(task_id,action,at) VALUES(?,?,?)', (tid, action, now()))
