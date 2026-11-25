"""Find the best exciting & clip-worthy moments in a video or VOD.

Signals per second: audio loudness spikes, multilingual hype/reaction words (EN+ID),
facial expression excitement & head bounce (YuNet landmarks), visual action/motion spikes,
speech burst density, YouTube "most replayed" heatmap, and live chat spikes — plus optional
Gemini multimodal curation over keyframes + transcript so boring talking intros are skipped
and clips finish on a complete sentence/payoff without cutting off mid-thought.

usage: python moments.py <url-or-file> [--top 8] [--min 15] [--max 52] [--chat chat.json] [--max-minutes 15]
"""
import argparse, json, math, os, re, sys, wave
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent))
from common import ffprobe, is_url, job_dir, load_json, run, save_json, tool, ytdlp_base, ytdlp_json

HYPE = re.compile(
    r"\b(no way|oh my god|omg|what|wait|bro|let'?s go|holy|insane|crazy|yo+|wtf|dude|look at|nah|run|go go|"
    r"clip that|bruh|sheesh|damnn?|hell nah|no shot|actually|freaking|"
    r"anjir+|anjay+|gila+|kaget|astaga|serius|gokil|parah|kocak|ngakak|wkwk+|mampus|tolong|kabur|pecah|"
    r"buset|edan|mantap|sumpah|beneran|euphoria|excited|mati|lari|meledak|woi+|haha+)\b",
    re.I,
)
CHAT_HYPE = re.compile(r"(LMAO|LOL|KEKW|OMEGALUL|W+\b|CLIP|💀|😂|🔥|NO WAY|HOLY|WKWK|ANJIR|GILA)", re.I)


def _media_dur_ok(vid, min_ratio=0.7):
    """Verify video is readable by ffprobe and its audio stream is not severely truncated."""
    try:
        p = ffprobe(vid)
    except SystemExit:
        return False, 0.0
    vid_dur = float((p.get("format") or {}).get("duration") or 0)
    if vid_dur < 5.0:
        return False, vid_dur
    streams = p.get("streams") or []
    has_v = any(s.get("codec_type") == "video" for s in streams)
    if not has_v:
        return False, vid_dur
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if a and a.get("duration"):
        aud_dur = float(a["duration"])
        if aud_dur < min_ratio * vid_dur:
            return False, vid_dur
    return True, vid_dur


def _pick_section(info, max_min):
    """Choose which time slice [start, end] to fetch for very long VODs."""
    total = float(info.get("duration") or 0)
    win = max_min * 60
    if total <= 0 or total <= win:
        return None
    heatmap = info.get("heatmap") or []
    best_hp = None
    for h in heatmap:
        if h.get("start_time", 0) >= min(30, total * 0.05):
            if best_hp is None or h.get("value", 0) > best_hp.get("value", 0):
                best_hp = h
    if best_hp and best_hp.get("value", 0) > 0.3:
        center = float(best_hp["start_time"])
        s = max(0, int(center - win * 0.45))
        e = min(int(total), s + int(win))
        return (s, e)
    # Long VOD without heatmap (e.g. multi-hour livestream): skip initial countdown/menu intro
    if total > 1800:
        s = 180
        return (s, int(min(total, s + win)))
    return (0, int(win))


def _download_section(src, part, fmt, section):
    args = ytdlp_base() + ["-f", fmt, "--merge-output-format", "mp4", "--force-overwrites", "-o", str(part)]
    if section:
        s, e = section
        args += ["--download-sections", f"*{s}-{e}"]
    return run(args + [src], check=False, capture=True)


