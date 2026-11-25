import os
import sys
import json
import subprocess
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from bot_core.config import SCRIPTS_DIR, BASE_DIR, JOBS_DIR, DOCS_DIR

def run_cmd(cmd, cwd=None, timeout=600):
    env = dict(os.environ)
    env["CLIP_DESK_HOME"] = str(BASE_DIR)
    
    p = subprocess.run(
        cmd,
        cwd=str(cwd or SCRIPTS_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout
    )
    return p.returncode, p.stdout, p.stderr

def get_processed_video_urls() -> set:
    """Collect YouTube URLs/IDs that have actually produced a finished clip in JOBS_DIR."""
    urls = set()
    for j in JOBS_DIR.glob("*-*"):
        if not j.is_dir() or not any((j / "edits").glob("*.mp4")):
            continue
        for f_name in ["info.json", "candidates.json"]:
            f_path = j / f_name
            if f_path.exists():
                try:
                    data = json.loads(f_path.read_text(encoding="utf-8"))
                    info = data.get("info", data)
                    u = info.get("webpage_url") or info.get("url") or info.get("id")
                    if u:
                        urls.add(str(u).strip().lower())
                        if "v=" in str(u):
                            vid_id = str(u).split("v=")[-1].split("&")[0].strip().lower()
                            urls.add(vid_id)
                            urls.add(f"https://www.youtube.com/watch?v={vid_id}".lower())
                            urls.add(f"http://www.youtube.com/watch?v={vid_id}".lower())
                except Exception:
                    pass
    return urls

def find_top_video(query_or_url: str, skip_processed: bool = True) -> Optional[Dict[str, Any]]:
    """
    If query_or_url is already a URL, return it directly.
    Otherwise searches YouTube with ytsearch and returns dict with title, url, channel, duration.
    Avoids returning videos that have already been clipped in previous jobs.
    """
    s = str(query_or_url).strip()
    if s.startswith("http://") or s.startswith("https://"):
        return {
            "title": "Target Video",
            "url": s,
            "channel": "@Creator",
            "duration": 0
        }
    
    clean_q = s
    for pfx in [
        "buatin video clipping lucu dari", "buatin video clipping", "buatin video",
        "buatkan video clipping dari", "buatkan video clipping", "buatkan video lucu dari", "buatkan video lucu", "buatkan video",
        "buat klip video lucu dari", "buat klip video", "buat klip", "buatin klip",
        "bikin video clipping dari", "bikin video clipping", "bikin video lucu dari", "bikin video", "bikin klip",
        "potongin video dari", "potongin video", "potong video", "potong klip",
        "clipping video", "clipping", "lucu", "funny"
    ]:
        if clean_q.lower().startswith(pfx):
            clean_q = clean_q[len(pfx):].strip()
            break
            
    clean_q = clean_q.replace("buatin", "").replace("buatkan", "").replace("bikin", "").replace("video", "").replace("clipping", "").replace("dari", "").strip()
    
    processed_urls = get_processed_video_urls() if skip_processed else set()

    # If user refers to trending videos or radar
    is_trend_ref = any(k in clean_q.lower() for k in ["trending", "tren", "di atas", "populer", "viral", "radar"])
    if is_trend_ref or not clean_q:
        trends_file = BASE_DIR / "trends.md"
        if trends_file.exists():
            for line in trends_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("|") and not line.startswith("| #") and not line.startswith("|---"):
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 8:
                        tl = parts[7]
                        if "[" in tl and "](" in tl and tl.endswith(")"):
                            t_title = tl[1:tl.rfind("](")]
                            t_url = tl[tl.rfind("](") + 2:-1]
                            t_chan = parts[6]
                            t_id = t_url.split("v=")[-1].split("&")[0].strip().lower() if "v=" in t_url else t_url.lower()
                            
                            # Skip if already processed
                            if skip_processed and (t_url.lower() in processed_urls or t_id in processed_urls):
                                continue
                                
                            return {
                                "title": t_title,
                                "url": t_url,
                                "channel": t_chan,
                                "duration": int(float(parts[5]) * 60) if parts[5] else 600
                            }

    # Format query for YouTube search
    if "speed" in clean_q.lower():
        if "gta" in clean_q.lower():
            clean_q = "ishowspeed gta 6 funny moments gameplay"
        else:
            clean_q = "ishowspeed funny moments highlights"
    elif "kai" in clean_q.lower():
        clean_q = "kai cenat gta 6 funny moments"
    elif "windah" in clean_q.lower():
        clean_q = "windah basudara gta 6 lucu"
    elif not clean_q or is_trend_ref:
        clean_q = "gta 6 funny moments streamer"
    else:
        if "gta" not in clean_q.lower():
            clean_q += " gta 6"
        if "funny" not in clean_q.lower() and "lucu" not in clean_q.lower():
            clean_q += " funny moments"

    try:
        py_bin = sys.executable
        code_py = (
            f"import sys, json; sys.path.insert(0, r'{SCRIPTS_DIR}'); "
            f"from common import ytdlp_json; "
            f"res = ytdlp_json('ytsearch10:{clean_q}', ['--flat-playlist']); "
            f"print(json.dumps(res.get('entries', [])))"
        )
        cmd = [py_bin, "-c", code_py]
        code, out, err = run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=30)
        if code == 0 and out.strip():
            lines = [l for l in out.strip().splitlines() if l.startswith("[") and l.endswith("]")]
            if lines:
                entries = json.loads(lines[-1])
                for e in entries:
                    url = e.get("url") or e.get("webpage_url")
                    if url and "/shorts/" not in url:
                        if not url.startswith("http"):
                            url = f"https://www.youtube.com/watch?v={url}"
                        vid_id = url.split("v=")[-1].split("&")[0].strip().lower() if "v=" in url else url.lower()
                        
                        # Skip if already processed in previous jobs
                        if skip_processed and (url.lower() in processed_urls or vid_id in processed_urls):
                            continue
                            
                        return {
                            "title": e.get("title", "Trending Video"),
                            "url": url,
                            "channel": e.get("uploader") or e.get("channel") or "@Streamer",
                            "duration": e.get("duration", 0)
                        }
                        
                # Fallback to first non-short if all were processed
                for e in entries:
                    url = e.get("url") or e.get("webpage_url")
                    if url and "/shorts/" not in url:
                        if not url.startswith("http"):
                            url = f"https://www.youtube.com/watch?v={url}"
                        return {
                            "title": e.get("title", "Trending Video"),
                            "url": url,
                            "channel": e.get("uploader") or e.get("channel") or "@Streamer",
                            "duration": e.get("duration", 0)
                        }
    except Exception as e:
        print(f"[find_top_video error]: {e}")
    return None

