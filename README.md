# speak-drill

英语跟读发音练习：电脑领读，你跟着读，本地 Whisper 识别后逐词比对，读错的词标出来。
每个音素都配了口腔侧剖面动画（辅音）和真人 MRI 视频（元音），能看到舌头、嘴唇该怎么动。

- **macOS + Apple 芯片**：领读用系统自带的 `say`，识别用 mlx-whisper，一条不到 1 秒。图形界面和命令行都能用。
- **Linux**（比如放在服务器上用）：领读用 [Kokoro](https://github.com/thewh1teagle/kokoro-onnx)（离线神经网络 TTS，默认英音女声），
  识别用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（CPU）。只支持图形界面，见下面的「服务器 / 容器」。

## 安装

需要 [uv](https://docs.astral.sh/uv/) 和 ffmpeg：

```bash
brew install ffmpeg          # Linux：apt install ffmpeg
git clone https://github.com/heywji/speak-drill.git
cd speak-drill
uv sync
```

第一次识别会下载 Whisper 模型（约 500MB），第一次启动图形界面会下载发音动画视频（约 12MB），Linux 上还会下载 Kokoro 模型（约 90MB），之后都离线可用。

## 图形界面

```bash
uv run speak-drill gui      # 启动 http://127.0.0.1:8765/ 并自动打开浏览器
```

左边选关卡和条目，也可以输入任意句子做自由练习。按 **空格** 开始/结束录音，**L** 听领读，**M** 回放自己的录音，**P** 连播口型动画，**← →** 切换条目。
读错的词会标成 ~~目标~~ → 识别结果。尝试次数不限，最新的一次在最上面，每次旁边的 🔊 可以回放那一次的录音。
语速滑块在左下角。录音保存在 `recordings/<时间>/`（每次识别会追加一行到 `log.jsonl`）。
服务默认只监听 127.0.0.1，录音在浏览器里录，第一次使用要允许麦克风权限。

### 发音动画

右边（窄屏时在下面）的面板把当前条目拆成音素：点音标看口型，点单词连播这个词，最近一次没读对的词会标红。

- 辅音是 [Seeing Speech](https://www.seeingspeech.ac.uk/) 的 2D 侧剖面动画；元音它只有真人 MRI，就放 MRI 视频。双元音按两个元音依次播放。
  Seeing Speech 没有 æ 和 ɜ，分别用最接近的 [a]、[ə] 示意，页面上会注明。
- 每段视频本来是一整套示范（元音「V、VpV、VtV」，辅音「C、əCə」，塞音只有「əCə」），所以默认只放单独发音那一下，勾「完整示范」才整段放。
  播放区间用 ffmpeg silencedetect 自动找。
- 元音视频是语音学家在扫描仪里发的标准元音（cardinal vowels），带机器噪音，和英语里的实际元音略有差别。
- 音标优先用练习提示里 `/.../` 的写法（句子里遇到练习过的词也沿用），其余查 [CMU 发音词典](https://github.com/cmusphinx/cmudict)（美式），全大写缩写逐个字母读。

视频不在仓库里：第一次启动时从 Seeing Speech 下载到 `~/.cache/speak-drill/seeingspeech/`，只在本机播放。
它的授权是 [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/)，只能非商业使用，页面上会署名。

## 服务器 / 容器

[`deploy/Containerfile`](deploy/Containerfile) 构建 Linux 版镜像（Kokoro + faster-whisper），数据（录音、模型缓存）都在 `/data`：

```bash
podman build -t speak-drill -f deploy/Containerfile .      # docker 也行
podman run -d --name speak-drill -p 127.0.0.1:8080:8080 -v ./data:/data \
  -e SPEAK_DRILL_PASSWORD=换成你的密码 speak-drill
```

- 设了 `SPEAK_DRILL_PASSWORD` 就要登录（签名 Cookie，30 天有效；同一 IP 15 分钟内输错 10 次先锁住）；不设就不用登录，只适合本机用。
- **浏览器只在 https（或 localhost）下允许录音**，放到公网要在前面加一层 https 反代，比如 Caddy、Cloudflare Tunnel。
- 登录失败按 `CF-Connecting-IP` 头计 IP（经 Cloudflare 进来时它是真实地址），没有就用连接地址。不经 Cloudflare 时，
  反代要用真实客户端地址覆盖这个头（Caddy：`header_up CF-Connecting-IP {remote_host}`），不然客户端能伪造它绕过锁定。
- 容器内存给 2GB 够用（Whisper + Kokoro 加载后约 1.2GB）。CPU 上识别比 Apple 芯片慢得多：Whisper 不管录音多短都按
  30 秒窗口算，老一点的 4 核服务器上每条大约 4–5 秒。

## 双击打开

```bash
macos/make-app.sh          # 生成 ~/Applications/Speak Drill.app（可以拖到 Dock）
```

双击后如果服务没在跑，会先在后台启动（日志在 `~/Library/Logs/speak-drill.log`），然后用浏览器打开页面；
已经在跑就直接打开。服务会一直在后台，要停掉用 `pkill -f "speak-drill gui"`。项目挪了位置要重新跑一次 make-app.sh。
想要图标的话，放一张方形的 `macos/icon.png` 再运行。

## 命令行

```bash
uv run speak-drill drill drills/level1_words.txt        # 第一关：技术词
uv run speak-drill drill drills/level3_sentences.txt    # 第三关：整句跟读
uv run speak-drill --rate 120 drill drills/level1_words.txt   # 语速放慢一点
uv run speak-drill say "command by command"             # 只听一遍
```

每条练习：回车开始录音，读完再按回车；`r` 重听，`s` 跳过，`q` 退出。
录音和 `summary.json` 存在 `recordings/<时间>/`。第一次运行时终端会请求麦克风权限。

## 练习文件

`drills/` 下每个 `.txt` 是一关，每行一条，格式是 `目标文本 | 发音提示`，提示可以不写，`#` 开头的行是注释：

```
Anthropic | /ænˈθrɒpɪk/ 首音节 /æn/ 不吞，/θ/ 咬舌吹气，重音在 THRO
```

提示开头写了 `/.../` 音标的话，发音动画就按这个音标拆音素。

## AI 分析（开源版没接）

原版在同一条连续读错几次（左下角滑块设，也能随时手动点）后，会把最后一次录音 + 最近几次识别结果发给大模型，让它指出具体是哪个音素、重音或连读出了问题。
那部分接的是作者自己的服务，开源版把 token 和调用都注释掉了，所以只做 Whisper 比对。
想接自己的模型，看 [`speak_drill/analyze.py`](speak_drill/analyze.py)：提示词已经写好，实现发送录音的那几行，再让 `enabled()` 返回 True 就行。

## 其他选项

- `--asr-model` 换 Whisper 模型（macOS 默认 `mlx-community/whisper-small.en-mlx`，Linux 默认 `small.en`）。
- `SPEAK_DRILL_VOICE` 换 Kokoro 的声音（默认英音女声 `bf_emma`；`bm_george` 英音男声，`af_heart` 美音）。
- `SPEAK_DRILL_TTS`（`say` / `kokoro`）、`SPEAK_DRILL_ASR`（`mlx` / `faster`）强制指定领读和识别后端，默认按系统自动选。
- 只测识别和比对：

  ```bash
  say -o /tmp/x.aiff "Anthropic" && ffmpeg -y -i /tmp/x.aiff -ar 16000 -ac 1 /tmp/x.wav
  uv run speak-drill check /tmp/x.wav "Anthropic"
  ```

## 许可

代码以 [MIT](LICENSE) 发布。发音动画和 MRI 视频版权归 University of Glasgow / University of Strathclyde 的 Seeing Speech 项目，
按 CC BY-NC-ND 4.0 使用，不随本仓库分发。