def fetch(src, d, max_min):
    info = {}
    if is_url(src):
        info = ytdlp_json(src)
        save_json(d / "info.json", {k: info.get(k) for k in ("id", "title", "uploader", "channel", "uploader_id", "webpage_url",
                                                             "duration", "view_count", "upload_date", "heatmap", "is_live", "was_live")})
        vid = d / "source.mp4"
        if vid.exists():
            ok, _ = _media_dur_ok(vid)
            if not ok:
                print(f"moments: cached source.mp4 incomplete/corrupt, re-downloading cleanly...")
                for stale in (vid, d / "audio.wav", d / "transcript.json"):
                    stale.unlink(missing_ok=True)
        if not vid.exists():
            part = d / "source.part.mp4"
            part.unlink(missing_ok=True)
            sec = _pick_section(info, max_min)
            # Prefer 720p H.264 (avc1) + m4a for fast OpenCV decoding and no AV1 stalls; fallback to progressive mp4
            fmts = [
                "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/b",
                "b[height<=720][ext=mp4]/b[ext=mp4]/b",
            ]
            last_err = ""
            for fmt in fmts:
                part.unlink(missing_ok=True)
                r = _download_section(src, part, fmt, sec)
                if r.returncode == 0 and part.exists() and _media_dur_ok(part)[0]:
                    part.replace(vid)
                    break
                last_err = (r.stderr or r.stdout or "")[-1000:]
            if not vid.exists():
                part.unlink(missing_ok=True)
                sys.exit(f"failed to download intact video: {last_err}")
    else:
        vid = Path(src).resolve()
        save_json(d / "info.json", {"title": vid.stem, "webpage_url": str(vid)})
    return vid, info


