"""图形界面：本地网页 + 小 HTTP 服务。浏览器负责录音和播放，这里负责 say / Whisper / 比对 / 分析。"""

import datetime as dt
import json
import re
import subprocess
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import analyze, articulation, asr, compare

WEB_DIR = Path(__file__).parent / "web"
_asr_lock = threading.Lock()  # mlx 不保证线程安全，识别串行


class App:
    def __init__(self, drills_dir: Path, out_dir: Path, asr_model: str, gemini_model: str):
        self.drills_dir = drills_dir
        self.session = out_dir / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.asr_model = asr_model
        self.gemini_model = gemini_model
        self.counter = 0

    def log(self, record: dict) -> None:
        self.session.mkdir(parents=True, exist_ok=True)
        with (self.session / "log.jsonl").open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def drills(self) -> list[dict]:
        from .cli import load_drills

        return [
            {"name": p.stem, "items": [{"target": t, "hint": h} for t, h in load_drills(p)]}
            for p in sorted(self.drills_dir.glob("*.txt"))
        ]

    def phonemes(self, text: str, hint: str) -> dict:
        from .cli import load_drills

        lexicon = articulation.build_lexicon([x for p in sorted(self.drills_dir.glob("*.txt")) for x in load_drills(p)])
        res = articulation.analyze(text, hint, lexicon)
        articulation.prefetch(list(res["clips"]))
        return res

    def tts(self, text: str, rate: int) -> bytes:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "say.wav"
            subprocess.run(
                ["say", "-r", str(rate), "--data-format=LEI16@22050", "-o", str(out), text],
                check=True,
            )
            return out.read_bytes()

    def check(self, audio: bytes, target: str) -> dict:
        self.session.mkdir(parents=True, exist_ok=True)
        self.counter += 1
        from .cli import _slug

        stem = f"{self.counter:03d}-{_slug(target)}"
        raw = self.session / f"{stem}.webm"
        wav = self.session / f"{stem}.wav"
        raw.write_bytes(audio)
        # 浏览器录的是 webm/opus，转成 Whisper 和 AI 分析都认的 16k 单声道 wav
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-i", str(raw), "-ar", "16000", "-ac", "1", str(wav)],
            check=True,
        )
        raw.unlink()
        with _asr_lock:
            heard = asr.transcribe(wav, self.asr_model)
        res = compare.compare(target, heard)
        self.log({"type": "check", "target": target, "heard": heard, "ok": res.ok, "wav": wav.name})
        return {"heard": heard, "ok": res.ok, "wer": res.wer, "ops": res.ops, "wav": wav.name}

    def analyze(self, wav_name: str, target: str, hint: str, attempts: list[str]) -> str:
        wav = (self.session / wav_name).resolve()
        if wav.parent != self.session.resolve() or not wav.exists():
            raise ValueError("录音不存在")
        reply = analyze.analyze(wav, target, attempts, hint, self.gemini_model)
        (self.session / f"{wav.stem}-analysis.md").write_text(reply)
        self.log({"type": "analysis", "target": target, "attempts": attempts, "wav": wav_name})
        return reply


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 安静点
            pass

        def _send(self, status, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, status=HTTPStatus.OK):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _send_file(self, path: Path, ctype: str):
            """带 Range 支持，<video> 拖动进度和 Safari 都要这个。"""
            data = path.read_bytes()
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if not m or not (m[1] or m[2]):
                status, body = HTTPStatus.OK, data
            else:
                start = int(m[1]) if m[1] else max(len(data) - int(m[2]), 0)
                end = min(int(m[2]), len(data) - 1) if m[1] and m[2] else len(data) - 1
                if start > end:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.end_headers()
                    return
                status, body = HTTPStatus.PARTIAL_CONTENT, data[start : end + 1]
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "max-age=604800")
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length", 0)))

        def do_GET(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    self._send(HTTPStatus.OK, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/api/drills":
                    self._json({"drills": app.drills(), "session": str(app.session), "analyze": analyze.enabled()})
                elif url.path == "/api/phonemes":
                    self._json(app.phonemes(q.get("text", ""), q.get("hint", "")))
                elif url.path.startswith("/api/articulation/") and url.path.endswith(".mp4"):
                    ref = url.path.removeprefix("/api/articulation/").removesuffix(".mp4")
                    if ref not in articulation.CLIPS:
                        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                    else:
                        self._send_file(articulation.clip_path(ref), "video/mp4")
                elif url.path == "/api/tts":
                    self._send(HTTPStatus.OK, app.tts(q["text"], int(q.get("rate", 150))), "audio/wav")
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

        def do_POST(self):
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/check":
                    self._json(app.check(self._body(), q["target"]))
                elif url.path == "/api/analyze":
                    d = json.loads(self._body())
                    self._json({"reply": app.analyze(d["wav"], d["target"], d.get("hint", ""), d["attempts"])})
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except Exception as e:
                self._json({"error": str(e)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    return Handler


def _warm_up(model: str) -> None:
    """后台先把 Whisper 模型加载好，第一次读的时候不用干等。"""
    import numpy as np
    import wave

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "silence.wav"
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(np.zeros(8000, dtype=np.int16).tobytes())
        with _asr_lock:
            asr.transcribe(p, model)


def serve(drills_dir: Path, out_dir: Path, asr_model: str, gemini_model: str, port: int, open_browser: bool) -> None:
    app = App(drills_dir, out_dir, asr_model, gemini_model)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"speak-drill 图形界面：{url}  （Ctrl+C 退出）")
    threading.Thread(target=_warm_up, args=(asr_model,), daemon=True).start()
    articulation.prefetch(list(articulation.CLIPS))  # 全部 39 段约 12MB，下一次就离线可用
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
