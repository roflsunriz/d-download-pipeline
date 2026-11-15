# 検証手順

## 1. 静的確認

```powershell
python -m compileall -q d_download_pipeline.py
python d_download_pipeline.py --help
```

`--help` が終了コード 0 で、オプション一覧を表示することを確認する。

## 2. 引数エラー

```powershell
python d_download_pipeline.py "作品名"
```

`--ep` と `--all` を省くと、メッセージを出して終了コード 1 になることを確認する。存在しない `--device` パスを指定した場合も終了コード 1 になる。

## 3. 実機能(1 話)

```powershell
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1 --quality 720p
```

確認項目:

1. `完了:` の行に出力パスとサイズが出る。
2. 出力ファイルの長さが `WS010105` の `partMeasureSecond` と一致する。

```powershell
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height -of default=nw=1 "<出力>.mp4"
```

3. 120 秒分をデコードしてエラーがない。

```powershell
ffmpeg -v error -i "<出力>.mp4" -t 120 -f null - 2>&1 | Measure-Object -Line
```

行数が 0 であること。行数が多い場合は復号されていない(`findings.md` の「復号」を参照)。

`--quality` を省略した場合、`映像:` の行が最も高い解像度(例: 1080p)になり、`音声:` が最も高いビットレートになることを確認する。

## 4. スキップと再開

同じ引数でもう一度実行し、`スキップ (既存)` が出て再取得しないことを確認する。`--force` を付けると再取得する。

## 5. 複数話

```powershell
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1-3
```

`結果: 成功 3 / 失敗 0` を確認する。話ごとに KID が変わるため、3 話すべてで復号されていることを 3 の手順で確認する。

## 7. カタログ

```powershell
python d_download_pipeline.py --catalog --device C:\path\to\device.wvd --ep 1
```

確認項目:

1. 入口 1〜7 が表示され、`q` で終了する。
2. 1 (新着) / 2 (ジャンル) / 3 (五十音) / 4 (ランキング) / 5 (特集) / 6 (検索) / 7 (workId) で一覧が出る。
3. 一覧で `n` / `p` / `g` によりページを移動でき、`b` で入口へ戻る。
4. 番号で作品を選ぶと話数一覧が出て、`--ep` 指定時は入力を省略する。
5. 話数を選ぶとダウンロードが始まり、完了後に「続けて別の作品を選びますか?」が出る。

ページ数の表示と件数が、同じ入口の Web 表示と大きく食い違わないことを確認する。

## 8. デバイスファイルの自動検出

`--device` を省いたときの解決順を確認する。

1. `%USERPROFILE%\.cache\d-download-pipeline\config.json` を削除し、`.wvd` をスクリプトと同じフォルダに置いて実行すると、`スクリプトと同じフォルダのデバイスファイルを使用` と表示され、`config.json` に `device` が記録される。
2. 2 回目の実行では `記憶したデバイスファイルを使用` と表示される。
3. `config.json` を消し、`.wvd` もスクリプトと同じフォルダに無い状態で実行すると、`PC 全体から検索中 (MFT)` と `管理者権限で MFT を走査します` が表示され、見つかったパスが使われる。所要時間は 10〜20 秒程度。
4. `config.json` の `device` を存在しないパスに書き換えて実行すると、同じ MFT 検索が走り、`config.json` が実際のパスで上書きされる。
5. `.wvd` が見つからない環境では、`--device` を促すメッセージで終了コード 1 になる。
6. `--device` を別の `.wvd` で指定すると、`config.json` の `device` が更新される。

## 9. YouTube

```powershell
python d_download_pipeline.py --youtube "https://www.youtube.com/watch?v=..." --quality 360p
```

確認項目:

1. `[YouTube]` の行にタイトル、長さ、ライセンスが出る。
2. 保存後に `再生確認: ... (デコードエラー 0 行)` が出る。`0` 以外なら再生できない可能性があるため `--force` で取り直す。
3. 保存された MP4 が H.264 + AAC である(`ffprobe` で確認)。
4. 同じ引数で再実行すると `has already been downloaded` と表示され、終了コード 0 になる。
5. `--force` を付けると取り直す。
6. `--quality` を変えると別名のファイルができる(例: `... [ID] 360p.mp4` と `... [ID] 720p.mp4`)。

### DRM 付きの映画

無料公開でも Widevine で保護された映画で確認する。

1. Firefox を起動していない状態でも、`Firefox を headless で起動しています` と表示されて処理が進む。
2. `メタデータを取得できませんでした` にならず、`DRM 動画です` と選択可能な高さが出る。
3. `キー: N 件` が出て、映像と音声がそれぞれ復号される。
4. `再生確認: ... (デコードエラー 0 行)` になる。
5. `ffprobe` で指定した高さ以下になっている。
6. 途中の位置(`-ss 3000` など)でもデコードエラーが 0 行である。
7. 処理後に自動起動した headless の Firefox が残っていない。

DRM 保護されていない動画で実行すると、`DRM 保護されていない動画です` と表示されて終了コード 1 になる。

### 暗号化済みファイルの復号

`yt-dlp --allow-unplayable-formats` で取得した暗号化ファイルで確認する。

```powershell
python d_download_pipeline.py --youtube "https://www.youtube.com/watch?v=..." --decrypt video.mp4 audio.m4a --out C:\path\to\out
```

1. `キー: N 件` が出て、映像と音声が復号される。
2. `再生確認: ... (デコードエラー 0 行)` になる。
3. 出力が `<タイトル> [<ID>].mp4` になる。
4. 同じ引数で再実行するとスキップされる。`--force` で取り直す。
5. `--youtube` を省くと `--decrypt には --youtube <URL> が必要です` で終了コード 1 になる。

## 10. 異常系

| 条件 | 期待 |
|---|---|
| 存在しないキーワード | `検索結果がありません` で終了コード 1 |
| 存在しない話数 | `注意: 存在しない話数を除外します` を出して残りを処理 |
| 不正な `--ep` 書式 | `--ep の書式が不正です` で終了コード 1 |
| `--mp4decrypt` / `--ffmpeg` が無い | 解決できない旨のメッセージで終了コード 1 |