def scan_youtube_trends(query="gta 6", hours=48, limit=10):
    trends_file = BASE_DIR / "trends.md"
    if trends_file.exists():
        try:
            trends_file.unlink()
        except Exception:
            pass
    py_bin = sys.executable
    cmd = [py_bin, str(SCRIPTS_DIR / "trends.py"), "--query", query, "--hours", str(hours), "--limit", str(limit), "--out", str(trends_file)]
    try:
        code, out, err = run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=120)
    except Exception as e:
        print(f"[scan_youtube_trends warning]: {e}")
    
    results = []
    if trends_file.exists():
        lines = trends_file.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if line.startswith("|") and not line.startswith("| #") and not line.startswith("|---"):
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 8:
                    results.append({
                        "rank": parts[1],
                        "views_per_hour": parts[2],
                        "views": parts[3],
                        "age_hours": parts[4],
                        "duration_min": parts[5],
                        "channel": parts[6],
                        "title_link": parts[7]
                    })
    return results

def extract_moments(video_url_or_file, top=6, max_minutes=12) -> Tuple[Optional[Path], List[Dict[str, Any]], str]:
    """
    Runs moments.py to download, transcribe, score visual/facial/audio excitement, and curate top moments.
    Returns (job_dir, candidates, error_msg).
    """
    src = str(video_url_or_file).strip()
    if not src.startswith("http://") and not src.startswith("https://") and not Path(src).exists():
        found = find_top_video(src)
        if found:
            src = found["url"]
        else:
            return None, [], "Video target tidak ditemukan."

    py_bin = sys.executable
    cmd = [py_bin, str(SCRIPTS_DIR / "moments.py"), src, "--top", str(top), "--max-minutes", str(max_minutes)]
    try:
        code, out, err = run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=1200)
    except subprocess.TimeoutExpired:
        return None, [], "Proses download/transkrip memakan waktu terlalu lama (timeout 20 menit). Coba video lain atau kirim file MP4 langsung."
    except Exception as e:
        return None, [], str(e)[:500]
    
    error_msg = ""
    combined_err = f"{out}\n{err}"
    if "Sign in to confirm you’re not a bot" in combined_err or "Sign in to confirm you're not a bot" in combined_err:
        error_msg = "YOUTUBE_ANTIBOT_BLOCKED"
    elif code != 0:
        error_msg = (err or out)[-800:]

    job_dir = None
    for line in out.splitlines():
        if "job:" in line:
            job_dir = Path(line.split("job:")[-1].strip())
            break

    candidates = []
    if job_dir and (job_dir / "candidates.json").exists():
        try:
            cand_data = json.loads((job_dir / "candidates.json").read_text(encoding="utf-8"))
            candidates = cand_data.get("candidates", [])
        except Exception:
            pass
            
    return job_dir, candidates, error_msg

