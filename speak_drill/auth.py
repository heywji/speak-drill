"""登录：设了环境变量 SPEAK_DRILL_PASSWORD 才启用（部署到服务器时用，本机不设就不用登录）。

会话是签名 Cookie：{过期时间}.{HMAC(密钥, 过期时间|密码摘要)}，改密码后旧 Cookie 自动失效。
签名密钥第一次启动时随机生成，存在 <数据目录>/.session-secret。
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path

COOKIE = "sd_session"
SESSION_SECONDS = 30 * 86400
MAX_FAILS, FAIL_WINDOW = 10, 15 * 60  # 同一 IP 15 分钟内错 10 次就先锁住


class Auth:
    def __init__(self, password: str, secret_file: Path):
        self.password = password
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        if password:
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            if not secret_file.exists():
                secret_file.write_bytes(secrets.token_bytes(32))
                secret_file.chmod(0o600)
            self.secret = secret_file.read_bytes()

    @property
    def enabled(self) -> bool:
        return bool(self.password)

    def _sign(self, exp: int) -> str:
        digest = hashlib.sha256(self.password.encode()).hexdigest()
        return hmac.new(self.secret, f"{exp}|{digest}".encode(), hashlib.sha256).hexdigest()

    def new_session(self) -> str:
        exp = int(time.time()) + SESSION_SECONDS
        return f"{exp}.{self._sign(exp)}"

    def valid(self, cookie_header: str | None) -> bool:
        if not self.enabled:
            return True
        morsel = SimpleCookie(cookie_header or "").get(COOKIE)
        if not morsel or "." not in morsel.value:
            return False
        exp, sig = morsel.value.split(".", 1)
        return exp.isdigit() and int(exp) > time.time() and hmac.compare_digest(sig, self._sign(int(exp)))

    def locked(self, ip: str) -> bool:
        with self._lock:
            recent = [t for t in self._fails.get(ip, []) if t > time.time() - FAIL_WINDOW]
            self._fails[ip] = recent
            return len(recent) >= MAX_FAILS

    def login(self, ip: str, password: str) -> bool:
        if hmac.compare_digest(password.encode(), self.password.encode()):
            with self._lock:
                self._fails.pop(ip, None)
            return True
        with self._lock:
            self._fails.setdefault(ip, []).append(time.time())
        time.sleep(1)  # 拖慢猜密码
        return False


def from_env(data_dir: Path) -> Auth:
    return Auth(os.environ.get("SPEAK_DRILL_PASSWORD", ""), data_dir / ".session-secret")
