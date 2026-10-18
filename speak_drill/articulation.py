"""发音动画：把目标文本拆成音素，每个音素配 Seeing Speech 的口腔侧剖面动画 / 真人 MRI 视频。

视频来自格拉斯哥大学 Seeing Speech（https://www.seeingspeech.ac.uk/，CC BY-NC-ND 4.0），
第一次用到时下载到 ~/.cache/speak-drill/seeingspeech/，之后离线可用。
辅音用 2D 动画（1024×1024）；元音那边只有 MRI，用 MRI 2（320×320，2022 年录）。
"""

import json
import re
import subprocess
import threading
from collections import defaultdict
from pathlib import Path

import requests

BASE_URL = "https://www.seeingspeech.ac.uk/recording/"
CACHE_DIR = Path.home() / ".cache" / "speak-drill" / "seeingspeech"
# 站点会拦 python-requests 默认 UA，如实标明来源即可
USER_AGENT = "speak-drill/0.1 (personal pronunciation practice)"

# 视频片段：reference → (演示的音, 类型, Seeing Speech 的英文描述)
CLIPS = {
    "vl_bilabial_plosive": ("p", "anim", "Voiceless bilabial plosive"),
    "vd_bilabial_plosive": ("b", "anim", "Voiced bilabial plosive"),
    "vl_alveolar_plosive": ("t", "anim", "Voiceless alveolar plosive"),
    "vd_alveolar_plosive": ("d", "anim", "Voiced alveolar plosive"),
    "vl_velar_plosive": ("k", "anim", "Voiceless velar plosive"),
    "vd_velar_plosive": ("ɡ", "anim", "Voiced velar plosive"),
    "vd_bilabial_nasal": ("m", "anim", "Voiced bilabial nasal"),
    "vd_alveolar_nasal": ("n", "anim", "Voiced alveolar nasal"),
    "vd_velar_nasal": ("ŋ", "anim", "Voiced velar nasal"),
    "vl_labiodental_fricative": ("f", "anim", "Voiceless labiodental fricative"),
    "vd_labiodental_fricative": ("v", "anim", "Voiced labiodental fricative"),
    "vl_dental_fricative": ("θ", "anim", "Voiceless dental fricative"),
    "vd_dental_fricative": ("ð", "anim", "Voiced dental fricative"),
    "vl_alveolar_fricative": ("s", "anim", "Voiceless alveolar fricative"),
    "vd_alveolar_fricative": ("z", "anim", "Voiced alveolar fricative"),
    "vl_postalveolar_fricative": ("ʃ", "anim", "Voiceless postalveolar fricative"),
    "vd_postalveolar_fricative": ("ʒ", "anim", "Voiced postalveolar fricative"),
    "vl_glottal_fricative": ("h", "anim", "Voiceless glottal fricative"),
    "vl_postalveolar_affricate": ("tʃ", "anim", "Voiceless postalveolar affricate"),
    "vd_postalveolar_affricate": ("dʒ", "anim", "Voiced postalveolar affricate"),
    "vd_alveolar_lateral_approximant": ("l", "anim", "Voiced alveolar lateral approximant"),
    "vd_alveolar_approximant": ("ɹ", "anim", "Voiced alveolar approximant"),
    "vd_palatal_approximant": ("j", "anim", "Voiced palatal approximant"),
    "vd_labial_velar_approximant": ("w", "anim", "Voiced labial-velar approximant"),
    "vd_alveolar_tap": ("ɾ", "anim", "Voiced alveolar tap"),
    "vl_glottal_plosive": ("ʔ", "anim", "Voiceless glottal plosive"),
    "MRI2_cardinal_1_vowel_overdubbed": ("i", "mri", "Front close unrounded vowel"),
    "MRI2_front_close_float_vowel": ("ɪ", "mri", "Front close unrounded float vowel"),
    "MRI2_cardinal_2_vowel": ("e", "mri", "Front close-mid unrounded vowel"),
    "MRI2_cardinal_3_vowel": ("ɛ", "mri", "Front open-mid unrounded vowel"),
    "MRI2_cardinal_4_vowel_overdubbed": ("a", "mri", "Front open unrounded vowel"),
    "MRI2_cardinal_14_vowel": ("ʌ", "mri", "Back open-mid unrounded vowel"),
    "MRI2_cardinal_5_vowel": ("ɑ", "mri", "Back open unrounded vowel"),
    "MRI2_cardinal_13_vowel": ("ɒ", "mri", "Back open rounded vowel"),
    "MRI2_cardinal_6_vowel": ("ɔ", "mri", "Back open-mid rounded vowel"),
    "MRI2_cardinal_7_vowel": ("o", "mri", "Back close-mid rounded vowel"),
    "MRI2_back_close_float_vowel": ("ʊ", "mri", "Back close rounded float vowel"),
    "MRI2_cardinal_8_vowel_overdubbed": ("u", "mri", "Back close rounded vowel"),
    "MRI2_central_schwa_float_vowel": ("ə", "mri", "Central vowel (schwa)"),
}
_C = {sym: ref for ref, (sym, _, _) in CLIPS.items()}  # 演示的音 → reference
_STOPS = {"p", "b", "t", "d", "k", "ɡ", "ɾ", "ʔ"}