def _clip_file_valid(path: Path) -> bool:
    if not path or not path.exists() or path.stat().st_size < 10_000:
        return False
    try:
        code, out, _ = run_cmd(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", str(path)],
            timeout=15
        )
        return code == 0 and float((out or "0").strip()) >= 5.0
    except Exception:
        return False

def render_vertical_clip(job_dir, pick=1, layout="react", hook="", title="", title_style="box", captions="word", start=None, end=None):
    py_bin = sys.executable
    edits_dir = Path(job_dir) / "edits"
    edits_dir.mkdir(parents=True, exist_ok=True)
    clip_file = edits_dir / f"clip_{pick}.mp4"
    # Remove any stale pre-existing render so failed runs never return an old partial/wrong clip
    clip_file.unlink(missing_ok=True)

    def _run_cut(chosen_layout: str):
        cmd = [
            py_bin, str(SCRIPTS_DIR / "cut.py"), str(job_dir),
            "--pick", str(pick),
            "--layout", chosen_layout,
            "--captions", captions
        ]
        if chosen_layout in ("react", "facecam"):
            cmd += ["--cam", "auto"]
        if title and chosen_layout == "react":
            cmd += ["--title", title, "--title-style", title_style]
        if hook:
            cmd += ["--hook", hook]
        if start is not None:
            cmd += ["--start", str(start)]
        if end is not None:
            cmd += ["--end", str(end)]
        try:
            return run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=480)
        except Exception as e:
            print(f"[render_vertical_clip warning ({chosen_layout})]: {e}")
            return 1, "", str(e)

    code, out, err = _run_cut(layout)
    if code == 0 and _clip_file_valid(clip_file):
        return clip_file

    # Automatic fallback to blur layout if react/facecam fails or times out
    if layout != "blur":
        clip_file.unlink(missing_ok=True)
        print(f"[render_vertical_clip] layout '{layout}' failed ({err.strip()[:80]}), falling back to 'blur'...")
        code2, out2, err2 = _run_cut("blur")
        if code2 == 0 and _clip_file_valid(clip_file):
            return clip_file

    return None

