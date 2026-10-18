import subprocess


def say(text: str, rate: int = 150) -> None:
    subprocess.run(["say", "-r", str(rate), text], check=False)
