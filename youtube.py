"""YouTube の無料公開動画を保存する (DRM 付きはライセンスを取得して復号)。"""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import shutil
import subprocess
import time
from typing import Any

from common import die, log

PUBLIC_AVAILABILITY = {"public", "unlisted"}
DRM_FLAG = "DRM"

HOOK_SCRIPT = r"""
(function () {
  if (window.__ddCap) { return; }
  const cap = (window.__ddCap = []);
  let timer = null;
  const sync = function () {
    if (timer) { return; }
    timer = setTimeout(function () {
      timer = null;
      try { document.documentElement.dataset.cap = JSON.stringify(cap); }
      catch (e) {}
    }, 250);
  };
  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const rec = { kind: 'fetch',
      url: String(typeof input === 'string' ? input : (input && input.url) || input),
      method: (init && init.method) || 'GET', body: null,
      status: null, resp: null };
    try { if (init && init.body) { rec.body = String(init.body).slice(0, 20000); } }
    catch (e) {}
    cap.push(rec);
    sync();
    const p = origFetch.apply(this, arguments);
    p.then(function (r) {
      rec.status = r.status;
      return r.clone().text().then(function (t) {
        rec.resp = t.slice(0, 20000);
        sync();
      });
    }).catch(function () {});
    return p;
  };
  const X = window.XMLHttpRequest;
  const origOpen = X.prototype.open;
  const origSend = X.prototype.send;
  X.prototype.open = function (method, url) {
    this.__ddRec = { kind: 'xhr', method: String(method), url: String(url),
      body: null, status: null, resp: null };
    cap.push(this.__ddRec);
    return origOpen.apply(this, arguments);
  };
  X.prototype.send = function (body) {
    if (this.__ddRec && body != null) {
      try { this.__ddRec.body = String(body).slice(0, 20000); } catch (e) {}
    }
    const rec = this.__ddRec;
    this.addEventListener('loadend', function () {
      if (!rec) { return; }
      rec.status = this.status;
      try { rec.resp = String(this.responseText).slice(0, 20000); } catch (e) {}
      sync();
    });
    return origSend.apply(this, arguments);
  };
  return 'hooked';
})();
"""

INSTALL_SCRIPT = (
    "if (!document.documentElement || !window.trustedTypes) { return null; }"
    "if (document.documentElement.dataset.hook) { return 'already'; }"
    "let policy;"
    "try { policy = window.trustedTypes.createPolicy('ddpipe' + "
    "(window.__ddN = (window.__ddN || 0) + 1), {"
    "  createScript: function (s) { return s; } }); }"
    "catch (e) { policy = null; }"
    "if (!policy) { return null; }"
    "const s = document.createElement('script');"
    "s.textContent = policy.createScript(arguments[0]);"
    "document.documentElement.dataset.hook = '1';"
    "document.documentElement.appendChild(s);"
    "return 'injected';"
)


# --------------------------------------------------------------- base helpers

def resolve_ytdlp(explicit: str | None) -> str:
    if explicit:
        if not os.path.exists(explicit):
            die(f"yt-dlp が見つかりません: {explicit}")
        return explicit
    found = shutil.which("yt-dlp")
    if not found:
        die("yt-dlp が PATH にありません。インストールするか "
            "--yt-dlp で指定してください。")
    return found


