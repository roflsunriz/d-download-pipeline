"""デバイスファイル (.wvd) の解決と NTFS MFT 検索。"""

from __future__ import annotations

import json
import os
import string
import subprocess
import sys
from typing import Any

from common import die, log

if sys.platform == "win32":
    import ctypes
    import struct
    from ctypes import wintypes

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FSCTL_ENUM_USN_DATA = 0x000900B3
FSCTL_QUERY_USN_JOURNAL = 0x000900F4
FILE_ATTRIBUTE_DIRECTORY = 0x10
TOKEN_QUERY = 0x0008
TOKEN_ELEVATION = 20
DRIVE_FIXED = 3
SEE_MASK_NOCLOSEPROCESS = 0x00000040


# --------------------------------------------------------------------- config

def cache_dir() -> str:
    base = os.environ.get("D_DOWNLOAD_CACHE_DIR")
    if base:
        return base
    return os.path.join(os.path.expanduser("~"), ".cache",
                        "d-download-pipeline")


def default_cookie_path() -> str:
    return os.path.join(cache_dir(), "cookies.txt")


def config_path() -> str:
    return os.path.join(cache_dir(), "config.json")


def load_config() -> dict[str, Any]:
    try:
        with open(config_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=1)


# ------------------------------------------------------------- device finding

def _pick_wvd(candidates: list[str]) -> str | None:
    unique = sorted({os.path.abspath(path) for path in candidates},
                    key=lambda path: (len(path), path.lower()))
    if not unique:
        return None
    if len(unique) > 1:
        log(f"   見つかったデバイスファイル: {len(unique)} 件")
        for path in unique:
            log(f"     {path}")
    return unique[0]


def find_script_wvd() -> str | None:
    folder = os.path.dirname(os.path.abspath(__file__))
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    return _pick_wvd([os.path.join(folder, name) for name in names
                      if name.lower().endswith(".wvd")])


def _is_elevated() -> bool:
    if os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD)]
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                                     TOKEN_QUERY, ctypes.byref(token)):
        return False
    try:
        elevation = wintypes.DWORD()
        size = wintypes.DWORD()
        if not advapi32.GetTokenInformation(
                token, TOKEN_ELEVATION, ctypes.byref(elevation),
                ctypes.sizeof(elevation), ctypes.byref(size)):
            return False
        return bool(elevation.value)
    finally:
        kernel32.CloseHandle(token)


def _drive_type(root: str) -> int:
    return ctypes.WinDLL("kernel32").GetDriveTypeW(root)


def _fs_type(root: str) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    name = ctypes.create_unicode_buffer(64)
    kernel32.GetVolumeInformationW(root, None, 0, None, None, None,
                                    name, 64)
    return name.value