# 英语音素：key → (片段, 中文名, 要领, 近似说明)。双元音按两个元音依次播放。
PHONES = {
    "p": ([_C["p"]], "清双唇塞音", "双唇紧闭憋住气，突然张开送气；声带不振动。", ""),
    "b": ([_C["b"]], "浊双唇塞音", "口型同 p，但声带振动、几乎不送气。", ""),
    "t": ([_C["t"]], "清齿龈塞音", "舌尖抵住上齿龈（上门牙后面那道硬棱），突然放开送气；不是顶牙齿。", ""),
    "d": ([_C["d"]], "浊齿龈塞音", "舌位同 t，声带振动；词尾的 d 要轻轻发出来，别吞掉或读成 t。", ""),
    "k": ([_C["k"]], "清软腭塞音", "舌后部抬起抵住软腭，突然放开送气。", ""),
    "ɡ": ([_C["ɡ"]], "浊软腭塞音", "舌位同 k，声带振动。", ""),
    "m": ([_C["m"]], "双唇鼻音", "双唇闭合，气流从鼻腔出；词尾 m 要把嘴闭上收住。", ""),
    "n": ([_C["n"]], "齿龈鼻音", "舌尖抵上齿龈，气流从鼻腔出；词尾 n 舌尖要顶住，别滑成 ng。", ""),
    "ŋ": ([_C["ŋ"]], "软腭鼻音", "舌后部抵软腭，气流从鼻腔出（sing 的结尾），后面不要带出 g。", ""),
    "f": ([_C["f"]], "清唇齿擦音", "上齿轻贴下唇，气流从缝里摩擦而出；声带不振动。", ""),
    "v": ([_C["v"]], "浊唇齿擦音", "口型同 f，声带振动；上齿一定要碰到下唇，别读成 w。", ""),
    "θ": ([_C["θ"]], "清齿擦音", "舌尖轻放在上下齿之间，气流从舌齿缝里挤出；别读成 s 或 f。", ""),
    "ð": ([_C["ð"]], "浊齿擦音", "舌位同 θ，声带振动；别读成 z 或 d。", ""),
    "s": ([_C["s"]], "清齿龈擦音", "舌尖靠近上齿龈但不碰，留一道窄缝，气流嘶嘶地摩擦。", ""),
    "z": ([_C["z"]], "浊齿龈擦音", "舌位同 s，声带振动，像蜜蜂嗡嗡。", ""),
    "ʃ": ([_C["ʃ"]], "清齿龈后擦音", "舌身抬向齿龈后部，双唇略向前突出，送气摩擦（比汉语 sh 更圆唇、舌位更靠前）。", ""),
    "ʒ": ([_C["ʒ"]], "浊齿龈后擦音", "舌位同 ʃ，声带振动（usual、vision 中间那个音）。", ""),
    "h": ([_C["h"]], "清声门擦音", "口腔保持后面元音的口型，气流从喉咙轻轻呼出；不要像汉语 h 那样在舌根摩擦。", ""),
    "tʃ": ([_C["tʃ"]], "清齿龈后塞擦音", "舌尖先抵住齿龈后部堵住气流，再放开成 ʃ，双唇略突出。", ""),
    "dʒ": ([_C["dʒ"]], "浊齿龈后塞擦音", "舌位同 tʃ，声带振动。", ""),
    "l": ([_C["l"]], "齿龈边近音", "舌尖抵上齿龈，气流从舌头两侧流出；词尾和辅音前的 l 舌后部同时抬起，别读成「欧」。", ""),
    "ɹ": ([_C["ɹ"]], "齿龈近音", "舌尖向上卷起靠近上腭但不碰，或舌身后缩隆起，双唇略圆。", ""),
    "j": ([_C["j"]], "硬腭近音", "舌面抬向硬腭，像很短的「衣」，马上滑向后面的元音。", ""),
    "w": ([_C["w"]], "唇软腭近音", "双唇收圆突出、舌后部抬起，像很短的「乌」，马上滑向后面的元音；牙齿别碰嘴唇（那是 v）。", ""),
    "ɾ": ([_C["ɾ"]], "齿龈闪音", "舌尖快速轻弹一下上齿龈（美式 water、better 里的 t）。", ""),
    "ʔ": ([_C["ʔ"]], "声门塞音", "声门瞬间闭合再放开（美式 button 中间的 t）。", ""),
    "iː": ([_C["i"]], "长元音", "舌前部抬到最高，嘴角向两边展开，拉长（see）。", ""),
    "ɪ": ([_C["ɪ"]], "短元音", "比 iː 舌位低一点、更放松，短促（sit）；别读成「衣」。", ""),
    "e": ([_C["ɛ"]], "短元音", "嘴半开，舌前部半低，短促（bed）。", ""),
    "æ": ([_C["a"]], "短元音", "嘴张大、下巴放低，舌前部压低，嘴角略往两边拉（cat），介于「哎」和「啊」之间。",
          "Seeing Speech 没有 æ，用最接近的 [a] 示意"),
    "ʌ": ([_C["ʌ"]], "短元音", "嘴半开，舌位居中偏后，短促有力（cup），像短的「阿」。", ""),
    "ɑː": ([_C["ɑ"]], "长元音", "嘴张大，舌位低而靠后，拉长（car），像放低下巴的「啊」。", ""),
    "ɒ": ([_C["ɒ"]], "短元音", "嘴张大、双唇略圆，舌位低靠后，短促（hot）。", ""),
    "ɔː": ([_C["ɔ"]], "长元音", "双唇收圆向前突出，舌后部半低，拉长（call）。", ""),
    "o": ([_C["o"]], "元音", "双唇收圆，舌后部半高。", ""),
    "ʊ": ([_C["ʊ"]], "短元音", "双唇略圆、放松，舌后部抬高，短促（book）；别读成「乌」。", ""),
    "uː": ([_C["u"]], "长元音", "双唇收圆突出，舌后部抬到最高，拉长（food）。", ""),
    "ɜː": ([_C["ə"]], "长元音", "舌位居中、嘴唇放松半开，拉长（bird）；英式不卷舌。", "Seeing Speech 没有 ɜ，用舌位最接近的 [ə] 示意"),
    "ə": ([_C["ə"]], "弱读元音", "舌头完全放松、居中，又轻又短（about 的 a）。", ""),
    "eɪ": ([_C["e"], _C["ɪ"]], "双元音", "从 e 滑向 ɪ，前长后短（day）；别读成单个「诶」。", ""),
    "aɪ": ([_C["a"], _C["ɪ"]], "双元音", "从 a 滑向 ɪ，嘴从张大到收小（my）。", ""),
    "ɔɪ": ([_C["ɔ"], _C["ɪ"]], "双元音", "从 ɔ 滑向 ɪ（boy）。", ""),
    "əʊ": ([_C["ə"], _C["ʊ"]], "双元音", "从 ə 滑向 ʊ，双唇逐渐收圆（go，英式）；别读成「欧」。", ""),
    "oʊ": ([_C["o"], _C["ʊ"]], "双元音", "从 o 滑向 ʊ，双唇逐渐收圆（go，美式）。", ""),
    "aʊ": ([_C["a"], _C["ʊ"]], "双元音", "从 a 滑向 ʊ，嘴从张大到收圆（now）。", ""),
    "ɪə": ([_C["ɪ"], _C["ə"]], "双元音", "从 ɪ 滑向 ə（near，英式）。", ""),
    "eə": ([_C["ɛ"], _C["ə"]], "双元音", "从 e 滑向 ə（hair，英式）。", ""),
    "ʊə": ([_C["ʊ"], _C["ə"]], "双元音", "从 ʊ 滑向 ə（tour，英式）。", ""),
    "ɚ": ([_C["ə"], _C["ɹ"]], "卷舌弱元音", "弱读的 ə 同时卷舌（美式 teacher 的 -er）。", ""),
    "ɝ": ([_C["ə"], _C["ɹ"]], "卷舌长元音", "舌位居中同时卷舌（美式 bird）。", "Seeing Speech 没有 ɜ，用 [ə] + [ɹ] 示意"),
}
VOWELS = {k for k, (clips, *_) in PHONES.items() if CLIPS[clips[0]][1] == "mri"}