def fetch_metadata(tool: str, url: str, drm: bool = False) -> dict[str, Any]:
    args = [tool, "--no-warnings", "--no-playlist", "--dump-single-json",
            "--skip-download", "--ignore-no-formats-error"]
    if drm:
        args += ["--allow-unplayable-formats",
                 "--extractor-args", "youtube:formats=dashy"]
    result = subprocess.run(args + [url], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _has_streams(meta: dict[str, Any]) -> bool:
    for item in meta.get("formats") or []:
        if (item.get("vcodec") or "none") != "none" and item.get("height"):
            return True
    return False


def _has_drm(meta: dict[str, Any]) -> bool:
    for item in meta.get("formats") or []:
        if item.get("has_drm") or DRM_FLAG in (item.get("format_note") or ""):
            return True
    return False


def _check_license(meta: dict[str, Any]) -> None:
    availability = meta.get("availability")
    if availability is not None and availability not in PUBLIC_AVAILABILITY:
        die(f"無料公開ではないため中止します: availability={availability}")
    if meta.get("is_live"):
        die("ライブ配信中は対象外です。")


# ---------------------------------------------------------- DRM key capture

def capture_license(port: int, url: str,
                    timeout: float = 150.0) -> list[dict[str, Any]]:
    """Firefox で再生し、ライセンス応答を採取する。"""
    from marionette_driver.marionette import Marionette

    log("   ライセンスを取得するため Firefox で再生します ...")
    client = Marionette(port=port)
    try:
        client.start_session()
    except Exception as error:  # noqa: BLE001
        die(f"Firefox の Marionette に接続できません (port {port}): "
            f"{type(error).__name__}")
    try:
        client.navigate(url)
        installed = False
        for _ in range(150):
            time.sleep(0.1)
            try:
                if client.execute_script(INSTALL_SCRIPT, [HOOK_SCRIPT]):
                    installed = True
                    break
            except Exception:  # noqa: BLE001 - 読み込み中の失敗は無視
                continue
        if not installed:
            die("ライセンス採取用のフックを注入できませんでした。")
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            try:
                client.execute_script(
                    "const b = document.querySelector('.ytp-skip-ad-button');"
                    "if (b) { b.click(); }"
                    "const p = document.querySelector('.ytp-large-play-button');"
                    "if (p && p.offsetParent !== null) { p.click(); }"
                    "const v = document.querySelector('video');"
                    "if (v && v.paused) { v.muted = true; "
                    "v.play().catch(function(){}); }"
                    "return 1;")
                raw = client.execute_script(
                    "return document.documentElement.dataset.cap || null;")
            except Exception:  # noqa: BLE001
                continue
            if raw and "get_drm_license" in raw:
                return json.loads(raw)
        die("ライセンス要求を採取できませんでした。動画を再生できるか確認して"
            "ください。")
    finally:
        client.close()


def _extract_pssh(path: str) -> bytes | None:
    with open(path, "rb") as handle:
        data = handle.read(4 << 20)
    for index in range(len(data) - 4):
        if data[index:index + 4] != b"pssh":
            continue
        start = index - 4
        if start < 0:
            continue
        size = int.from_bytes(data[start:start + 4], "big")
        if 32 <= size <= 8192 and start + size <= len(data):
            return data[start:start + size]
    return None


def _license_keys(captures: list[dict[str, Any]], pssh: bytes,
                  device_path: str) -> dict[str, str]:
    """採取した要求をひな形に、自前の CDM でライセンスを取得する。"""
    import requests
    from pywidevine import Cdm, Device, PSSH

    entry = next((item for item in captures
                  if "get_drm_license" in (item.get("url") or "")
                  and item.get("body")), None)
    if not entry:
        die("ライセンス要求のひな形を採取できませんでした。")
    body = json.loads(entry["body"])
    headers = dict(entry.get("headers") or {})
    url = entry["url"]
    if not url.startswith("http"):
        url = "https://www.youtube.com" + url

    device = Device.load(device_path)
    cdm = Cdm.from_device(device)
    session_id = cdm.open()
    try:
        challenge = cdm.get_license_challenge(
            session_id, PSSH(base64.b64encode(pssh).decode()))
        body["licenseRequest"] = base64.b64encode(challenge).decode()
        headers["Content-Type"] = "application/json"
        response = requests.post(url, data=json.dumps(body), headers=headers,
                                 timeout=60)
        if response.status_code != 200:
            die(f"ライセンス取得に失敗しました: HTTP "
                f"{response.status_code} {response.text[:300]}")
        encoded = (response.json().get("license") or "")
        if not encoded:
            die("ライセンス応答に license がありません。")
        cleaned = re.sub(r"[^A-Za-z0-9_\-+/=]", "", encoded).rstrip("=")
        license_bytes = base64.urlsafe_b64decode(
            cleaned + "=" * (-len(cleaned) % 4))
        cdm.parse_license(session_id, license_bytes)
        keys = {str(key.kid).lower().replace("-", ""): key.key.hex()
                for key in cdm.get_keys(session_id) if len(key.key) == 16}
    finally:
        cdm.close(session_id)
    if not keys:
        die("ライセンスからキーを取得できませんでした。")
    return keys


# ------------------------------------------------------------- download/decrypt

def _tenc_kid(path: str, keys: dict[str, str]) -> str | None:
    with open(path, "rb") as handle:
        data = handle.read(4 << 20)
    index = data.find(b"tenc")
    if index < 0:
        return None
    window = data[index:index + 64]
    for kid in keys:
        if bytes.fromhex(kid) in window:
            return kid
    return None


def _decrypt(ffmpeg: str, source: str, destination: str, kid: str,
             key: str) -> None:
    result = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-decryption_key", key,
         "-i", source, "-map", "0", "-c", "copy", destination],
        capture_output=True)
    if result.returncode != 0:
        die("復号に失敗しました: "
            f"{result.stderr.decode('utf-8', 'replace').strip()[:400]}")


