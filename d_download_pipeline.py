#!/usr/bin/env python3
"""d-download-pipeline - CLI 本体。

認証情報 (Cookie, デバイスファイル) はリポジトリに含めず、引数または
キャッシュディレクトリから読み込む。
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from typing import Any, Iterable

import requests
from marionette_driver.marionette import Marionette
from pywidevine import Cdm, Device, PSSH

BASE = "https://animestore.docomo.ne.jp"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
    "Gecko/20100101 Firefox/140.0"
)
QUALITY_HEIGHT = {"1080p": 1080, "720p": 720, "480p": 480, "360p": 360}
DEFAULT_PORT = 2828
MIN_OUTPUT_BYTES = 1 << 20


# --------------------------------------------------------------------- utils

def log(message: str) -> None:
    print(message, flush=True)


def die(message: str) -> None:
    log(f"!! {message}")
    raise SystemExit(1)


def default_cookie_path() -> str:
    base = os.environ.get("D_DOWNLOAD_CACHE_DIR")
    if base:
        return os.path.join(base, "cookies.txt")
    return os.path.join(os.path.expanduser("~"), ".cache",
                        "d-download-pipeline", "cookies.txt")


def resolve_tool(explicit: str | None, name: str, flag: str) -> str:
    if explicit:
        if not os.path.exists(explicit):
            die(f"{flag} の実行ファイルが見つかりません: {explicit}")
        return explicit
    found = shutil.which(name)
    if not found:
        die(f"{name} が PATH にありません。{flag} で指定してください。")
    return found


def parse_episode_selection(text: str, available: Iterable[int]) -> list[int]:
    wanted: list[int] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            try:
                wanted.extend(range(int(start), int(end) + 1))
            except ValueError:
                die(f"--ep の書式が不正です: {token!r}")
        else:
            try:
                wanted.append(int(token))
            except ValueError:
                die(f"--ep の書式が不正です: {token!r}")
    known = set(available)
    missing = [n for n in wanted if n not in known]
    if missing:
        log(f"   注意: 存在しない話数を除外します: {missing}")
    # 重複を除き、指定順を保つ
    seen: set[int] = set()
    result = []
    for n in wanted:
        if n in known and n not in seen:
            seen.add(n)
            result.append(n)
    return result


def pick_representation(representations: list[dict], target_height: int) -> dict:
    exact = [r for r in representations if r.get("height") == target_height]
    if exact:
        candidates = exact
    else:
        nearest = min(
            (r.get("height") or 0 for r in representations),
            key=lambda h: abs(h - target_height),
        )
        candidates = [r for r in representations if r.get("height") == nearest]
    return max(candidates, key=lambda r: r.get("bandwidth", 0))


# ------------------------------------------------------------------ pipeline

class Pipeline:
    def __init__(
        self,
        device_path: str,
        mp4decrypt: str,
        ffmpeg: str,
        cookie_path: str,
        refresh_cookies: bool,
        port: int,
        force: bool,
    ) -> None:
        self.device_path = device_path
        self.mp4decrypt = mp4decrypt
        self.ffmpeg = ffmpeg
        self.cookie_path = cookie_path
        self.refresh_cookies = refresh_cookies
        self.port = port
        self.force = force
        self.headers: dict[str, str] = {}
        self.cdm: Cdm | None = None

    # -- cookies ---------------------------------------------------------
    def load_cookies(self) -> None:
        if (not self.refresh_cookies and os.path.exists(self.cookie_path)
                and os.path.getsize(self.cookie_path) > 10):
            with open(self.cookie_path, encoding="utf-8") as handle:
                cookie_header = handle.read().strip()
            if cookie_header:
                log(f"[1] Cookie を再利用: {self.cookie_path}")
                self.headers = {"Cookie": cookie_header,
                                "User-Agent": USER_AGENT}
                return
        log(f"[1] Firefox から Cookie を取得 (port {self.port}) ...")
        cookies = self._cookies_from_browser()
        if not cookies:
            die("Cookie を取得できませんでした。Firefox の起動と "
                "--port を確認してください。")
        cookie_header = "; ".join(
            f"{item['name']}={item['value']}" for item in cookies)
        self.headers = {"Cookie": cookie_header, "User-Agent": USER_AGENT}
        directory = os.path.dirname(self.cookie_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.cookie_path, "w", encoding="utf-8") as handle:
            handle.write(cookie_header)
        log(f"    {len(cookies)} Cookie を保存: {self.cookie_path}")

    def _cookies_from_browser(self) -> list[dict[str, Any]]:
        client = Marionette(port=self.port)
        client.start_session()
        try:
            client.navigate(f"{BASE}/animestore/")
            time.sleep(3)
            return client.get_cookies()
        finally:
            client.close()

    # -- search ----------------------------------------------------------
    def search(self, keyword: str) -> list[tuple[str, str]]:
        log(f"[2] 検索: {keyword!r}")
        response = requests.get(
            f"{BASE}/animestore/rest/WS000105",
            params={"searchKey": keyword, "start": "0", "length": "20",
                    "mainKeyVisualSize": "2"},
            headers=self.headers, timeout=30,
        )
        payload = response.json()
        if payload.get("resultCd") != "00":
            die(f"検索に失敗しました: resultCd={payload.get('resultCd')}")
        works = (payload.get("data") or {}).get("workList") or []
        results = [
            (work.get("workId"), (work.get("workInfo") or {}).get("workTitle", ""))
            for work in works
        ]
        for work_id, title in results:
            log(f"    {work_id}\t{title}")
        if not results:
            die(f"検索結果がありません: {keyword!r}")
        return results

    def choose_work(self, keyword: str, work_id: str | None) -> str:
        if work_id:
            log(f"[2] 検索を省略: workId={work_id}")
            return work_id
        results = self.search(keyword)
        for candidate, title in results:
            if title == keyword:
                return str(candidate)
        return str(results[0][0])

    # -- episodes --------------------------------------------------------
    def episodes(self, work_id: str) -> dict[str, str]:
        log(f"[3] 話数一覧: workId={work_id}")
        response = requests.get(
            f"{BASE}/animestore/ci_pc",
            params={"workId": work_id, "partId": f"{work_id}001"},
            headers=self.headers, timeout=30,
        )
        found: dict[str, str] = {}
        for match in re.finditer(
            r"<a[^>]*?(?:cd_pc|ci_pc)\?[^>]*partId=(\d+)[^>]*>(.*?)</a>",
            response.text, re.S,
        ):
            part_id = match.group(1)
            label = re.sub(r"<[^>]+>", " ", match.group(2))
            label = re.sub(r"\s+", " ", label).strip()
            found.setdefault(part_id, label)
        if not found:
            die(f"話数を取得できませんでした: workId={work_id}")
        log(f"    {len(found)} 話")
        return dict(sorted(found.items()))

    # -- play parameters -------------------------------------------------
    def play_params(self, part_id: str) -> dict[str, str]:
        payload: dict[str, Any] = {}
        response = None
        for attempt in range(3):
            response = requests.get(
                f"{BASE}/animestore/rest/WS010105",
                params={"defaultPlay": "", "viewType": "2", "mpVersion": "",
                        "partId": part_id},
                headers=self.headers, timeout=30,
            )
            payload = response.json()
            if payload.get("resultCd") == "00":
                break
            log(f"    WS010105 resultCd={payload.get('resultCd')} "
                f"(再試行 {attempt + 1}/3)")
            time.sleep(3)
        if payload.get("resultCd") != "00":
            die(f"WS010105 が失敗しました: {part_id}")
        data = payload["data"]
        urls = data.get("contentUrls") or {}
        mpd_url = None
        for key_name in ("highest", "high"):
            if urls.get(key_name):
                mpd_url = urls[key_name]
                break
        if not mpd_url:
            die(f"MPD の URL がありません: {list(urls)}")
        if not mpd_url.endswith(".mpd"):
            mpd_url += ".mpd"
        return {
            "one_time_key": data["oneTimeKey"],
            "mpd_url": mpd_url,
            "la_url": data["laUrl"],
            "tokens_url": data["castCustomDataUrl"],
            "title": data.get("title", part_id),
        }

    # -- manifest --------------------------------------------------------
    def parse_mpd(self, mpd_url: str) -> dict[str, Any]:
        response = requests.get(mpd_url, headers=self.headers, timeout=30)
        if response.status_code != 200:
            die(f"MPD の取得に失敗しました: HTTP {response.status_code}")
        root = ET.fromstring(response.content)
        kid = None
        pssh = None
        for element in root.iter():
            if kid is None:
                for attribute, value in element.attrib.items():
                    if attribute.split("}")[-1] == "default_KID":
                        kid = value
                        break
            if pssh is None and element.tag.split("}")[-1] == "pssh":
                pssh = (element.text or "").strip()
        if not kid or not pssh:
            die("MPD に KID / PSSH がありません。")

        video: list[dict] = []
        audio: list[dict] = []
        for representation in root.iter(
                "{urn:mpeg:dash:schema:mpd:2011}Representation"):
            base_url = None
            for child in representation:
                if child.tag.endswith("BaseURL"):
                    base_url = (child.text or "").strip()
            entry = {
                "bandwidth": int(representation.get("bandwidth", "0")),
                "height": (int(representation.get("height"))
                           if representation.get("height") else None),
                "url": base_url,
            }
            mime_type = representation.get("mimeType")
            if mime_type == "video/mp4":
                video.append(entry)
            elif mime_type == "audio/mp4":
                audio.append(entry)
        if not video or not audio:
            die("MPD に映像 / 音声のトラックがありません。")
        return {"kid": kid, "pssh": pssh, "video": video, "audio": audio,
                "mpd_url": mpd_url}

    # -- key -------------------------------------------------------------
    def content_key(self, manifest: dict[str, Any],
                    play: dict[str, str]) -> str:
        token_url = (play["tokens_url"].rstrip("/") + "/?&keyId="
                     + manifest["kid"] + "&oneTimeKey="
                     + play["one_time_key"])
        response = requests.get(token_url, headers=self.headers, timeout=30)
        if response.status_code != 200:
            die(f"トークン取得に失敗しました: HTTP {response.status_code}")
        token_info = response.json().get("tokenInfo")
        if not token_info:
            die("トークン取得の応答に tokenInfo がありません。")

        if self.cdm is None:
            self.cdm = Cdm.from_device(Device.load(self.device_path))
        session_id = self.cdm.open()
        try:
            challenge = self.cdm.get_license_challenge(
                session_id, PSSH(manifest["pssh"]))
            headers = dict(self.headers)
            headers["Content-Type"] = "application/octet-stream"
            headers["AcquireLicenseAssertion"] = token_info
            license_response = requests.post(
                play["la_url"], data=challenge, headers=headers, timeout=30)
            if license_response.status_code != 200:
                die(f"ライセンス取得に失敗しました: "
                    f"HTTP {license_response.status_code}")
            self.cdm.parse_license(session_id, license_response.content)
            keys = self.cdm.get_keys(session_id)
        finally:
            self.cdm.close(session_id)

        target = str(manifest["kid"]).lower()
        dummy = "00000000-0000-0000-0000-000000000000"
        content_keys = [k for k in keys if str(k.kid).lower() != dummy]
        for key in content_keys:
            if str(key.kid).lower() == target:
                return key.key.hex()
        if content_keys:
            return content_keys[0].key.hex()
        die("ライセンスからキーを取得できませんでした。")

    # -- download --------------------------------------------------------
    def download(self, url: str, destination: str) -> None:
        for attempt in range(8):
            position = (os.path.getsize(destination)
                        if os.path.exists(destination) else 0)
            headers = dict(self.headers)
            if position:
                headers["Range"] = f"bytes={position}-"
            try:
                with requests.get(url, headers=headers,
                                  timeout=(10, 120), stream=True) as response:
                    if response.status_code == 416:
                        return
                    if response.status_code not in (200, 206):
                        die(f"ダウンロードに失敗しました: HTTP "
                            f"{response.status_code} {url}")
                    expected = response.headers.get("Content-Length")
                    if response.status_code == 200:
                        position_used = 0
                        mode = "wb"
                    else:
                        position_used = position
                        mode = "ab"
                    written = position_used
                    with open(destination, mode) as handle:
                        for chunk in response.iter_content(1 << 20):
                            handle.write(chunk)
                            written += len(chunk)
                if expected and written != int(expected) + position_used:
                    raise IOError("Content-Length mismatch")
                return
            except Exception as error:  # noqa: BLE001 - 再試行のため広く捕捉
                log(f"    ダウンロード再試行 {attempt}: "
                    f"{type(error).__name__}")
        die(f"ダウンロードを完了できませんでした: {url}")

    # -- decrypt + mux ---------------------------------------------------
    def _has_tenc(self, path: str, probe: int = 4 << 20) -> bool:
        with open(path, "rb") as handle:
            return b"tenc" in handle.read(probe)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(args, capture_output=True)

    def decrypt_mux(self, manifest: dict[str, Any], key: str, video_src: str,
                    audio_src: str, output_path: str,
                    workdir: str) -> None:
        # Bento4 1.6 の mp4decrypt はダッシュ付き UUID を track ID と
        # 解釈し、何も復号せず rc=0 で終わる。32 桁 hex で渡す。
        kid_hex = str(manifest["kid"]).replace("-", "").lower()
        video_dec = os.path.join(workdir, "video_dec.mp4")
        audio_dec = os.path.join(workdir, "audio_dec.mp4")
        for source, destination, label in (
                (video_src, video_dec, "映像"),
                (audio_src, audio_dec, "音声")):
            result = self._run(
                [self.mp4decrypt, "--key", f"{kid_hex}:{key}",
                 source, destination])
            if result.returncode != 0:
                die(f"mp4decrypt ({label}) が失敗しました: "
                    f"{result.stderr.decode('utf-8', 'replace').strip()[:300]}")
            if self._has_tenc(destination):
                die(f"mp4decrypt ({label}) が暗号化情報を残しています。"
                    f"キー指定を確認してください: {kid_hex}:{key}")

        result = self._run([
            self.ffmpeg, "-y",
            "-i", video_dec,
            "-i", audio_dec,
            "-map", "0:0", "-map", "1:0",
            "-c", "copy",
            output_path,
        ])
        if result.returncode != 0:
            die("ffmpeg の多重化が失敗しました: "
                f"{result.stderr.decode('utf-8', 'replace').strip()[-600:]}")

    # -- one episode -----------------------------------------------------
    def episode(self, part_id: str, quality: str, out_dir: str) -> str:
        log(f"== partId={part_id} ({quality})")
        play = self.play_params(part_id)
        log(f"   {play['title']}")

        filename = re.sub(r'[\\/:*?"<>|]', "_", play["title"]).strip()
        output_path = os.path.join(out_dir, f"{filename}.mp4")
        if (not self.force and os.path.exists(output_path)
                and os.path.getsize(output_path) > MIN_OUTPUT_BYTES):
            log(f"   スキップ (既存): {output_path}")
            return output_path

        manifest = self.parse_mpd(play["mpd_url"])
        log(f"   KID: {manifest['kid']}")
        key = self.content_key(manifest, play)

        video = pick_representation(manifest["video"],
                                    QUALITY_HEIGHT.get(quality, 720))
        audio = max(manifest["audio"], key=lambda r: r["bandwidth"])
        if not video.get("url") or not audio.get("url"):
            die("MPD の BaseURL がありません。")
        base = play["mpd_url"].rsplit("/", 1)[0]
        video_url = f"{base}/{video['url']}"
        audio_url = f"{base}/{audio['url']}"
        log(f"   映像: {video['url']} ({video['height']}p / "
            f"{video['bandwidth']})")
        log(f"   音声: {audio['url']} ({audio['bandwidth']})")

        workdir = os.path.join(out_dir, f"work_{part_id}")
        os.makedirs(workdir, exist_ok=True)
        video_src = os.path.join(workdir, video["url"])
        audio_src = os.path.join(workdir, audio["url"])
        log("   映像をダウンロード中 ...")
        self.download(video_url, video_src)
        log("   音声をダウンロード中 ...")
        self.download(audio_url, audio_src)

        self.decrypt_mux(manifest, key, video_src, audio_src,
                         output_path, workdir)
        log(f"   完了: {output_path} "
            f"({os.path.getsize(output_path)} bytes)")

        for path in (video_src, audio_src,
                     os.path.join(workdir, "video_dec.mp4"),
                     os.path.join(workdir, "audio_dec.mp4")):
            if os.path.exists(path):
                os.remove(path)
        try:
            os.rmdir(workdir)
        except OSError:
            pass
        return output_path


# ---------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="d-download-pipeline",
        description="指定した作品のエピソードをまとめて保存します。",
    )
    parser.add_argument("title", nargs="?", default=None,
                        help="検索キーワード (作品名)")
    parser.add_argument("--work-id", help="検索を省略して workId を指定")
    parser.add_argument("--ep", help="話数または範囲 (例: 1 / 1-3 / 1,3,5)")
    parser.add_argument("--all", action="store_true", help="全話")
    parser.add_argument("--quality", default="720p",
                        choices=list(QUALITY_HEIGHT), help="解像度")
    parser.add_argument("--out", default=os.path.join(os.getcwd(), "downloads"),
                        help="出力ディレクトリ (既定: ./downloads)")
    parser.add_argument("--force", action="store_true",
                        help="既存ファイルを無視して再取得")
    parser.add_argument("--device", required=True,
                        help="Widevine デバイスファイル (.wvd)")
    parser.add_argument("--mp4decrypt", default=None,
                        help="mp4decrypt のパス (既定: PATH から解決)")
    parser.add_argument("--ffmpeg", default=None,
                        help="ffmpeg のパス (既定: PATH から解決)")
    parser.add_argument("--cookies", default=default_cookie_path(),
                        help="Cookie キャッシュの保存先")
    parser.add_argument("--refresh-cookies", action="store_true",
                        help="キャッシュを使わず Cookie を再取得")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Marionette のポート (既定: 2828)")
    return parser


def configure_output_encoding() -> None:
    """コンソールの既定コードページ (cp1252 など) でも日本語を出力できるようにする。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = build_parser().parse_args(argv)
    if not args.device:
        die("--device を指定してください。")
    if not args.device.endswith(".wvd") or not os.path.exists(args.device):
        die(f"デバイスファイルが見つかりません: {args.device}")
    if not args.work_id and not args.title:
        die("作品名か --work-id を指定してください。")
    if not args.all and not args.ep:
        die("--ep か --all を指定してください。")

    pipeline = Pipeline(
        device_path=args.device,
        mp4decrypt=resolve_tool(args.mp4decrypt, "mp4decrypt", "--mp4decrypt"),
        ffmpeg=resolve_tool(args.ffmpeg, "ffmpeg", "--ffmpeg"),
        cookie_path=args.cookies,
        refresh_cookies=args.refresh_cookies,
        port=args.port,
        force=args.force,
    )
    pipeline.load_cookies()

    work_id = pipeline.choose_work(args.title, args.work_id)
    log(f"   workId={work_id}")
    episodes = pipeline.episodes(work_id)
    by_number: dict[int, str] = {}
    for part_id in episodes:
        try:
            by_number[int(part_id[len(work_id):])] = part_id
        except ValueError:
            continue
    if not by_number:
        die("話番号を解釈できませんでした。")

    if args.all:
        wanted = sorted(by_number)
    else:
        wanted = parse_episode_selection(args.ep, by_number)
    if not wanted:
        die("対象の話数がありません。")

    os.makedirs(args.out, exist_ok=True)
    ok = failed = 0
    for number in wanted:
        try:
            pipeline.episode(by_number[number], args.quality, args.out)
            ok += 1
        except SystemExit:
            failed += 1
            log(f"   !! 第{number}話で失敗しました。続行します。")
        except Exception as error:  # noqa: BLE001 - 1 話の失敗で全体を止めない
            failed += 1
            log(f"   !! 第{number}話でエラー: "
                f"{type(error).__name__}: {error}")
    log(f"== 結果: 成功 {ok} / 失敗 {failed} (対象 {len(wanted)} 話)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
