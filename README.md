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

`.wvd` は次の順で選ばれます。一度使ったパスは `%USERPROFILE%\.cache\d-download-pipeline\config.json` に記憶され、以降は `--device` を省略できます。

1. `--device` の指定
2. 記憶したパス
3. スクリプトと同じフォルダの `.wvd`
4. NTFS の MFT を列挙して PC 全体を検索(初回のみ)

4 は MFT を読むため、初回だけ管理者権限の確認が表示されます。処理は数秒から十数秒です。記憶したパスが見つからない場合も、同じ手順で再検索して記憶を更新します。

`--device` を指定し直すと記憶が更新されます。

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

# 最高画質 (--quality 省略時)
python d_download_pipeline.py "作品名" --ep 1

# 範囲指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1-3

# 個別指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1,3,5

# 全話
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --all

# workId を直接指定(検索を省略)
python d_download_pipeline.py --work-id 26610 --device C:\path\to\device.wvd --ep 1

# カタログから選ぶ (対話)
python d_download_pipeline.py --catalog --device C:\path\to\device.wvd

# 1080p 指定
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1 --quality 1080p
```

検索結果が複数ある場合は、作品名が完全一致したものを優先し、一致がなければ先頭を使います。

`--device` は最初の 1 回だけ指定すれば、以降は省略できます。

```powershell
python d_download_pipeline.py "作品名" --ep 1
```

## カタログ

`--catalog` を付けると、次の入口から作品を選べます。

| 番号 | 入口 |
|---|---|
| 1 | 新着 |
| 2 | ジャンル (15 分類) |
| 3 | 五十音 (行 10 × 列 5) |
| 4 | ランキング (4 種) |
| 5 | 特集 (6 テーマ) |
| 6 | キーワード検索 |
| 7 | workId を直接入力 |
| q | 終了 |

一覧は 20 件ずつ表示します。`n` で次のページ、`p` で前のページ、`g` でページ指定、`b` で戻る、`q` で終了します。番号を入力すると作品が決まり、話数の選択に進みます。

話数は `1-3`、`1,3,5`、`all`、空欄 (全話) で指定します。`--ep` または `--all` を付けた場合は、話数の入力を省略します。

```powershell
python d_download_pipeline.py --catalog --device C:\path\to\device.wvd --ep 1-3 --quality 1080p
```

ダウンロード後に「続けて別の作品を選びますか?」と表示されます。`y` で入口へ戻り、それ以外で終了します。

## オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `title` | — | 検索キーワード(作品名) |
| `--catalog` | 無効 | カタログから作品と話数を対話で選ぶ |
| `--work-id` | — | workId を直接指定し、検索を省略する |
| `--ep` | — | 話数(`1`、`1-3`、`1,3,5`) |
| `--all` | 無効 | 全話を対象にする |
| `--quality` | 最高画質 | `1080p` / `720p` / `480p` / `360p`。指定がなければ最も高い解像度と最も高い音声ビットレートを使う。指定した解像度がなければ最も近いものを使う |
| `--out` | `./downloads` | 出力先ディレクトリ |
| `--force` | 無効 | 既存の出力を無視して取得し直す |
| `--device` | 自動検出 | Widevine デバイスファイル。省略時は「記憶 → スクリプト隣 → MFT 検索」の順に探す |
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
| `D_DOWNLOAD_CACHE_DIR` | Cookie と設定 (`config.json`) のディレクトリを上書きする |

## 終了コード

| 値 | 意味 |
|---|---|
| `0` | 対象の全話が成功した |
| `1` | 1 話以上の失敗 |
| `2` | 引数の誤り |

失敗した話があっても残りは続行し、最後に成功数と失敗数を表示します。

## ライセンス

MIT
