import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

DEFAULT_MODEL = "mlx-community/whisper-small.en-mlx"


def transcribe(wav: Path, model: str = DEFAULT_MODEL) -> str:
    import mlx_whisper

    # 不给 initial_prompt：不把目标文本透露给识别器，免得它"脑补"成正确答案
    result = mlx_whisper.transcribe(str(wav), path_or_hf_repo=model, language="en")
    return result["text"].strip()
