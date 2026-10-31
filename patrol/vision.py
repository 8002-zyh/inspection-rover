import time
import uuid
from .common import now


class Vision:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = None
        self.error = ''
        self.last = {}
        self.version = 'hsv-candidate-v1'

    def load(self):
        from pathlib import Path
        try:
            if not Path(self.cfg['model_path']).is_file():
                raise RuntimeError('模型权重未安装，瓶子/杯子识别不可用')
            from ultralytics import YOLO
            self.model = YOLO(self.cfg['model_path'])
            self.version = 'yolov8n+hsv-v1'
        except Exception as e:
            self.error = str(e)

    def detect(self, frame):
        import cv2
        findings = []
        if self.model:
            try:
                result = self.model.predict(frame, imgsz=640, conf=self.cfg['confidence'], verbose=False)[0]
                h, w = frame.shape[:2]
                for box in result.boxes:
                    name = result.names[int(box.cls.item())]
                    if name in self.cfg['categories']:
                        coords = box.xyxy[0].tolist()
                        if coords[3] / h >= self.cfg['ground_roi_top']:
                            findings.append(dict(category=self.cfg['categories'][name], confidence=float(box.conf.item()), bbox=coords))
                self.error = ''
            except Exception as e:
                self.error = '模型推理失败: ' + str(e)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (30, 55, 35), (90, 255, 255))
        fraction = cv2.countNonZero(mask) / float(mask.size)
        if fraction >= self.cfg['green_fraction']:
            findings.append(dict(category='vegetation_candidate', confidence=None, green_fraction=fraction, method='HSV颜色规则，非植物语义识别'))
        return findings

    def event(self, finding, location, session, captured):
        key = (finding['category'], location.get('checkpoint'), session)
        t = time.monotonic()
        if t-self.last.get(key, -10000) < self.cfg['dedup_seconds']:
            return None
        self.last[key] = t
        return dict(finding, event_id=uuid.uuid4().hex, device_id=self.cfg['device_id'],
                    captured_at=captured, location=location, session_id=session,
                    model_version=self.version, class_schema_version=1, inference_state='identified')
