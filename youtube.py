"""YouTube の無料公開動画を yt-dlp で保存する。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from common import die, log

PUBLIC_AVAILABILITY = {"public", "unlisted"}


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


def fetch_metadata(tool: str, url: str) -> dict[str, Any]:
    result = subprocess.run(
        [tool, "--no-warnings", "--no-playlist", "--dump-single-json",
         "--skip-download", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        die(f"メタデータを取得できませんでした: "
            f"{result.stderr.strip()[:300]}")
    try:
        data = json.loads(result.stdout)
    except ValueError:
        die("メタデータを解析できませんでした。")
    return data if isinstance(data, dict) else {}


def download(tool: str, url: str, out_dir: str, quality: str | None,
             force: bool, ffmpeg: str) -> int:
    """無料公開の動画を 1 本保存する。"""
    meta = fetch_metadata(tool, url)
    availability = meta.get("availability")
    if availability is not None and availability not in PUBLIC_AVAILABILITY:
        die(f"無料公開ではないため中止します: availability={availability}")
    if meta.get("is_live"):
        die("ライブ配信中は対象外です。")

    title = meta.get("title") or meta.get("id") or url
    duration = meta.get("duration")
    log(f"[YouTube] {title}")
    if duration:
        log(f"   長さ: {int(duration) // 60} 分 {int(duration) % 60} 秒")
    if meta.get("license"):
        log(f"   ライセンス: {meta['license']}")

    height = None
    if quality:
        try:
            height = int(quality.rstrip("p"))
        except ValueError:
            height = None
    selector = "bv*+ba/b"
    if height:
        selector = (f"bv*[height<={height}]+ba/b[height<={height}]/b")

    args = [tool]
    args += ["--force-overwrites"] if force else ["--no-overwrites"]
    quality_suffix = f" {height}p" if height else ""
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
