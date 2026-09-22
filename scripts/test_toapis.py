# -*- coding: utf-8 -*-
"""ToAPIs GPT-Image-2.5 三版本真实接口联测.

流程: 读注册表/环境变量取 key -> 三版本并行提交 -> 轮询 -> 下载图片 -> 输出汇总 JSON.
Key 只读不写, 输出中打码.
"""
import json
import os
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
import winreg

BASE = "https://api.toapis.cn"
OUT_DIR = r"E:\project\Loom\deliverables\toapis-test"
PROMPT = "儿童绘本水彩风格, 一只橘色小狐狸坐在开满野花的草地上, 抬头看蝴蝶"
POLL_INTERVAL = 5
POLL_TIMEOUT = 600  # 单任务最长轮询 10 分钟

TASKS = [
    {
        "tag": "normal-flare-1k",
        "model": "gpt-image-2.5-flare",
        "payload": {"model": "gpt-image-2.5-flare", "prompt": PROMPT, "size": "1:1", "resolution": "1K", "n": 1},
    },
    {
        "tag": "vip-flare-low",
        "model": "gpt-image-2.5-flare-vip",
        "payload": {"model": "gpt-image-2.5-flare-vip", "prompt": PROMPT, "quality": "low", "size": "1024x1024", "n": 1},
    },
    {
        "tag": "official-flare-low",
        "model": "gpt-image-2.5-flare-official",
        "payload": {"model": "gpt-image-2.5-flare-official", "prompt": PROMPT, "quality": "low", "size": "1024x1024", "n": 1},
    },
]


def load_key():
    """依次尝试: 进程环境 -> User 注册表 -> Machine 注册表. 支持两个变量名."""
    for name in ("TOAPI_APIKEY", "TOAPIS_API_KEY"):
        v = os.environ.get(name)
        if v:
            return v.strip(), f"env:{name}"
    for name in ("TOAPI_APIKEY", "TOAPIS_API_KEY"):
        for scope, hive, path in (
            ("User", winreg.HKEY_CURRENT_USER, "Environment"),
            ("Machine", winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        ):
            try:
                with winreg.OpenKey(hive, path) as k:
                    v, _ = winreg.QueryValueEx(k, name)
                    if v and v.strip():
                        return v.strip(), f"registry:{scope}:{name}"
            except OSError:
                continue
    return None, None


CTX = ssl.create_default_context()


def http(method, url, key, body=None, timeout=60):
    data = None
    headers = {"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
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


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        data = r.read()
    with open(path, "wb") as f:
        f.write(data)
    return len(data)


def run_task(key, spec, results):
    tag = spec["tag"]
    rec = {"tag": tag, "model": spec["model"], "ok": False, "submit_ms": None, "total_s": None, "task_id": None, "status": None, "error": None, "image_url": None, "file": None, "file_bytes": None, "polls": 0, "raw_submit": None}
    t0 = time.time()
    code, resp = http("POST", f"{BASE}/v1/images/generations", key, spec["payload"])
    rec["submit_ms"] = round((time.time() - t0) * 1000)
    rec["raw_submit"] = resp
    print(f"[{tag}] submit http={code} resp={json.dumps(resp, ensure_ascii=False)[:300]}", flush=True)
    if code != 200 or "id" not in (resp or {}):
        rec["error"] = f"submit failed http={code}: {json.dumps(resp, ensure_ascii=False)[:400]}"
        results.append(rec)
        return
    task_id = resp["id"]
    rec["task_id"] = task_id

    deadline = time.time() + POLL_TIMEOUT
    final = None
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        rec["polls"] += 1
        code, st = http("GET", f"{BASE}/v1/images/generations/{task_id}", key)
        status = (st or {}).get("status", f"http_{code}")
        prog = (st or {}).get("progress")
        print(f"[{tag}] poll#{rec['polls']} status={status} progress={prog}", flush=True)
        if status in ("completed", "failed"):
            final = st
            break
    rec["total_s"] = round(time.time() - t0, 1)
    rec["status"] = (final or {}).get("status", "timeout")

    if not final or final.get("status") != "completed":
        rec["error"] = f"final status={rec['status']}: {json.dumps((final or {}).get('error'), ensure_ascii=False)[:300]}"
        results.append(rec)
        return

    # 提取图片 URL: 兼容 result.data[].url / result.data.url / result.data[0] 字符串
    url = None
    data = ((final.get("result") or {}).get("data"))
    if isinstance(data, list) and data:
        first = data[0]
        url = first.get("url") if isinstance(first, dict) else (first if isinstance(first, str) else None)
    elif isinstance(data, dict):
        url = data.get("url")
    elif isinstance(data, str):
        url = data
    rec["image_url"] = url
    usage = final.get("usage") or (final.get("result") or {}).get("usage")
    if usage:
        rec["usage"] = usage

    if url:
        ext = ".png" if ".png" in url.split("?")[0] else ".jpg"
        path = os.path.join(OUT_DIR, f"{tag}{ext}")
        try:
            rec["file_bytes"] = download(url, path)
            rec["file"] = path
            rec["ok"] = True
            print(f"[{tag}] downloaded {rec['file_bytes']} bytes -> {path}", flush=True)
        except Exception as e:
            rec["error"] = f"download failed: {e}"
    else:
        rec["error"] = "no image url in result: " + json.dumps(final.get("result"), ensure_ascii=False)[:400]
    results.append(rec)


def main():
    key, src = load_key()
    if not key:
        print("FATAL: 找不到 API Key (TOAPI_APIKEY / TOAPIS_API_KEY, env 与注册表均为空)")
        sys.exit(2)
    print(f"key source = {src}, key = {key[:8]}...{key[-4:]} (len={len(key)})", flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    results = []
    threads = [threading.Thread(target=run_task, args=(key, s, results), daemon=True) for s in TASKS]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = sorted(results, key=lambda r: r["tag"])
    out = os.path.join(OUT_DIR, "result.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("=== SUMMARY ===", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print(f"saved -> {out}", flush=True)


if __name__ == "__main__":
    main()