def _scan_volume(letter: str, suffix: str) -> list[str]:
    """NTFS ボリュームの MFT を列挙し、suffix で終わるパスを返す。"""
    invalid = ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID]
    kernel32.DeviceIoControl.restype = wintypes.BOOL

    handle = kernel32.CreateFileW(
        f"\\\\.\\{letter}:", GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if handle in (None, invalid):
        raise PermissionError(ctypes.get_last_error())

    try:
        journal = ctypes.create_string_buffer(128)
        returned = wintypes.DWORD()
        if not kernel32.DeviceIoControl(
                handle, FSCTL_QUERY_USN_JOURNAL, None, 0, journal,
                len(journal), ctypes.byref(returned), None):
            raise OSError(ctypes.get_last_error())
        next_usn = struct.unpack_from("<Q", journal.raw, 16)[0]

        buffer_size = 8 << 20
        buffer = ctypes.create_string_buffer(buffer_size)
        suffix_bytes = suffix.encode("utf-16-le")
        start = 0
        directories: dict[int, tuple[int, bytes]] = {}
        matches: list[tuple[int, bytes]] = []
        while True:
            query = struct.pack("<QQQ", start, 0, next_usn)
            returned.value = 0
            ok = kernel32.DeviceIoControl(
                handle, FSCTL_ENUM_USN_DATA, query, len(query), buffer,
                buffer_size, ctypes.byref(returned), None)
            if not ok or returned.value <= 8:
                break
            raw = buffer.raw[:returned.value]
            start = struct.unpack_from("<Q", raw, 0)[0]
            position = 8
            while position + 60 <= len(raw):
                length = struct.unpack_from("<I", raw, position)[0]
                if length < 60 or position + length > len(raw):
                    break
                frn, parent = struct.unpack_from("<QQ", raw, position + 8)
                attributes = struct.unpack_from("<I", raw, position + 52)[0]
                name_length, name_offset = struct.unpack_from(
                    "<HH", raw, position + 56)
                name = raw[position + name_offset:
                           position + name_offset + name_length]
                if attributes & FILE_ATTRIBUTE_DIRECTORY:
                    directories[frn] = (parent, name)
                elif name.endswith(suffix_bytes):
                    matches.append((parent, name))
                position += length

        paths = []
        for parent, name in matches:
            parts = []
            current = parent
            for _ in range(64):
                entry = directories.get(current)
                if not entry:
                    break
                current, directory_name = entry
                parts.append(directory_name.decode("utf-16-le", "replace"))
            parts.reverse()
            file_name = name.decode("utf-16-le", "replace")
            paths.append(f"{letter}:\\" + "\\".join(parts + [file_name]))
        return paths
    finally:
        kernel32.CloseHandle(handle)


def _elevated_mft_scan(suffix: str,
                       timeout: float = 300.0) -> list[str] | None:
    """自分自身を管理者権限で起動し、MFT 走査の結果を受け取る。"""
    if os.name != "nt":
        return None
    log("   管理者権限で MFT を走査します ...")
    output = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                          f"ddpipe-mft-{os.getpid()}.json")
    try:
        os.remove(output)
    except OSError:
        pass

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", ctypes.c_ulong),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD

    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(ShellExecuteInfo)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = sys.executable
    info.lpParameters = (f'"{os.path.abspath(__file__)}" --scan '
                          f'--output "{output}" --suffix "{suffix}"')
    info.lpDirectory = os.path.dirname(os.path.abspath(__file__))
    info.nShow = 0
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        return None
    try:
        kernel32.WaitForSingleObject(info.hProcess, int(timeout * 1000))
    finally:
        kernel32.CloseHandle(info.hProcess)
    try:
        with open(output, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    finally:
        try:
            os.remove(output)
        except OSError:
            pass
    paths = payload.get("paths") if isinstance(payload, dict) else None
    return paths if isinstance(paths, list) else None


def mft_search(suffix: str = ".wvd") -> list[str] | None:
    """NTFS の MFT を列挙して suffix 一致のファイルを返す。

    管理者権限が必要。昇格できない場合は None を返す。
    """
    if os.name != "nt":
        return None
    if not _is_elevated():
        return _elevated_mft_scan(suffix)
    paths: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if not os.path.exists(root):
            continue
        if _drive_type(root) != DRIVE_FIXED:
            continue
        if _fs_type(root).upper() != "NTFS":
            continue
        try:
            paths.extend(_scan_volume(letter, suffix))
        except OSError:
            continue
    return paths


def find_system_wvd() -> str | None:
    """PC 全体から .wvd を探す。NTFS の MFT 走査を優先する。"""
    log("   デバイスファイルを PC 全体から検索中 (MFT) ...")
    found = mft_search(".wvd")
    if found is not None:
        log(f"   MFT から {len(found)} 件検出")
        picked = _pick_wvd([path for path in found
                            if path.lower().endswith(".wvd")
                            and os.path.exists(path)])
        if picked:
            return picked

    log("   ドライブを走査します ...")
    candidates: list[str] = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if not os.path.exists(root):
            continue
        try:
            result = subprocess.run(["where", "/R", root, "*.wvd"],
                                    capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError):
            continue
        for line in result.stdout.decode("mbcs", "replace").splitlines():
            line = line.strip()
            if line.lower().endswith(".wvd") and os.path.exists(line):
                candidates.append(line)
    return _pick_wvd(candidates)


def resolve_device(explicit: str | None) -> tuple[str, bool]:
    """利用する .wvd を決める。(パス, 記憶が必要か) を返す。"""
    config = load_config()
    remembered = config.get("device")

    if explicit:
        path = os.path.abspath(os.path.expanduser(explicit))
        if not path.lower().endswith(".wvd") or not os.path.exists(path):
            die(f"デバイスファイルが見つかりません: {explicit}")
        return path, remembered != path

    if (isinstance(remembered, str) and remembered.lower().endswith(".wvd")
            and os.path.exists(remembered)):
        log(f"[0] 記憶したデバイスファイルを使用: {remembered}")
        return remembered, False

    found = find_script_wvd()
    if found:
        log(f"[0] スクリプトと同じフォルダのデバイスファイルを使用: {found}")
        return found, True

    found = find_system_wvd()
    if found:
        log(f"[0] PC 全体から検出したデバイスファイルを使用: {found}")
        return found, True

    die("デバイスファイル (.wvd) が見つかりません。"
        "--device で指定してください。")


def _main() -> int:
    """昇格した MFT 走査の入口。"""
    import argparse

    parser = argparse.ArgumentParser(prog="device", add_help=False)
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--suffix", default=".wvd")
    args = parser.parse_args()
    paths = mft_search(args.suffix) or []
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"paths": paths}, handle, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
