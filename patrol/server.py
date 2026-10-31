import hmac
import json
import os
import secrets
from functools import wraps
from pathlib import Path
import requests
from flask import Flask, jsonify, request, session, render_template, send_from_directory, Response
from werkzeug.security import check_password_hash
from .store import Store
from .common import configuration, credentials


def create_app(cfg=None, secret=None, root=None):
    cfg = cfg or configuration()
    secret = secret or credentials()
    store = Store(root or os.environ.get('PATROL_DATA', 'runtime/server'))
    app = Flask(__name__)
    app.secret_key = secret['session_key']
    app.config.update(MAX_CONTENT_LENGTH=12*1024*1024, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict')
    app.store = store
    net = requests.Session()
    net.trust_env = False

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not session.get('user'):
                return jsonify(error='请登录'), 401
            if request.method != 'GET' and not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.get('csrf', 'invalid')):
                return jsonify(error='请求校验失败，请重新登录'), 403
            return fn(*args, **kwargs)
        return wrapper

    @app.errorhandler(ValueError)
    def invalid(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(413)
    def too_big(e):
        return jsonify(error='图片超过上传限制'), 413

    @app.get('/')
    def index():
        return render_template('index.html')

    @app.post('/api/login')
    def login():
        data = request.get_json(silent=True) or {}
        if data.get('username') != 'operator' or not check_password_hash(secret['password_hash'], data.get('password', '')):
            return jsonify(error='用户名或密码错误'), 401
        session.clear()
        session['user'], session['csrf'] = 'operator', secrets.token_hex(24)
        return jsonify(csrf=session['csrf'])

    @app.get('/api/session')
    @login_required
    def current():
        return jsonify(csrf=session['csrf'])

    @app.post('/api/logout')
    @login_required
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.post('/api/events')
    def ingest():
        if not hmac.compare_digest(request.headers.get('X-Device-Token', ''), secret['device_token']):
            return jsonify(error='Unauthorized'), 401
        try:
            payload = json.loads(request.form['metadata'])
            photo = request.files['image'].read()
            created = store.put(payload, photo)
        except (KeyError, json.JSONDecodeError) as e:
            raise ValueError('事件格式不正确') from e
        return jsonify(event_id=payload['event_id'], created=created)

    @app.get('/api/events')
    @login_required
    def events():
        return jsonify(store.events())

    @app.get('/images/<name>')
    @login_required
    def image(name):
        return send_from_directory(store.images, name)

    @app.get('/api/tasks')
    @login_required
    def tasks():
        return jsonify(store.tasks())

    @app.post('/api/tasks')
    @login_required
    def task_create():
        return jsonify(task_id=store.task_create((request.get_json() or {}).get('event_id')))

    @app.post('/api/tasks/<tid>/<action>')
    @login_required
    def task_change(tid, action):
        file = request.files.get('photo')
        store.transition(tid, action, request.form.get('note', ''), file.read() if file else None)
        return jsonify(ok=True)

    @app.route('/api/robot/<path:path>', methods=['GET', 'POST'])
    @login_required
    def robot(path):
        allowed = {'status': 'GET', 'preview': 'GET', 'control/enable': 'POST', 'control/stop': 'POST',
                   'control/heartbeat': 'POST', 'checkpoint': 'POST', 'capture': 'POST', 'sampling': 'POST',
                   'routes': 'GET', 'routes/status': 'GET', 'routes/record/start': 'POST',
                   'routes/record/stop': 'POST', 'routes/record/note': 'POST', 'routes/play': 'POST', 'routes/stop': 'POST'}
        if allowed.get(path) != request.method:
            return jsonify(error='未知接口'), 404
        try:
            r = net.request(request.method, cfg['robot_url']+'/'+path,
                            headers={'X-Device-Token': secret['device_token']},
                            json=request.get_json(silent=True) if request.method=='POST' else None,
                            timeout=(1, 2))
            return Response(r.content, status=r.status_code, content_type=r.headers.get('Content-Type'), headers={'Cache-Control': 'no-store'})
        except requests.RequestException:
            return jsonify(error='小车离线或响应超时；控制需重新使能'), 503
    return app


if __name__ == '__main__':
    from waitress import serve
    serve(create_app(), host=configuration().get('server_bind_host', '127.0.0.1'), port=8765, threads=12)
