"""Shared helpers: paths, tool lookup, yt-dlp and ffmpeg wrappers."""
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(os.environ.get("CLIP_DESK_HOME", Path.cwd()))
JOBS = ROOT / "jobs"


def tool(name):
    p = shutil.which(name)
    if not p:
        sys.exit(f"{name} not found. Run the setup skill first (it installs ffmpeg and yt-dlp).")
    return p


def run(cmd, check=True, capture=False):
    r = subprocess.run(cmd, check=False, text=True, encoding="utf-8", errors="replace",
                       stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    if check and r.returncode != 0:
        msg = (r.stderr or "")[-1500:] if capture else ""
        sys.exit(f"command failed ({r.returncode}): {' '.join(map(str, cmd))[:200]}\n{msg}")
    return r


_WORKING_PROXY_CACHE = None  # (timestamp, chosen_url)


def _proxy_works(proxy_url, test_url="https://www.youtube.com/generate_204", timeout=3.0):
    import urllib.request
    try:
        handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        opener = urllib.request.build_opener(handler)
        req = urllib.request.Request(test_url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def ytdlp_base():
    global _WORKING_PROXY_CACHE
    import importlib.util, socket, time
    exe = [sys.executable, "-m", "yt_dlp"] if importlib.util.find_spec("yt_dlp") else [tool("yt-dlp")]
    base = exe + ["--no-warnings", "--no-progress", "--socket-timeout", "20", "--retries", "5", "--fragment-retries", "5"]
    if sys.platform == "win32":
        base += ["--compat-options", "no-certifi"]  # use the Windows certificate store

    # Verify a proxy actually forwards traffic (30s TTL so tunnel reconnects self-heal without bot restart)
    now = time.time()
    if _WORKING_PROXY_CACHE is None or (now - _WORKING_PROXY_CACHE[0]) > 30.0:
        chosen = ""
        for port, scheme, kind in [
            (10809, "http", "http"),
            (10808, "socks5h", "socks"),
            (9080, "http", "http"),
            (9050, "socks5h", "socks"),
        ]:
            sock = socket.socket()
            sock.settimeout(0.3)
            up = False
            try:
                sock.connect(("127.0.0.1", port))
                up = True
            except Exception:
                pass
            finally:
                try:
                    sock.close()
                except Exception:
                    pass
            if not up:
                continue
            url = f"{scheme}://127.0.0.1:{port}"
            if kind == "http":
                if _proxy_works(url):
                    chosen = url
                    break
            else:
                r = subprocess.run(["curl", "-sI", "--max-time", "4", "--socks5-hostname", f"127.0.0.1:{port}",
                                    "https://www.youtube.com/generate_204"], capture_output=True)
                if r.returncode == 0:
                    chosen = url
                    break
        _WORKING_PROXY_CACHE = (now, chosen)

    chosen = _WORKING_PROXY_CACHE[1]
    is_tor = chosen.endswith(":9080") or chosen.endswith(":9050")
    if chosen:
        base += ["--proxy", chosen]

    # Attach local bgutil POT server if running
    sock = socket.socket()
    sock.settimeout(0.3)
    try:
        sock.connect(("127.0.0.1", 4416))
        base += ["--extractor-args", "youtube:youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416"]
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass

    # Only attach residential cookies when using residential tunnel/direct (avoid IP mismatch lockout on Tor)
    if not is_tor:
        for c_path in [
            ROOT / "cookies.txt",
            Path("/root/projects/ProjectGTA/cookies.txt"),
            Path(__file__).resolve().parent / "cookies.txt",
            Path(__file__).resolve().parent.parent / "cookies.txt"
        ]:
            if c_path.exists():
                base += ["--cookies", str(c_path)]
                break
    return base


def ytdlp_json(url, extra=()):
    r = run(ytdlp_base() + ["-J", *extra, url], capture=True)
    return json.loads(r.stdout)


def is_url(s):
    return bool(re.match(r"https?://", s))


def job_dir(src):
    key = hashlib.sha1(src.encode()).hexdigest()[:8]
    stem = re.sub(r"[^a-z0-9]+", "-", Path(src).stem.lower() if not is_url(src) else src.split("v=")[-1].split("/")[-1].lower())[:24].strip("-")
    d = JOBS / f"{stem or 'job'}-{key}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ffprobe(path):
    r = run([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate,duration",
             "-of", "json", str(path)], capture=True)
    return json.loads(r.stdout)


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
