"""领读：macOS 用系统 say；Linux 服务器用 Kokoro（离线神经网络 TTS，int8 模型约 90MB）。"""

import io
import os
import subprocess
import sys
import tempfile
import threading
import wave
from pathlib import Path

BACKEND = os.environ.get("SPEAK_DRILL_TTS", "say" if sys.platform == "darwin" else "kokoro")
# 默认英音女声，和练习提示里的英式音标一致；bm_george 是英音男声，af_heart 是美音
VOICE = os.environ.get("SPEAK_DRILL_VOICE", "bf_emma")
MODEL_DIR = Path.home() / ".cache" / "speak-drill" / "kokoro"
_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ("kokoro-v1.0.int8.onnx", "voices-v1.0.bin")

_kokoro = None
_lock = threading.Lock()


def say(text: str, rate: int = 150) -> None:
    """命令行：直接从扬声器读出来（只在 macOS 上用）。"""
    subprocess.run(["say", "-r", str(rate), text], check=False)


def synth(text: str, rate: int = 150) -> bytes:
    """生成领读的 wav。rate 是词/分钟，150 算正常语速。"""
    if BACKEND == "say":
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "say.wav"
            subprocess.run(["say", "-r", str(rate), "--data-format=LEI16@22050", "-o", str(out), text], check=True)
            return out.read_bytes()

    import numpy as np

    lang = "en-gb" if VOICE.startswith("b") else "en-us"
    samples, sample_rate = load().create(text, voice=VOICE, speed=min(2.0, max(0.5, rate / 150)), lang=lang)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def load():
    """第一次用时下载 Kokoro 模型到 ~/.cache/speak-drill/kokoro/ 并加载。"""
    global _kokoro
    with _lock:
        if _kokoro is None:
            import requests
            from kokoro_onnx import Kokoro

            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            for name in MODEL_FILES:
                path = MODEL_DIR / name
                if not path.exists():
                    r = requests.get(_RELEASE + name, timeout=600)
                    r.raise_for_status()
                    tmp = path.with_suffix(".part")
                    tmp.write_bytes(r.content)
                    tmp.replace(path)
            _kokoro = Kokoro(str(MODEL_DIR / MODEL_FILES[0]), str(MODEL_DIR / MODEL_FILES[1]))
    return _kokoro
