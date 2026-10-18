"""AI 发音分析：同一条连续读错几次后，把最后一次录音 + 最近几次识别结果发给大模型，让它指出具体哪个音素有问题。

开源版把 token 和调用中转服务的部分注释掉了，enabled() 恒为 False，界面和命令行会跳过分析、只做 Whisper 比对。
想自己接上：在 analyze() 里把 message（提示词）和 wav（16k 单声道录音）发给任何能听音频的模型，
返回它的文字回复，再让 enabled() 返回 True。
"""

import os  # noqa: F401  （下面注释掉的代码会用到）
from pathlib import Path

# import base64
# import requests

# RELAY_URL = os.environ.get("SPEAK_DRILL_URL", "https://your-relay.example.com/chat")
DEFAULT_MODEL = "gemini-3.7-flash"
TOKEN_FILE = Path.home() / ".config" / "speak-drill" / "token"

PROMPT = """你是英语发音教练，学生母语是中文。附件录音是学生朗读下面这句目标文本的第 {n} 次尝试。

目标文本：{target}
{hint}语音识别（Whisper）对这 {n} 次的识别结果：
{attempts}

请直接听录音，用中文回答：
1. 哪些词读错了，具体是哪个音素（用 IPA 标出学生实际发的音 vs 标准音）、重音、连读或吞音的问题；
2. 为什么识别器会听成上面那些词；
3. 每个问题给一个可操作的纠正方法（口型/舌位/练习用的最小对立词）。
简洁，不要客套。"""


def enabled() -> bool:
    """开源版默认关闭 AI 分析。"""
    return False
    # return bool(os.environ.get("SPEAK_DRILL_TOKEN") or TOKEN_FILE.exists())


# def _token() -> str:
#     tok = os.environ.get("SPEAK_DRILL_TOKEN")
#     if tok:
#         return tok.strip()
#     if TOKEN_FILE.exists():
#         return TOKEN_FILE.read_text().strip()
#     raise SystemExit(f"缺少 token：设置 SPEAK_DRILL_TOKEN 或写入 {TOKEN_FILE}")


def analyze(wav: Path, target: str, attempts: list[str], hint: str = "", model: str = DEFAULT_MODEL) -> str:
    message = PROMPT.format(
        n=len(attempts),
        target=target,
        hint=f"发音提示：{hint}\n" if hint else "",
        attempts="\n".join(f"  第{i}次：{a or '（空）'}" for i, a in enumerate(attempts, 1)),
    )
    raise RuntimeError("开源版没有接 AI 分析，见 speak_drill/analyze.py")
    # payload = {
    #     "message": message,
    #     "model": model,
    #     "files": [{"data": base64.b64encode(wav.read_bytes()).decode(), "mime_type": "audio/wav", "name": wav.name}],
    # }
    # resp = requests.post(RELAY_URL, json=payload, headers={"Authorization": f"Bearer {_token()}"}, timeout=300)
    # body = resp.json()
    # if not body.get("success"):
    #     raise RuntimeError(f"分析服务报错：{body.get('error')}")
    # return body["data"]["reply"]