def generate_viral_hook(streamer_name: str, cand_text: str = "", video_title: str = "", candidate: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """
    Applies AI-curated hook/title if present in candidate, else hook-writer formulas.
    Returns (hook, title) where title is burned on the seam (reaction layout) and hook opens first 2-3 seconds.
    """
    if candidate and candidate.get("ai_title"):
        return str(candidate.get("ai_hook") or candidate["ai_title"])[:42], str(candidate["ai_title"])[:52]
    s_name = (streamer_name or "Streamer").strip()
    s_upper = s_name.upper()
    tl = (cand_text or "").lower()
    vt = (video_title or "").lower()
    
    # 1. Streamer Specific Reaction Formulas
    if "speed" in s_name.lower():
        if "13" in tl or "years" in tl or "tahun" in tl:
            return "SPEED REALIZED THIS 💀", "SPEED REALIZED WHY GTA 6 TOOK 13 YEARS"
        if any(w in tl for w in ["cop", "police", "busted", "wasted", "polisi"]):
            return "SPEED VS COPS 💀", "SPEED LOST HIS MIND WITH THE COPS IN GTA 6"
        return "SPEED CANNOT BE REAL 💀", f"SPEED LOST HIS MIND IN GTA 6 😭"
        
    if "windah" in s_name.lower():
        if "13 tahun" in tl or "menunggu" in tl or "excited" in tl or "euphoria" in tl:
            return "WINDAH 13 TAHUN MENUNGGU 😭", "WINDAH KAGET LIHAT GTA 6 SETELAH 13 TAHUN MENUNGGU"
        if any(w in tl for w in ["grafis", "map", "cheat", "gila", "kocak"]):
            return "WINDAH KAGET BANGET 💀", "WINDAH BASUDARA SHOCK LIHAT DETAIL GTA 6"
        return "WINDAH KAGET BANGET 😭", "WINDAH BASUDARA NONTON GTA 6 KAGET 💀"

    if "kai" in s_name.lower():
        return "KAI CENAT LOST IT 💀", "KAI CENAT REACTS TO CRAZIEST GTA 6 MOMENT"

    # 2. Indonesian / General Streamer Reaction Formulas
    if any(w in tl for w in ["gila", "kaget", "anjir", "parah", "kocak", "ngakak", "lucu"]):
        return f"{s_upper} KAGET BANGET 💀", f"{s_upper} SHOCK LIHAT MOMEN INI DI GTA 6 😭"

    if any(w in tl for w in ["secret", "rahasia", "hidden", "easter egg", "cheat"]):
        return "ROCKSTAR HID THIS IN PLAIN SIGHT", "THIS GTA 6 DETAIL IS ACTUALLY INSANE"

    if any(w in tl for w in ["cop", "police", "chase", "polisi"]):
        return "COPS CHASED THE WRONG GUY 💀", "WHEN COPS CHASE THE WRONG PLAYER IN GTA 6"

    # Default punchy reaction formula
    if s_name and s_name.lower() not in ("streamer", "gta 6", "gta 6 trending", "gta vi"):
        return f"{s_upper} WAS NOT READY 💀", f"{s_upper} REALIZED WHY GTA 6 TOOK ROCKSTAR 13 YEARS"

    return "NOBODY EXPECTED THIS IN GTA 6 💀", "ROCKSTAR ADDED THIS AND TOLD NOBODY"

def find_live_streams(query: str = "gta 6", limit: int = 10) -> List[Dict[str, Any]]:
    """Runs streams.py to find active Twitch and YouTube live streams ranked by concurrent viewers."""
    py_bin = sys.executable
    out_file = BASE_DIR / "streams.json"
    cmd = [py_bin, str(SCRIPTS_DIR / "streams.py"), "--query", query, "--limit", str(limit), "--json", str(out_file)]
    try:
        run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=60)
    except Exception as e:
        print(f"[find_live_streams warning]: {e}")
    if out_file.exists():
        try:
            return json.loads(out_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def translate_clip_subtitles(job_dir: Path, pick: int = 1, langs: str = "id", voice: bool = False) -> Optional[Path]:
    """Runs translate.py to translate captions and hook into target language (e.g. Indonesian 'id')."""
    py_bin = sys.executable
    cmd = [py_bin, str(SCRIPTS_DIR / "translate.py"), str(job_dir), "--pick", str(pick), "--langs", langs]
    if voice:
        cmd += ["--voice"]
    try:
        run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=480)
    except Exception as e:
        print(f"[translate_clip_subtitles warning]: {e}")
    
    first_lang = langs.split(",")[0].strip()
    out_mp4 = Path(job_dir) / "edits" / f"clip_{pick}_{first_lang}.mp4"
    if _clip_file_valid(out_mp4):
        return out_mp4
    return None

def verify_clip(clip_path, caption=""):
    py_bin = sys.executable
    campaign_file = DOCS_DIR / "campaigns.md"
    cmd = [py_bin, str(SCRIPTS_DIR / "check.py"), str(clip_path), "--campaign", str(campaign_file), "--caption", caption]
    code, out, err = run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=60)
    is_pass = "RESULT: PASS" in out
    return is_pass, out

def log_payout(campaign, platform, post_url, views, rate_per_1k=1.0, status="pending"):
    py_bin = sys.executable
    cmd = [
        py_bin, str(SCRIPTS_DIR / "payouts.py"), "add",
        "--campaign", str(campaign),
        "--platform", str(platform),
        "--post-url", str(post_url),
        "--views", str(views),
        "--rate-per-1k", str(rate_per_1k),
        "--status", str(status)
    ]
    code, out, err = run_cmd(cmd, cwd=SCRIPTS_DIR, timeout=30)
    return out

def cleanup_raw_media(keep_hours=24):
    now = time.time()
    cutoff = now - (keep_hours * 3600)
    freed_mb = 0
    
    for job in JOBS_DIR.glob("*-*"):
        if job.is_dir():
            for f in [job / "source.mp4", job / "audio.wav"]:
                if f.exists() and f.stat().st_mtime < cutoff:
                    size = f.stat().st_size
                    try:
                        f.unlink()
                        freed_mb += size / (1024 * 1024)
                    except Exception:
                        pass
    return freed_mb
