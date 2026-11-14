# 更新手順

## 前提

- Windows 10 / 11、PowerShell 7
- Python 3.12 以上
- `git`、`mp4decrypt`(Bento4)、`ffmpeg` が利用できる

## 1. 取得と依存の更新

```powershell
git pull origin main
python -m pip install --upgrade -r requirements.txt
python -m pip check
```

`construct` は 2.8.8 に固定している。2.9 以降へ上げると `pymp4` と `pywidevine` が壊れる(`findings.md` を参照)。更新する場合は、`pywidevine` と `pymp4` の対応版を確認してから 3 つを同時に上げる。

```powershell
python -m pip install --upgrade --no-build-isolation construct==2.8.8
```

Python 3.14 でソースから入れる場合、`--no-build-isolation` が必要になることがある。

## 2. 外部ツール

| ツール | 確認コマンド | 更新時の注意 |
|---|---|---|
| `mp4decrypt` | `mp4decrypt` (引数なしで usage 表示) | Bento4 1.6 系で動作確認。KID の扱いは `findings.md` を参照 |
| `ffmpeg` | `ffmpeg -version` | 主要な配布版で動作確認済み |

## 3. Firefox / Cookie

- 初回は `MOZ_REMOTE_DEBUGGING_PORT` を設定して Firefox を起動する。
- ログイン状態が切れたら、Firefox でログインし直してから `--refresh-cookies` を付けて実行する。
- 既定の Cookie キャッシュは `%USERPROFILE%\.cache\d-download-pipeline\cookies.txt`。`D_DOWNLOAD_CACHE_DIR` で変更できる。

## 4. 検証

```powershell
python -m compileall -q d_download_pipeline.py
python d_download_pipeline.py --help
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1
```

詳細は `verification.md` に従う。

## 5. 失敗時の復旧

- 出力ファイルが暗号化されたまま、または再生できない: 同じ引数で `--force` を付けて再生成する。
- ダウンロードが途中で止まる: `work_<partId>/` に途中ファイルが残る。同じ引数で再実行すると Range で再開する。
- `resultCd: 86`: Cookie が不足している。`--refresh-cookies` で取り直す。
- `mp4decrypt` が rc=0 なのに復号されない: KID がダッシュ付きになっていないか確認する(`findings.md`)。
