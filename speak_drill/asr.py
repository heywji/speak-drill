import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# macOS 用 mlx-whisper（Apple 芯片）；Linux 服务器用 faster-whisper（CPU int8），模型同是 small.en
BACKEND = os.environ.get("SPEAK_DRILL_ASR", "mlx" if sys.platform == "darwin" else "faster")
DEFAULT_MODEL = "mlx-community/whisper-small.en-mlx" if BACKEND == "mlx" else "small.en"
_models: dict = {}


def transcribe(wav: Path, model: str = DEFAULT_MODEL) -> str:
    # 不给 initial_prompt：不把目标文本透露给识别器，免得它"脑补"成正确答案
    if BACKEND == "mlx":
        import mlx_whisper

        result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language="en", temperature=0.0)
        return result["text"].strip()

    import wave

    import numpy as np
    from faster_whisper import WhisperModel

    if model not in _models:
        _models[model] = WhisperModel(model, device="cpu", compute_type="int8")
    # 传进来的都是 ffmpeg 转好的 16k 单声道 wav，自己读成数组：faster-whisper 自带的解码
    # 依赖 PyAV，新版 PyAV 去掉了它用的 metadata_errors 参数，会直接报 TypeError
    with wave.open(str(wav)) as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    # temperature=0：没把握时 faster-whisper 默认会升温重新解码好几遍（长篇转写防跑偏用的），
    # 跟读的短录音用不着，服务器上一条读歪的 3 秒录音因此从 4 秒拖到 28 秒；时间戳也用不着
    segments, _ = _models[model].transcribe(audio, language="en", beam_size=5, temperature=0.0, without_timestamps=True)
    return " ".join(s.text.strip() for s in segments).strip()