def _pick_encrypted(tool: str, url: str, workdir: str,
                    height: int | None) -> tuple[str, str]:
    selector = "bv*"
    if height:
        selector = (
            f"bv*[height<={height}][protocol=dash][vcodec^=avc1]"
            f"/bv*[height<={height}][protocol=dash]"
            f"/bv*[height<={height}]")
    video_out = os.path.join(workdir, "video.%(ext)s")
    audio_out = os.path.join(workdir, "audio.%(ext)s")
    common_args = [tool, "--no-warnings", "--allow-unplayable-formats",
                   "--extractor-args", "youtube:formats=dashy",
                   "-S", "vcodec:h264,acodec:aac", "--no-playlist"]
    for fmt, output in ((selector, video_out),
                        ("ba[ext=m4a][protocol=dash]/ba[ext=m4a]/ba",
                         audio_out)):
        result = subprocess.run(common_args + ["-f", fmt, "-o", output, url],
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            die(f"暗号化ストリームの取得に失敗しました: "
                f"{result.stderr.strip()[-400:]}")
    videos = [p for p in glob.glob(os.path.join(workdir, "video.*"))
              if not p.endswith(".dec")]
    audios = [p for p in glob.glob(os.path.join(workdir, "audio.*"))
              if not p.endswith(".dec")]
    if not videos or not audios:
        die("暗号化ストリームのファイルが見つかりません。")
    return videos[0], audios[0]


def _download_drm(tool: str, url: str, out_dir: str, meta: dict[str, Any],
                  quality: str | None, ffmpeg: str, port: int,
                  output_path: str) -> None:
    from device import resolve_device

    heights = [item.get("height") for item in meta.get("formats") or []
               if item.get("height")
               and (item.get("vcodec") or "none") != "none"
               and (item.get("has_drm")
                    or DRM_FLAG in (item.get("format_note") or ""))]
    height = int(quality.rstrip("p")) if quality else None
    if height and heights:
        eligible = [h for h in heights if h <= height]
        height = max(eligible) if eligible else min(heights)
    log(f"   DRM 動画です (選択可能な高さ: {sorted(set(heights))})")

    workdir = os.path.join(out_dir, f"yt_{meta.get('id') or 'drm'}")
    os.makedirs(workdir, exist_ok=True)
    video_enc, audio_enc = _pick_encrypted(tool, url, workdir, height)

    pssh = _extract_pssh(video_enc)
    if not pssh:
        die("暗号化ストリームから PSSH を取得できませんでした。")
    captures = capture_license(port, url)
    device_path, remember = resolve_device(None)
    if remember:
        from device import config_path, load_config, save_config
        config = load_config()
        config["device"] = device_path
        save_config(config)
        log(f"   デバイスファイルを記憶しました: {config_path()}")
    keys = _license_keys(captures, pssh, device_path)
    log(f"   キー: {len(keys)} 件")

    video_dec = os.path.join(workdir, "video.dec.mp4")
    audio_dec = os.path.join(workdir, "audio.dec.m4a")
    for source, destination in ((video_enc, video_dec),
                                (audio_enc, audio_dec)):
        kid = _tenc_kid(source, keys)
        if not kid:
            die(f"ストリームの KID に対応するキーがありません: {source}")
        log(f"   復号: {os.path.basename(source)} ({kid})")
        _decrypt(ffmpeg, source, destination, kid, keys[kid])

    result = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", video_dec, "-i", audio_dec,
         "-map", "0:0", "-map", "1:0", "-c", "copy", output_path],
        capture_output=True)
    if result.returncode != 0:
        die("多重化に失敗しました: "
            f"{result.stderr.decode('utf-8', 'replace').strip()[-400:]}")

    for path in (video_enc, audio_enc, video_dec, audio_dec):
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir(workdir)
    except OSError:
        pass