# 各种写法 → PHONES 里的 key
_ALIASES = {
    "i": "iː", "u": "uː", "ɑ": "ɑː", "ɔ": "ɔː", "ɜ": "ɜː", "əː": "ɜː", "ɛ": "e", "ɛə": "eə", "a": "æ",
    "r": "ɹ", "g": "ɡ", "ɫ": "l", "ɐ": "ʌ", "ᵻ": "ɪ", "ʧ": "tʃ", "ʤ": "dʒ", "t͡ʃ": "tʃ", "d͡ʒ": "dʒ",
    "ɒː": "ɔː", "ɚː": "ɝ",
}
_SYMBOLS = sorted(set(PHONES) | set(_ALIASES), key=len, reverse=True)  # 最长匹配

# CMU 词典（ARPAbet，美式）→ IPA；AH / ER 按是否重读分开
_ARPABET = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ɝ", "EY": "eɪ",
    "IH": "ɪ", "IY": "i", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ", "K": "k",
    "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t",
    "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
# 缩写逐个字母读
_LETTERS = {
    "a": "ˈeɪ", "b": "ˈbi", "c": "ˈsi", "d": "ˈdi", "e": "ˈi", "f": "ˈɛf", "g": "ˈdʒi", "h": "ˈeɪtʃ",
    "i": "ˈaɪ", "j": "ˈdʒeɪ", "k": "ˈkeɪ", "l": "ˈɛl", "m": "ˈɛm", "n": "ˈɛn", "o": "ˈoʊ", "p": "ˈpi",
    "q": "ˈkju", "r": "ˈɑɹ", "s": "ˈɛs", "t": "ˈti", "u": "ˈju", "v": "ˈvi", "w": "ˈdʌbəlju",
    "x": "ˈɛks", "y": "ˈwaɪ", "z": "ˈzi",
}
_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
# 可以放在重读音节开头的辅音组合，只用来决定重音符号 ˈ 标在哪
_ONSETS = {
    "pl", "pɹ", "bl", "bɹ", "tɹ", "dɹ", "kl", "kɹ", "ɡl", "ɡɹ", "fl", "fɹ", "θɹ", "ʃɹ", "sp", "st", "sk",
    "sm", "sn", "sl", "sw", "tw", "dw", "kw", "ɡw", "pj", "bj", "kj", "fj", "vj", "mj", "hj",
    "spl", "spɹ", "stɹ", "skɹ", "skw", "spj", "skj",
}

