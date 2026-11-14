# d-download-pipeline

## 要件

| 種別 | 内容 |
|---|---|
| OS | Windows 10 / 11(PowerShell 7 で確認) |
| Python | 3.12 以上(3.14.10 で確認) |
| ブラウザ | Firefox(Cookie の初回取得時のみ) |
| 外部ツール | `mp4decrypt`(Bento4 1.6)、`ffmpeg` |
| デバイスファイル | Widevine の `.wvd` |

## セットアップ

```powershell
git clone https://github.com/roflsunriz/d-download-pipeline.git
cd d-download-pipeline
python -m pip install -r requirements.txt
```

`mp4decrypt` と `ffmpeg` は PATH に通すか、実行時に `--mp4decrypt` / `--ffmpeg` で指定します。

## 事前準備

### 1. Widevine デバイスファイル

`.wvd` のパスを `--device` に渡します。

### 2. Firefox の起動

初回は Cookie を取得するため、Marionette を有効にして Firefox を起動します。

```powershell
Get-Process firefox -ErrorAction SilentlyContinue | Stop-Process
$env:MOZ_REMOTE_DEBUGGING_PORT = "2828"
& "C:\Program Files\Mozilla Firefox\firefox.exe"
```

Cookie は既定で `%USERPROFILE%\.cache\d-download-pipeline\cookies.txt` に保存され、2 回目以降は再利用されます。取得し直すときは `--refresh-cookies` を指定します。

## 使い方

```powershell
# 1 話
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1

# 範囲指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1-3

# 個別指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1,3,5

# 全話
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --all

# workId を直接指定(検索を省略)
python d_download_pipeline.py --work-id 26610 --device C:\path\to\device.wvd --ep 1

# 1080p 指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1 --quality 1080p
```

検索結果が複数ある場合は、作品名が完全一致したものを優先し、一致がなければ先頭を使います。

## オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `title` | — | 検索キーワード(作品名) |
| `--work-id` | — | workId を直接指定し、検索を省略する |
| `--ep` | — | 話数(`1`、`1-3`、`1,3,5`) |
| `--all` | 無効 | 全話を対象にする |
| `--quality` | `720p` | `1080p` / `720p` / `480p` / `360p`。該当がなければ最も近い解像度を使う |
| `--out` | `./downloads` | 出力先ディレクトリ |
| `--force` | 無効 | 既存の出力を無視して取得し直す |
| `--device` | — | Widevine デバイスファイル(必須) |
| `--mp4decrypt` | PATH から解決 | `mp4decrypt` のパス |
| `--ffmpeg` | PATH から解決 | `ffmpeg` のパス |
| `--cookies` | `%USERPROFILE%\.cache\d-download-pipeline\cookies.txt` | Cookie の保存先 |
| `--refresh-cookies` | 無効 | キャッシュを使わず Cookie を取得し直す |
| `--port` | `2828` | Marionette のポート |
| `-h` / `--help` | — | ヘルプを表示する |

`--ep` と `--all` の両方を指定した場合は `--all` が優先されます。

## 出力

```
<--out>/<作品名> <第N話> <サブタイトル>.mp4
```

ファイル名に使えない文字(`\ / : * ? " < > |`)は `_` に置き換えます。

## 再実行

同じ出力先で再実行すると、1 MB を超える既存ファイルはスキップされます。途中で失敗した話だけを取得し直せます。

```powershell
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1-12
```

## 環境変数

| 変数 | 説明 |
|---|---|
| `D_DOWNLOAD_CACHE_DIR` | Cookie キャッシュのディレクトリを上書きする |

## 終了コード

| 値 | 意味 |
|---|---|
| `0` | 対象の全話が成功した |
| `1` | 1 話以上の失敗 |
| `2` | 引数の誤り |

失敗した話があっても残りは続行し、最後に成功数と失敗数を表示します。

## ライセンス

MIT