# ------------------------------------------------------------------ public API

def download(tool: str, url: str, out_dir: str, quality: str | None,
             force: bool, ffmpeg: str, port: int) -> int:
    meta = fetch_metadata(tool, url)
    if not meta:
        die("メタデータを取得できませんでした。")
    _check_license(meta)

    title = meta.get("title") or meta.get("id") or url
    duration = meta.get("duration")
    log(f"[YouTube] {title}")
    if duration:
        log(f"   長さ: {int(duration) // 60} 分 {int(duration) % 60} 秒")
    if meta.get("license"):
        log(f"   ライセンス: {meta['license']}")

    height = None
    if quality:
        match = re.fullmatch(r"(\d+)p", quality.strip())
        if not match:
            die("--quality は 1080p や 144p のように指定してください。")
        height = int(match.group(1))
    suffix = f" {height}p" if height else ""
    output_path = os.path.join(
        out_dir, f"{_safe(title)} [{meta.get('id')}]{suffix}.mp4")

    drm = False
    if not _has_streams(meta):
        drm_meta = fetch_metadata(tool, url, drm=True)
        if _has_drm(drm_meta):
            drm = True
            meta = drm_meta
            if height is None:
                height = max(
                    (item.get("height") for item in meta.get("formats") or []
                     if item.get("height")), default=None)
                suffix = f" {height}p" if height else ""
                output_path = os.path.join(
                    out_dir, f"{_safe(title)} [{meta.get('id')}]{suffix}.mp4")
    if drm:
        if not force and os.path.exists(output_path):
            log(f"   スキップ (既存): {output_path}")
            return 0
        _download_drm(tool, url, out_dir, meta, quality, ffmpeg, port,
                      output_path)
        verify_playable(ffmpeg, output_path)
        log(f"   完了: {output_path} ({os.path.getsize(output_path)} bytes)")
        return 0

    args = [tool]
    args += ["--force-overwrites"] if force else ["--no-overwrites"]
    quality_suffix = f" {height}p" if height else ""
    selector = "bv*+ba/b"
    if height:
        selector = f"bv*[height<={height}]+ba/b[height<={height}]/b"
    args += [
        "-S", "vcodec:h264,acodec:aac",
        "-f", selector,
        "--merge-output-format", "mp4",
        "--ffmpeg-location", ffmpeg,
        "--no-playlist",
        "--newline",
        "-o", os.path.join(
            out_dir, f"%(title)s [%(id)s]{quality_suffix}.%(ext)s"),
        url,
    ]
    before = _snapshot(out_dir)
    log("   保存しています ...")
    result = subprocess.run(args)
    if result.returncode != 0:
        die(f"保存に失敗しました (exit={result.returncode})")
    changed = [path for path, mtime in _snapshot(out_dir).items()
               if before.get(path) != mtime]
    for path in changed:
        verify_playable(ffmpeg, path)
    return 0


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def _snapshot(folder: str) -> dict[str, float]:
    result: dict[str, float] = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return result
    for name in names:
        if name.lower().endswith(".mp4"):
            path = os.path.join(folder, name)
            try:
                result[path] = os.path.getmtime(path)
            except OSError:
                continue
    return result


def verify_playable(ffmpeg: str, path: str, seconds: int = 10) -> None:
    """先頭を復号・デコードして、再生できる状態か確認する。"""
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-t", str(seconds), "-i", path,
         "-f", "null", "-"],
        capture_output=True)
    text = result.stderr.decode("utf-8", "replace")
    errors = [line for line in text.splitlines() if line.strip()]
    log(f"   再生確認: {os.path.basename(path)} "
        f"(デコードエラー {len(errors)} 行)")
    if errors:
        log(f"   !! 先頭 {len(errors)} 行にエラーがあります。"
            "再生できない場合は --force で取り直してください。")