_cmu = None


def _cmudict() -> dict:
    global _cmu
    if _cmu is None:
        import cmudict

        _cmu = cmudict.dict()
    return _cmu


def hint_ipa(hint: str) -> str:
    """提示开头 /.../ 里的音标；没有或不像音标就返回空串。"""
    m = re.match(r"\s*/([^/]+)/", hint or "")
    if not m or re.search(r"[一-鿿]", m.group(1)):
        return ""
    return m.group(1).strip()


def parse_ipa(ipa: str) -> list[dict]:
    """IPA 字符串 → [{sym, key, stress}]，认不出的字符跳过。"""
    s = ipa.replace(":", "ː").replace("'", "ˈ")
    phones, stress, i = [], 0, 0
    while i < len(s):
        ch = s[i]
        if ch in "ˈˌ":
            stress = 1 if ch == "ˈ" else 2
            i += 1
            continue
        sym = next((x for x in _SYMBOLS if s.startswith(x, i)), None)
        if sym is None:
            i += 1
            continue
        key = _ALIASES.get(sym, sym)
        ph = {"sym": sym, "key": key, "stress": 0}
        if key in VOWELS:
            ph["stress"], stress = stress, 0
        phones.append(ph)
        i += len(sym)
    return phones


def tokens(text: str) -> list[str]:
    """按空格、连字符、斜杠切词，去掉标点（保留撇号和大小写）。"""
    out = []
    for w in re.split(r"[\s\-/]+", text.replace("’", "'")):
        w = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", w)
        if w:
            out.append(w)
    return out


