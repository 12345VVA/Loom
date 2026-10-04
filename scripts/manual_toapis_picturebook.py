# -*- coding: utf-8 -*-
"""ToAPIs gpt-image-2.5-flare-vip 完整绘本生产测试: 封面 + 内页(参考图链路).

流程:
  1. 文生图提交封面 (POST /v1/images/generations, JSON)
  2. 内页以封面 URL 作参考图 (POST /v1/images/edits, multipart 表单, curl)
  3. 轮询 -> 下载 -> 汇总 result.json

Key 只读不写, 输出中打码.
"""
import json
import os
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_toapis import load_key  # 复用 key 加载逻辑

BASE = "https://api.toapis.cn"
NOREF = "--noref" in sys.argv   # 无参考图模式: 内页也走文生图, 只靠 STYLE_ANCHOR 锁风格
OUT_DIR = (r"E:\project\Loom\deliverables\toapis-picturebook-noref-test" if NOREF
           else r"E:\project\Loom\deliverables\toapis-picturebook-test")
MODEL = "gpt-image-2.5-flare-vip"
QUALITY = "low"            # 测试用 low 档; 成品可切 high
SIZE = "1248x1664"         # 小红书 3:4 竖版自定义像素, 提交失败则回退 1024x1536
FALLBACK_SIZE = "1024x1536"
POLL_INTERVAL = 5
POLL_TIMEOUT = 600
CURL = r"C:/Windows/System32/curl.exe"

STYLE_ANCHOR = (
    "hand-drawn children's picture book illustration in wax crayon and oil pastel, "
    "clearly visible crayon strokes and scribble texture, grainy off-white cream paper background, "
    "matte flat color fills with slightly rough uneven edges, childlike naive drawing style, "
    "low-saturation warm earthy color palette (honey yellow, cream, sage green, terracotta, muted cocoa brown), "
    "simple composition with generous negative space, one single scene per page, cozy bedtime mood. "
    "IMPORTANT: NOT anime, NOT manga, no glossy digital airbrushing, no smooth gradient shading, "
    "no sparkling highlight eyes, no 3D rendering, no vector-clean outlines, no photorealism"
)
CHAR_ASU = (
    "Asu, a 4-year-old Chinese boy, round face, short slightly-tousled black hair, "
    "simple small round black eyes, childlike naive facial features, wearing an orange-yellow hoodie "
    "and blue overalls, same character design, consistent appearance"
)

COVER = {
    "tag": "p01-cover",
    "kind": "text2img",
    "prompt": (
        f"{STYLE_ANCHOR}. {CHAR_ASU}. "
        "Scene: Asu crouches down on a garden path, looking closely at a tiny snail on a big green leaf, "
        "morning soft light. "
        "画面底部保留约四分之一高度的干净留白作为文字区, 只在文字区内渲染一遍标题文字「阿苏和小蜗牛」, "
        "文字不要重复, 画面其余位置不要出现任何文字"
    ),
}

def build_page_prompt(scene, text):
    """按模式拼内页 prompt: 参考图模式靠参考图锁风格; 无参考图模式只能靠 STYLE_ANCHOR."""
    head = (f"保持参考图的蜡笔油画棒绘本风格和角色设计完全一致, 绝不是照片. {CHAR_ASU}. "
            if not NOREF else f"{STYLE_ANCHOR}. {CHAR_ASU}. ")
    return (head + scene +
            f"画面底部保留约四分之一高度的干净留白作为文字区, 只在文字区内渲染一遍文字「{text}」, "
            "文字不要重复, 画面其余位置不要出现任何文字")


PAGES = [
    {
        "tag": "p02-follow",
        "prompt": build_page_prompt(
            "Scene: Asu tiptoes slowly behind the tiny snail on the garden path, following it, "
            "both moving in the same direction. ",
            "阿苏轻轻地跟着小蜗牛，一步一步，慢慢的。"),
    },
    {
        "tag": "p03-rain",
        "prompt": build_page_prompt(
            "Scene: light rain falling, Asu holds a big green leaf above the tiny snail like an umbrella, "
            "protecting it, warm caring mood. ",
            "下雨了，阿苏摘了一片大叶子，给小蜗牛挡雨。"),
    },
    {
        "tag": "p04-goodbye",
        "prompt": build_page_prompt(
            "Scene: the rain stopped, the tiny snail crawls onto a small colorful flower, Asu waves goodbye "
            "to it with a smile, sunset warm light. ",
            "小蜗牛爬到花朵上，阿苏挥挥手说：明天见！"),
    },
]

