import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import analyze, asr, compare, tts

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def load_drills(path: Path) -> list[tuple[str, str]]:
    items = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        target, _, hint = line.partition("|")
        items.append((target.strip(), hint.strip()))
    return items


def run_item(target: str, hint: str, args, outdir: Path) -> dict:
    """一条练习：领读 → 最多 tries 次跟读 → 全错则送去分析。"""
    from .record import record_until_enter

    print(f"\n━━ {target}")
    if hint:
        print(f"{DIM}   {hint}{RESET}")
    tts.say(target, args.rate)

    attempts: list[str] = []
    wav = None
    while len(attempts) < args.tries:
        cmd = input(f"  [{len(attempts) + 1}/{args.tries}] 回车开始录音，r 重听，s 跳过，q 退出 > ").strip().lower()
        if cmd == "r":
            tts.say(target, args.rate)
            continue
        if cmd == "s":
            return {"target": target, "result": "skipped", "attempts": attempts}
        if cmd == "q":
            raise KeyboardInterrupt
        wav = outdir / f"{_slug(target)}-{len(attempts) + 1}.wav"
        record_until_enter(wav)
        heard = asr.transcribe(wav, args.asr_model)
        attempts.append(heard)
        res = compare.compare(target, heard)
        print(f"  识别：{heard!r}")
        if res.ok:
            print(f"  {GREEN}✔ 通过{RESET}")
            return {"target": target, "result": "pass", "attempts": attempts}
        print(f"  ✘ {res.diff}  (词错率 {res.wer:.0%})")

    if not analyze.enabled():
        print(f"  {args.tries} 次没读对。")
        return {"target": target, "result": "fail", "attempts": attempts}
    print(f"  {args.tries} 次没读对，发送录音去分析…")
    try:
        reply = analyze.analyze(wav, target, attempts, hint, args.gemini_model)
    except Exception as e:  # 分析失败不影响继续练
        print(f"  {RED}分析失败：{e}{RESET}")
        return {"target": target, "result": "fail", "attempts": attempts, "analysis_error": str(e)}
    print(f"\n{reply}\n")
    (outdir / f"{_slug(target)}-analysis.md").write_text(reply)
    return {"target": target, "result": "fail", "attempts": attempts, "analysis": reply}


def _slug(text: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in text.lower())
    return "_".join(filter(None, s.split("_")))[:40]


def cmd_drill(args) -> None:
    items = load_drills(Path(args.file))
    outdir = Path(args.out) / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for target, hint in items:
            results.append(run_item(target, hint, args, outdir))
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
    (outdir / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print("\n━━ 汇总")
    for r in results:
        mark = {"pass": f"{GREEN}✔{RESET}", "fail": f"{RED}✘{RESET}", "skipped": "–"}[r["result"]]
        print(f"  {mark} {r['target']}  ({len(r['attempts'])} 次)")
    print(f"{DIM}录音和分析保存在 {outdir}{RESET}")


def cmd_check(args) -> None:
    """不用麦克风：拿现成 wav 测识别 + 比对（可选再送分析）。"""
    wav = Path(args.wav)
    heard = asr.transcribe(wav, args.asr_model)
    res = compare.compare(args.target, heard)
    print(f"识别：{heard!r}")
    print(f"{GREEN}✔ 通过{RESET}" if res.ok else f"✘ {res.diff}  (词错率 {res.wer:.0%})")
    if args.analyze and not analyze.enabled():
        print("没配置 AI 分析，跳过。")
    elif args.analyze:
        print(analyze.analyze(wav, args.target, [heard], model=args.gemini_model))
    sys.exit(0 if res.ok else 1)


def cmd_gui(args) -> None:
    from .server import serve

    serve(Path(args.drills), Path(args.out), args.asr_model, args.gemini_model, args.port, not args.no_browser, args.host)


def main() -> None:
    p = argparse.ArgumentParser(prog="speak-drill", description="跟读发音练习")
    p.add_argument("--rate", type=int, default=150, help="say 语速（词/分钟），默认 150")
    p.add_argument("--asr-model", default=asr.DEFAULT_MODEL, help="Whisper 模型（macOS 用 mlx，Linux 用 faster-whisper）")
    p.add_argument("--gemini-model", default=analyze.DEFAULT_MODEL)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("drill", help="按练习文件逐条跟读")
    d.add_argument("file")
    d.add_argument("--tries", type=int, default=3)
    d.add_argument("--out", default="recordings")
    d.set_defaults(func=cmd_drill)

    s = sub.add_parser("say", help="只让电脑读一遍")
    s.add_argument("text")
    s.set_defaults(func=lambda a: tts.say(a.text, a.rate))

    c = sub.add_parser("check", help="用现成 wav 测识别比对（调试用）")
    c.add_argument("wav")
    c.add_argument("target")
    c.add_argument("--analyze", action="store_true", help="同时做 AI 分析")
    c.set_defaults(func=cmd_check)

    g = sub.add_parser("gui", help="打开图形界面（本地网页）")
    g.add_argument("--drills", default=str(Path(__file__).resolve().parent.parent / "drills"), help="练习文件目录")
    g.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "recordings"))
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--host", default="127.0.0.1", help="监听地址，容器里用 0.0.0.0")
    g.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    g.set_defaults(func=cmd_gui)

    args = p.parse_args()
    args.func(args)