def audio_rms(vid, d, vid_dur):
    wav = d / "audio.wav"
    if wav.exists():
        try:
            with wave.open(str(wav)) as w:
                wav_dur = w.getnframes() / float(w.getframerate() or 16000)
            if vid_dur > 20 and wav_dur < 0.7 * vid_dur:
                print(f"moments: cached audio.wav truncated ({wav_dur:.1f}s vs {vid_dur:.1f}s), regenerating...")
                wav.unlink(missing_ok=True)
        except Exception:
            wav.unlink(missing_ok=True)
    if not wav.exists():
        run([tool("ffmpeg"), "-y", "-v", "error", "-fflags", "+genpts", "-err_detect", "ignore_err",
             "-i", str(vid), "-ac", "1", "-ar", "16000", str(wav)])
    with wave.open(str(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    n = len(x) // 16000
    if n <= 0:
        sys.exit("audio stream empty (< 1s)")
    rms = np.sqrt((x[: n * 16000].reshape(n, 16000) ** 2).mean(1) + 1e-9)
    return wav, 20 * np.log10(rms)


def transcribe(wav, d, model_name=None):
    out = d / "transcript.json"
    if out.exists():
        return load_json(out)
    from faster_whisper import WhisperModel
    try:
        import ctranslate2
        cuda = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        cuda = False
    chosen = model_name or os.environ.get("WHISPER_MODEL") or ("small" if cuda else "base")
    with wave.open(str(wav)) as w:  # pass samples directly (16 kHz mono), no extra decoder needed
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768

    def run_on(device, mdl):
        model = WhisperModel(mdl, device=device, compute_type="float16" if device == "cuda" else "int8")
        segs, _ = model.transcribe(pcm, word_timestamps=True, vad_filter=True)
        return [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for s in segs for w in (s.words or [])]
    try:
        words = run_on("cuda" if cuda else "cpu", chosen)
    except RuntimeError as e:
        print(f"GPU transcription unavailable ({str(e)[:80]}), using CPU base")
        words = run_on("cpu", "base")
    save_json(out, words)
    return words


def visual_excitement(vid, n, peak_hints=None):
    """Per-second (face_excite, scene_motion) scored from YuNet landmarks + motion over baseline + peak hints."""
    face_sc = np.zeros(n)
    motion_sc = np.zeros(n)
    if n <= 0:
        return face_sc, motion_sc
    try:
        import cv2
        from facecam import model_path
        det = cv2.FaceDetectorYN.create(model_path(), "", (320, 320), 0.65, 0.3, 5000)
    except Exception:
        return face_sc, motion_sc

    # Sample ~24 evenly spaced baseline frames plus dense windows around top audio/hype/heatmap peaks (~75 frames max)
    ts_set = {round(float(t), 1) for t in np.linspace(1.0, max(1.0, n - 1.5), min(24, max(4, n // 4)))}
    for p in (peak_hints or [])[:10]:
        for dt in (-4.0, -2.0, 0.0, 2.0, 4.0):
            t_val = min(max(0.5, float(p) + dt), max(0.5, n - 0.5))
            ts_set.add(round(t_val, 1))
    sample_ts = sorted(ts_set)

    cap = cv2.VideoCapture(str(vid))
    prev_gray = None
    prev_t = None
    samples = []  # (t_sec, motion, face_metrics_or_None)
    for t_cur in sample_ts:
        cap.set(cv2.CAP_PROP_POS_MSEC, t_cur * 1000.0)
        ok, f = cap.read()
        if ok and f is not None:
            t_sec = min(n - 1, int(t_cur))
            h, w = f.shape[:2]
            if w > 640:
                f = cv2.resize(f, (640, int(h * 640 / w)), interpolation=cv2.INTER_AREA)
                h, w = f.shape[:2]
            gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
            mot = float(np.abs(gray - prev_gray).mean()) if (prev_gray is not None and prev_t is not None and (t_cur - prev_t) <= 6.0) else 0.0
            prev_gray = gray
            prev_t = t_cur

            det.setInputSize((w, h))
            _, faces = det.detect(f)
            fm = None
            if faces is not None and len(faces) > 0:
                best = max(faces, key=lambda r: float(r[2] * r[3]) * float(r[14]))
                fw, fh = float(best[2]), float(best[3])
                cx, cy = (best[0] + fw / 2) / w, (best[1] + fh / 2) / h
                eye_d = max(4.0, math.hypot(best[6] - best[4], best[7] - best[5]))
                nx, ny = float(best[8]), float(best[9])
                mrx, mry, mlx, mly = float(best[10]), float(best[11]), float(best[12]), float(best[13])
                mouth_y = (mry + mly) / 2.0
                mouth_drop = (mouth_y - ny) / eye_d
                mouth_w = math.hypot(mrx - mlx, mry - mly) / eye_d
                mx0, mx1 = max(0, int(min(mrx, mlx) - 0.1 * eye_d)), min(w, int(max(mrx, mlx) + 0.1 * eye_d))
                my0, my1 = max(0, int(mouth_y - 0.25 * eye_d)), min(h, int(mouth_y + 0.45 * eye_d))
                m_dark = 0.0
                if mx1 > mx0 + 2 and my1 > my0 + 2:
                    roi = gray[my0:my1, mx0:mx1]
                    m_dark = float(roi.std() / (roi.mean() + 10.0))
                fm = (mouth_drop, mouth_w, m_dark, cx, cy, fh / h)
            samples.append((t_sec, mot, fm))
    cap.release()

    if not samples:
        return face_sc, motion_sc

    for t, mot, _ in samples:
        motion_sc[max(0, t - 1):min(n, t + 2)] = np.maximum(motion_sc[max(0, t - 1):min(n, t + 2)], mot)

    fms = [s[2] for s in samples if s[2] is not None]
    if len(fms) >= 4:
        arr = np.array(fms)
        med_drop, med_w, med_dark = np.median(arr[:, 0]), np.median(arr[:, 1]), np.median(arr[:, 2])
        prev_pos, prev_ft = None, None
        for t, _, fm in samples:
            if fm is None:
                prev_pos = None
                continue
            drop, mw, mdark, cx, cy, sz = fm
            expr = abs(drop - med_drop) * 2.5 + abs(mw - med_w) * 1.8 + max(0.0, mdark - med_dark) * 2.0
            move = 0.0
            if prev_pos is not None and prev_ft is not None and (t - prev_ft) <= 6:
                move = (math.hypot(cx - prev_pos[0], cy - prev_pos[1]) * 18.0 + abs(sz - prev_pos[2]) * 10.0)
            prev_pos, prev_ft = (cx, cy, sz), t
            face_sc[max(0, t - 1):min(n, t + 2)] = np.maximum(face_sc[max(0, t - 1):min(n, t + 2)], expr + move)

    return smooth(face_sc, 3), smooth(motion_sc, 3)


def chat_series(d, n, chat_arg, info):
    """Messages per second from YouTube live_chat json lines or a TwitchDownloader chat.json."""
    c = np.zeros(n)
    yt = list(d.glob("chat*.live_chat.json"))
    if yt:
        for line in yt[0].read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                a = json.loads(line)["replayChatItemAction"]
                t = int(a["videoOffsetTimeMsec"]) / 1000
                txt = json.dumps(a["actions"], ensure_ascii=False)
            except Exception:
                continue
            if 0 <= t < n:
                c[int(t)] += 2 if CHAT_HYPE.search(txt) else 1
    elif chat_arg:
        js = load_json(chat_arg)
        for m in js.get("comments", []):
            t = m.get("content_offset_seconds", 0)
            body = (m.get("message") or {}).get("body", "")
            if 0 <= t < n:
                c[int(t)] += 2 if CHAT_HYPE.search(body) else 1
    return c


def z(a):
    a = np.asarray(a, dtype=float)
    if a.std() < 1e-9:
        return np.zeros_like(a)
    return (a - np.median(a)) / (a.std() + 1e-9)


def smooth(a, k):
    k = max(1, int(k))
    return np.convolve(a, np.ones(k) / k, mode="same")


def _utterances(words):
    """Group Whisper words into complete sentences/clauses separated by punctuation or >0.75s pause."""
    utts, cur = [], []
    for w in words:
        if cur and w["s"] - cur[-1]["e"] > 0.75:
            utts.append(cur); cur = []
        cur.append(w)
        if w["w"][-1:] in ".?!":
            utts.append(cur); cur = []
    if cur:
        utts.append(cur)
    return utts


def _snap_complete_window(utts, words, p, dur, min_len, max_len):
    """Anchor a clip around peak `p` so it opens cleanly on setup and finishes the entire payoff sentence."""
    hard_max = max(max_len, 52.0)  # stay safely under 60s platform limit while finishing sentences cleanly
    if not words:
        s0 = max(0.0, p - 0.5 * min(max_len, 35.0))
        e0 = min(dur, s0 + min(max_len, 35.0))
        return s0, e0

    target_s = max(0.0, p - 15.0)
    target_e = min(dur, p + 18.0)

    # Pick utterance starting closest to target_s (without starting too late after p)
    start_u = min(utts, key=lambda u: abs(u[0]["s"] - target_s) + (20.0 if u[0]["s"] > max(0.0, p - 5.0) else 0.0))
    s0 = max(0.0, start_u[0]["s"] - 0.35)
    if p - s0 > 26.0:
        s0 = max(0.0, p - 22.0)

    # Extend e0 past peak `p` to complete the full reaction utterance
    end_candidates = [u for u in utts if u[-1]["e"] >= p + 4.0 and u[-1]["e"] <= s0 + hard_max]
    if end_candidates:
        # Pick the utterance finishing nearest target_e (and at least min_len)
        valid = [u for u in end_candidates if u[-1]["e"] - s0 >= min_len]
        chosen_end = min(valid or end_candidates, key=lambda u: abs(u[-1]["e"] - target_e))
        e0 = min(dur, chosen_end[-1]["e"] + 0.8)
    else:
        e0 = min(dur, target_e)

    if e0 - s0 < min_len:
        # Pull in one more sentence after/before if still shorter than min_len
        later = [u for u in utts if u[-1]["e"] > e0 and u[-1]["e"] - s0 <= hard_max]
        if later:
            e0 = min(dur, later[0][-1]["e"] + 0.8)
        if e0 - s0 < min_len:
            e0 = min(dur, s0 + min_len)
    e0 = min(dur, e0, s0 + hard_max)
    return s0, e0


def _load_gemini_cfg():
    key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not key:
        cfg_file = Path(__file__).resolve().parent.parent.parent / "bot_core" / "settings.json"
        if not cfg_file.exists():
            cfg_file = Path("/root/projects/ProjectGTA/bot_core/settings.json")
        if cfg_file.exists():
            try:
                js = json.loads(cfg_file.read_text(encoding="utf-8"))
                key = js.get("gemini_api_key")
                model = js.get("gemini_model", model)
            except Exception:
                pass
    return key, model


def _ai_curate_candidates(vid, meta, picks):
    """Use Gemini Vision + Transcript over REST to rank candidates by genuine facial excitement & game action."""
    if len(picks) <= 1:
        return picks
    api_key, model = _load_gemini_cfg()
    if not api_key:
        return picks
    try:
        import base64, cv2, requests
    except Exception:
        return picks

    try:
        parts = []
        cap = cv2.VideoCapture(str(vid))
        summary_lines = [
            f"Video Title: {meta.get('title', '')} | Channel: {meta.get('channel') or meta.get('uploader') or ''}",
            "Evaluate these candidate clip windows and pick the #1 MOST EXCITING, FUNNY, OR EMOTIONAL reaction moment worth posting as a vertical Shorts/TikTok clip.",
            "AVOID boring menu/PS5 home screens or quiet intro chatter if gameplay reaction or funny facial expressions exist.",
            "Candidates (2 keyframes attached right before each):"
        ]
        for c in picks[:6]:
            for t in (c["start"] + 0.35 * (c["end"] - c["start"]), float(c["peak"])):
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000)
                ok, f = cap.read()
                if ok and f is not None:
                    h, w = f.shape[:2]
                    if w > 480:
                        f = cv2.resize(f, (480, int(h * 480 / w)), interpolation=cv2.INTER_AREA)
                    ok_enc, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if ok_enc:
                        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.tobytes()).decode()}})
            summary_lines.append(
                f"- Candidate #{c['n']} [{c['start']:.1f}s-{c['end']:.1f}s] score={c['score']} "
                f"signals={','.join(c['why'])} | transcript: \"{c['text'][:220]}\""
            )
        cap.release()
        prompt = "\n".join(summary_lines) + (
            "\n\nRespond STRICTLY as valid JSON: "
            '{"best_n": <int>, "why_id": "<1 short sentence in Indonesian explaining why this moment is best>", '
            '"title": "<punchy reaction headline <48 chars IN ENGLISH by default using viral hook formulas (Curiosity Gap, Contrarian, or Pattern-Interrupt with 2-3 CAPS words + 1 emoji), e.g. SPEED CANNOT BELIEVE THIS IN GTA 6! 💀🔥. Zero typos. If streamer is English speaker like Speed, title MUST be in English>", '
            '"hook": "<short opening hook <35 chars IN ENGLISH by default using viral hook psychology triggers (Curiosity Gap, Shock, or Story Open) + 1 emoji, e.g. NOBODY NOTICED THIS 💀>"}'
        )
        parts.append({"text": prompt})

        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
            json={"contents": [{"role": "user", "parts": parts}]},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"ai-curator skipped (HTTP {r.status_code})")
            return picks
        raw = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"]).strip()
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return picks
        ai = json.loads(m.group(0))
        best_n = int(ai.get("best_n", 1))
        best = next((c for c in picks if c["n"] == best_n), None)
        if best:
            best["why_ai"] = str(ai.get("why_id", "")).strip()
            if ai.get("title"):
                best["ai_title"] = str(ai["title"]).strip()[:52]
            if ai.get("hook"):
                best["ai_hook"] = str(ai["hook"]).strip()[:42]
            reordered = [best] + [c for c in picks if c["n"] != best_n]
            for i, c in enumerate(reordered, 1):
                c["n"] = i
            print(f"ai-curator: promoted candidate #{best_n} -> #1 ({best['why_ai']})")
            return reordered
    except Exception as e:
        print(f"ai-curator skipped ({str(e)[:90]})")
    return picks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min", type=float, default=15); ap.add_argument("--max", type=float, default=52)
    ap.add_argument("--chat"); ap.add_argument("--max-minutes", type=int, default=15)
    ap.add_argument("--whisper-model", default=None)
    a = ap.parse_args()
    d = job_dir(a.src)
    vid, info = fetch(a.src, d, a.max_minutes)
    dur = float(ffprobe(vid)["format"]["duration"])
    wav, db = audio_rms(vid, d, dur)
    n = len(db)
    words = transcribe(wav, d, a.whisper_model)

    # Multi-modal excitement signals (audio + speech + facial expression + motion + heatmap + chat)
    loud = smooth(np.clip(z(db - smooth(db, 30)), 0, None), 3)
    hype = np.zeros(n)
    burst = np.zeros(n)
    for w in words:
        t = int(w["s"])
        if 0 <= t < n:
            burst[t] += 1
            if HYPE.search(w["w"]):
                hype[t] += 1
    hype = smooth(hype, 5)
    burst = smooth(burst, 4)

    heat = np.zeros(n)
    sec_offset = 0.0
    sec_slice = _pick_section(info, a.max_minutes) if is_url(a.src) else None
    if sec_slice:
        sec_offset = float(sec_slice[0])
    for h in (info.get("heatmap") or []):
        hs = int(h["start_time"] - sec_offset)
        he = int(math.ceil(h["end_time"] - sec_offset))
        if he > 0 and hs < n:
            heat[max(0, hs):min(n, he)] = h["value"]

    chat = chat_series(d, n, a.chat, info)
    chatz = smooth(np.clip(z(smooth(chat, 10)), 0, None), 3)
    w_heat = 2.0 if heat.any() else 0
    w_chat = 1.5 if chat.any() else 0

    # Pick top spaced acoustic/hype/heatmap peak hints first so visual_excitement skips dead segments
    pre_score = 1.0 * loud + 0.9 * z(hype).clip(0) + 0.5 * z(burst).clip(0) + w_heat * z(heat).clip(0) + w_chat * chatz
    peak_hints = []
    for ph in np.argsort(-pre_score):
        if len(peak_hints) >= 10:
            break
        if all(abs(int(ph) - prev) >= 15 for prev in peak_hints):
            peak_hints.append(int(ph))

    face_excite, scene_motion = visual_excitement(vid, n, peak_hints=peak_hints)

    w_face = 1.2 if face_excite.any() else 0
    w_mot = 0.6 if scene_motion.any() else 0

    score = pre_score + w_face * z(face_excite).clip(0) + w_mot * z(scene_motion).clip(0)

    utts = _utterances(words)
    picks, used = [], np.zeros(n, bool)
    order = np.argsort(-score)
    want_n = max(a.top, 6)
    for p in order:
        if len(picks) >= want_n or score[p] <= 0:
            break
        s0, e0 = _snap_complete_window(utts, words, int(p), dur, a.min, a.max)
        if used[int(s0):int(e0)].any():
            continue
        used[int(s0):int(e0)] = True
        text = " ".join(x["w"] for x in words if s0 <= x["s"] < e0)
        why = []
        if face_excite[p] > 0 and z(face_excite)[p] > 1.0:
            why.append("ekspresi wajah seru")
        if loud[p] > 1.0:
            why.append("suara memuncak")
        if hype[p] > 0:
            why.append("kata reaksi")
        if scene_motion[p] > 0 and z(scene_motion)[p] > 1.0:
            why.append("aksi layar intens")
        if heat[p] > 0.5:
            why.append(f"most replayed {heat[p]:.2f}")
        if w_chat and chatz[p] > 1:
            why.append("chat spike")
        picks.append({
            "n": len(picks) + 1, "start": round(s0, 2), "end": round(e0, 2), "peak": int(p),
            "score": round(float(score[p]), 2), "why": why or ["overall energy"], "text": text[:400],
        })

    meta = load_json(d / "info.json")
    picks = _ai_curate_candidates(vid, meta, picks)
    picks = picks[:a.top]
    for i, x in enumerate(picks, 1):
        x["n"] = i

    save_json(d / "candidates.json", {
        "source": str(vid), "info": meta, "duration": dur, "candidates": picks,
        "signals": {
            "heatmap": bool(w_heat), "chat": bool(w_chat),
            "facial_expression": bool(w_face), "scene_motion": bool(w_mot),
            "words": len(words),
        },
    })
    fmt = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"
    md = [
        f"# Candidates: {meta.get('title', '')}",
        f"source: {meta.get('webpage_url', '')}",
        f"signals: loudness, transcript ({len(words)} words)"
        + (", facial expression" if w_face else "")
        + (", scene motion" if w_mot else "")
        + (", most replayed" if w_heat else "")
        + (", chat" if w_chat else ""),
        "",
    ]
    for x in picks:
        ai_note = f" | AI: {x['why_ai']}" if x.get("why_ai") else ""
        md += [
            f"## {x['n']}. {fmt(x['start'])}-{fmt(x['end'])} ({x['end'] - x['start']:.0f}s) score {x['score']}",
            f"why: {', '.join(x['why'])}{ai_note}",
            f"> {x['text']}",
            "",
        ]
    (d / "candidates.md").write_text("\n".join(md), encoding="utf-8")
    print(f"job: {d}\n{len(picks)} candidates -> {d / 'candidates.md'}")


if __name__ == "__main__":
    main()