CTX = ssl.create_default_context()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def http_json(method, url, key, body=None, timeout=60):
    data = None
    headers = {"Authorization": f"Bearer {key}", "User-Agent": UA}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:500]}


def submit_generations(key, prompt, size):
    payload = {"model": MODEL, "prompt": prompt, "quality": QUALITY, "size": size, "n": 1}
    code, resp = http_json("POST", f"{BASE}/v1/images/generations", key, payload)
    return code, resp


def submit_edits(key, prompt, ref_url):
    """VIP 版参考图走 /v1/images/edits, multipart 表单, image 字段放公网 URL."""
    args = [
        CURL, "-sS", "--ssl-no-revoke", "-X", "POST", f"{BASE}/v1/images/edits",
        "-H", f"Authorization: Bearer {key}",
        "-H", f"User-Agent: {UA}",
        "-F", f"model={MODEL}",
        "-F", f"prompt={prompt}",
        "-F", f"image={ref_url}",
        "-F", f"quality={QUALITY}",
        "-F", f"size={SIZE}",
        "-F", "n=1",
    ]
    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
    raw = (p.stdout or "").strip()
    if p.returncode != 0:
        return -1, {"curl_error": (p.stderr or "")[:400]}
    try:
        return 200, json.loads(raw)
    except json.JSONDecodeError:
        return -2, {"raw": raw[:500]}


def poll_task(key, task_id, tag):
    """轮询; 优先 generations 端点, 首个 404 后切换 edits 端点."""
    endpoint = "generations"
    deadline = time.time() + POLL_TIMEOUT
    polls = 0
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        polls += 1
        code, st = http_json("GET", f"{BASE}/v1/images/{endpoint}/{task_id}", key)
        if code == 404 and endpoint == "generations":
            endpoint = "edits"
            print(f"[{tag}] generations 404, switch poll endpoint -> edits", flush=True)
            continue
        status = (st or {}).get("status", f"http_{code}")
        prog = (st or {}).get("progress")
        print(f"[{tag}] poll#{polls} ({endpoint}) status={status} progress={prog}", flush=True)
        if status in ("completed", "failed"):
            return polls, st
    return polls, {"status": "timeout"}


def extract_url(final):
    data = (final.get("result") or {}).get("data")
    if isinstance(data, list) and data:
        first = data[0]
        return first.get("url") if isinstance(first, dict) else (first if isinstance(first, str) else None)
    if isinstance(data, dict):
        return data.get("url")
    if isinstance(data, str):
        return data
    return None


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def new_rec(spec, kind):
    return {"tag": spec["tag"], "kind": kind, "model": MODEL, "quality": QUALITY, "size": SIZE,
            "ok": False, "task_id": None, "status": None, "total_s": None, "polls": 0,
            "image_url": None, "file": None, "file_bytes": None, "usage": None, "error": None,
            "raw_submit": None}


def run_cover(key, results, holder):
    spec = COVER
    rec = new_rec(spec, "text2img")
    t0 = time.time()
    size = SIZE
    code, resp = submit_generations(key, spec["prompt"], size)
    if (code != 200 or "id" not in (resp or {})) and size != FALLBACK_SIZE:
        print(f"[{spec['tag']}] size {size} rejected (http={code}), fallback -> {FALLBACK_SIZE}", flush=True)
        size = FALLBACK_SIZE
        rec["size"] = size
        code, resp = submit_generations(key, spec["prompt"], size)
    rec["raw_submit"] = resp
    print(f"[{spec['tag']}] submit http={code} resp={json.dumps(resp, ensure_ascii=False)[:300]}", flush=True)
    if code != 200 or "id" not in (resp or {}):
        rec["error"] = f"submit failed http={code}: {json.dumps(resp, ensure_ascii=False)[:400]}"
        rec["total_s"] = round(time.time() - t0, 1)
        results.append(rec)
        return
    rec["task_id"] = resp["id"]

    rec["polls"], final = poll_task(key, rec["task_id"], spec["tag"])
    rec["total_s"] = round(time.time() - t0, 1)
    rec["status"] = (final or {}).get("status", "timeout")
    if rec["status"] != "completed":
        rec["error"] = f"final status={rec['status']}: {json.dumps((final or {}).get('error'), ensure_ascii=False)[:300]}"
        results.append(rec)
        return
    url = extract_url(final)
    rec["image_url"] = url
    usage = final.get("usage") or (final.get("result") or {}).get("usage")
    if usage:
        rec["usage"] = usage
    holder["cover_url"] = url   # 内页参考图等待此值
    if url:
        path = os.path.join(OUT_DIR, f"{spec['tag']}.png")
        try:
            rec["file_bytes"] = download(url, path)
            rec["file"] = path
            rec["ok"] = True
            print(f"[{spec['tag']}] downloaded {rec['file_bytes']} bytes -> {path}", flush=True)
        except Exception as e:
            rec["error"] = f"download failed: {e}"
    results.append(rec)