def build_lexicon(items: list[tuple[str, str]]) -> dict[str, str]:
    """从练习提示里收集单词音标（词数和音标段数对得上的才算），句子里遇到同一个词优先用它。"""
    lex = {}
    for target, hint in items:
        ipa = hint_ipa(hint)
        words, parts = tokens(target), ipa.split()
        if ipa and len(words) == len(parts):
            for w, p in zip(words, parts):
                lex.setdefault(w.lower(), p)
    return lex


def _number_words(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    return [_ONES[int(d)] for d in str(n)]


def _from_arpabet(pron: list[str]) -> list[dict]:
    phones = []
    for p in pron:
        base, st = p.rstrip("012"), p[len(p.rstrip("012")):]
        sym = _ARPABET[base]
        if base == "AH" and st == "0":
            sym = "ə"
        elif base == "ER" and st == "0":
            sym = "ɚ"
        key = _ALIASES.get(sym, sym)
        phones.append({"sym": sym, "key": key, "stress": int(st) if st and st != "0" else 0})
    return phones


def _ipa_string(phones: list[dict]) -> str:
    """按音素拼回 IPA，重音符号放在重读音节的开头。"""
    syms = [p["sym"] for p in phones]
    marks: dict[int, str] = {}
    prev_vowel = -1
    for i, p in enumerate(phones):
        if p["key"] not in VOWELS:
            continue
        if p["stress"]:
            cons = syms[prev_vowel + 1 : i]
            k = len(cons) if prev_vowel < 0 else next(
                (k for k in (3, 2) if len(cons) >= k and "".join(cons[-k:]) in _ONSETS), min(len(cons), 1)
            )
            marks[i - k] = "ˈ" if p["stress"] == 1 else "ˌ"
        prev_vowel = i
    return "".join(marks.get(i, "") + s for i, s in enumerate(syms))


def _word_phones(word: str, lexicon: dict[str, str]) -> tuple[list[dict], str, str]:
    """单个词 → (音素, 来源, 显示的音标)。顺序：练习提示里的音标 > 缩写/数字 > CMU 词典。"""
    low = word.lower()
    if low in lexicon:
        return parse_ipa(lexicon[low]), "hint", lexicon[low]
    parts = re.findall(r"[A-Za-z']+|\d+", word)
    if len(parts) > 1:  # ESP32 → ESP + 32
        res = [_word_phones(part, lexicon) for part in parts]
        return [p for r in res for p in r[0]], "cmu", " ".join(r[2] for r in res if r[2])
    cmu = _cmudict()
    if word.isdigit():
        res = [_from_arpabet(cmu[w][0]) for w in _number_words(int(word))]
        return [p for r in res for p in r], "cmu", " ".join(_ipa_string(r) for r in res)
    if (word.isupper() and len(word) >= 2) or (low not in cmu and len(word) <= 3 and word.isalpha()):
        letters = [_LETTERS[c] for c in low if c in _LETTERS]
        return parse_ipa("".join(letters)), "cmu", " ".join(letters)
    if low in cmu:
        phones = _from_arpabet(cmu[low][0])
        return phones, "cmu", _ipa_string(phones)
    return [], "unknown", ""


def analyze(text: str, hint: str, lexicon: dict[str, str]) -> dict:
    """给前端：按词分组的音素 + 每个音素的演示片段和要领。"""
    from .compare import normalize

    words = []
    ipa = hint_ipa(hint)
    if ipa:
        # 提示里写了音标就按它来（就是在练的那个口音）；词数对得上时给每段配上原词
        parts, toks = ipa.split(), tokens(text)
        labels = toks if len(toks) == len(parts) else [text] * len(parts) if len(toks) == 1 else [""] * len(parts)
        for label, part in zip(labels, parts):
            words.append({"text": label, "ipa": part, "phones": parse_ipa(part), "source": "hint"})
    else:
        for tok in tokens(text):
            phones, source, shown = _word_phones(tok, lexicon)
            words.append({"text": tok, "ipa": shown, "phones": phones, "source": source})
    for w in words:
        w["norm"] = normalize(w["text"]) if w["text"] else []

    used = {p["key"] for w in words for p in w["phones"]}
    phones = {}
    for key in used:
        clips, zh, tip, approx = PHONES[key]
        phones[key] = {"clips": clips, "zh": zh, "tip": tip, "approx": approx, "vowel": key in VOWELS}
    clips = {}
    for ref in {ref for p in phones.values() for ref in p["clips"]}:
        sym, kind, en = CLIPS[ref]
        # 每段视频是一整套示范：元音「V、VpV、VtV」，辅音「C、əCə」，塞音没法单独发只有「əCə」
        if kind == "mri":
            short, full = f"真人 MRI · {sym}", f"真人 MRI · {sym} → {sym}p{sym} → {sym}t{sym}"
            if sym == "ə":
                full = "真人 MRI · ə → ətə"
        elif sym in _STOPS:
            short = full = f"动画 · ə{sym}ə"
        else:
            short, full = f"动画 · {sym}", f"动画 · {sym} → ə{sym}ə"
        try:
            window = clip_window(ref)
        except Exception:
            window = None  # 下不到或分析失败就放整段
        clips[ref] = {"sym": sym, "kind": kind, "en": en, "short": short, "full": full, "window": window}
    return {"words": words, "phones": phones, "clips": clips}


# ---- 视频缓存 ----

_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def clip_path(ref: str) -> Path:
    """本地缓存的视频路径，没有就先从 Seeing Speech 下载。"""
    if ref not in CLIPS:
        raise KeyError(ref)
    path = CACHE_DIR / f"{ref}.mp4"
    with _locks_guard:
        lock = _locks[ref]
    with lock:
        if not path.exists():
            r = requests.get(BASE_URL + f"{ref}.mp4", headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            if not r.headers.get("Content-Type", "").startswith("video/"):
                raise RuntimeError(f"Seeing Speech 返回的不是视频：{r.headers.get('Content-Type')}")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(path)
    return path


def clip_window(ref: str) -> list[float] | None:
    """默认播放区间 [开始, 结束] 秒：只放「单独发一次」那段，塞音放整段 əCə。

    用 ffmpeg silencedetect 在缓存的视频上找第一段有声音的地方，结果存成 <ref>.json。
    """
    path = clip_path(ref)
    meta = path.with_suffix(".json")
    if meta.exists():
        return json.loads(meta.read_text())["window"]
    err = subprocess.run(
        ["ffmpeg", "-nostats", "-i", str(path), "-af", "silencedetect=noise=-30dB:d=0.2", "-f", "null", "-"],
        capture_output=True, text=True, check=True,
    ).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    dur = int(h) * 3600 + int(m) * 60 + float(s)
    segs, start = [], 0.0
    for ev, t in re.findall(r"silence_(start|end): ([\d.]+)", err):
        if ev == "start":
            segs.append((start, float(t)))
        else:
            start = float(t)
    segs.append((start, dur))
    segs = [(a, b) for a, b in segs if b - a >= 0.15]  # 去掉开头的爆音/零长度片段
    if not segs:
        window = None
    elif CLIPS[ref][0] in _STOPS:
        window = [0.0, round(dur, 2)]
    else:
        # 前面留一点看口型怎么摆好，后面留一点看怎么收
        window = [round(max(0.0, segs[0][0] - 0.6), 2), round(min(dur, segs[0][1] + 0.4), 2)]
    tmp = meta.with_suffix(".json.part")
    tmp.write_text(json.dumps({"window": window, "segments": [[round(a, 2), round(b, 2)] for a, b in segs]}))
    tmp.replace(meta)
    return window


def prefetch(refs) -> None:
    """后台把这一条要用的视频都先下好、算好播放区间，点哪个音都不用等。"""
    def run():
        for ref in refs:
            try:
                clip_window(ref)
            except Exception:
                pass  # 真要播的时候再报错

    threading.Thread(target=run, daemon=True).start()
