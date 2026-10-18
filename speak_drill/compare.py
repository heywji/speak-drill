import difflib
import re
from dataclasses import dataclass

# 识别器常把口语缩写/数字写成别的形式，比对前统一
_REPLACEMENTS = {
    "i'm": "i am",
    "it's": "it is",
    "you're": "you are",
    "don't": "do not",
    "esp 32": "esp32",
}


def normalize(text: str) -> list[str]:
    t = text.lower().replace("’", "'")
    t = re.sub(r"[-/]", " ", t)
    t = re.sub(r"[^a-z0-9' ]", " ", t)
    t = " ".join(t.split())
    for a, b in _REPLACEMENTS.items():
        t = re.sub(rf"\b{re.escape(a)}\b", b, t)
    # "A D B" → "adb"：连续的单字母并成一个缩写
    words = t.split()
    return _merge_letters(words)


def _merge_letters(words: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []
    for w in words + [""]:
        if len(w) == 1 and w.isalpha():
            run.append(w)
            continue
        if len(run) >= 2:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        if w:
            out.append(w)
    return out


@dataclass
class Result:
    ok: bool
    wer: float
    diff: str  # 给终端看的差异
    ops: list  # 给 GUI 用：[{"op": "equal"|"wrong", "want": str, "got": str}]


def compare(target: str, heard: str) -> Result:
    t, h = normalize(target), normalize(heard)
    sm = difflib.SequenceMatcher(a=t, b=h, autojunk=False)
    errors = 0
    parts = []
    ops = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        # "a db" 和 "adb"、"for mat" 和 "format" 只是空格不同，不算错
        if op == "equal" or "".join(t[i1:i2]) == "".join(h[j1:j2]):
            parts.append(" ".join(t[i1:i2]))
            ops.append({"op": "equal", "want": " ".join(t[i1:i2]), "got": " ".join(h[j1:j2])})
            continue
        errors += max(i2 - i1, j2 - j1)
        want = " ".join(t[i1:i2]) or "∅"
        got = " ".join(h[j1:j2]) or "∅"
        parts.append(f"\033[31m[{want} → {got}]\033[0m")
        ops.append({"op": "wrong", "want": " ".join(t[i1:i2]), "got": " ".join(h[j1:j2])})
    wer = min(errors / max(len(t), 1), 1.0)
    return Result(ok=errors == 0, wer=wer, diff=" ".join(p for p in parts if p), ops=ops)