def run_page(key, spec, results, holder):
    rec = new_rec(spec, "text2img" if NOREF else "ref2img")
    t0 = time.time()
    if NOREF:
        # 无参考图: 内页与封面一样走文生图, 无需等待封面, 4 张全并行
        code, resp = submit_generations(key, spec["prompt"], SIZE)
        if (code != 200 or "id" not in (resp or {})) and SIZE != FALLBACK_SIZE:
            rec["size"] = FALLBACK_SIZE
            code, resp = submit_generations(key, spec["prompt"], FALLBACK_SIZE)
    else:
        # 等待封面完成拿到参考图 URL
        deadline = time.time() + POLL_TIMEOUT
        while "cover_url" not in holder and time.time() < deadline:
            time.sleep(2)
        ref_url = holder.get("cover_url")
        if not ref_url:
            rec["error"] = "cover_url not available, skip"
            results.append(rec)
            return
        rec["ref_url"] = ref_url
        code, resp = submit_edits(key, spec["prompt"], ref_url)
    rec["raw_submit"] = resp
    print(f"[{spec['tag']}] submit http={code} resp={json.dumps(resp, ensure_ascii=False)[:300]}", flush=True)
    if code != 200 or "id" not in (resp or {}):
        rec["error"] = f"submit failed http={code}: {json.dumps(resp, ensure_ascii=False)[:400]}"
        rec["total_s"] = round(time.time() - t0, 1)
        results.append(rec)
        return
    rec["task_id"] = resp["id"]

    rec["polls"], final = poll_task(key, rec["task_id"], spec["tag"])
    rec["total_s"] = round(time.time() - t0, 1)
    rec["status"] = (final or {}).get("status", "timeout")
    if rec["status"] != "completed":
        rec["error"] = f"final status={rec['status']}: {json.dumps((final or {}).get('error'), ensure_ascii=False)[:300]}"
        results.append(rec)
        return
    url = extract_url(final)
    rec["image_url"] = url
    usage = final.get("usage") or (final.get("result") or {}).get("usage")
    if usage:
        rec["usage"] = usage
    if url:
        path = os.path.join(OUT_DIR, f"{spec['tag']}.png")
        try:
            rec["file_bytes"] = download(url, path)
            rec["file"] = path
            rec["ok"] = True
            print(f"[{spec['tag']}] downloaded {rec['file_bytes']} bytes -> {path}", flush=True)
        except Exception as e:
            rec["error"] = f"download failed: {e}"
    results.append(rec)


def main():
    key, src = load_key()
    if not key:
        print("FATAL: 找不到 API Key (TOAPI_APIKEY / TOAPIS_API_KEY, env 与注册表均为空)")
        sys.exit(2)
    print(f"key source = {src}, key = {key[:8]}...{key[-4:]} (len={len(key)})", flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    results = []
    holder = {}
    threads = [threading.Thread(target=run_cover, args=(key, results, holder), daemon=True)]
    threads += [threading.Thread(target=run_page, args=(key, s, results, holder), daemon=True) for s in PAGES]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = sorted(results, key=lambda r: r["tag"])
    ok_n = sum(1 for r in summary if r["ok"])
    print(f"=== DONE {ok_n}/{len(summary)} ok ===", flush=True)
    out = os.path.join(OUT_DIR, "result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"saved -> {out}", flush=True)


if __name__ == "__main__":
    main()
