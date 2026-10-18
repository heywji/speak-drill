import queue
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def record_until_enter(path: Path) -> np.ndarray:
    """回车开始前已由调用方确认；这里录到下一次回车为止，存 16k 单声道 wav。"""
    chunks: queue.Queue = queue.Queue()

    def callback(indata, frames, time, status):
        chunks.put(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback):
        input("  🎙  录音中…读完按回车结束 ")

    frames = []
    while not chunks.empty():
        frames.append(chunks.get())
    audio = np.concatenate(frames)[:, 0] if frames else np.zeros(0, dtype=np.int16)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return audio
