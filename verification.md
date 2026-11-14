# 検証手順

## 1. 静的確認

```powershell
python -m compileall -q d_download_pipeline.py
python d_download_pipeline.py --help
```

`--help` が終了コード 0 で、オプション一覧を表示することを確認する。

## 2. 引数エラー

```powershell
python d_download_pipeline.py "作品名" --ep 1
```

`--device` を省くと、メッセージを出して終了コード 2 になることを確認する。存在しないデバイスパスでは終了コード 1 になる。

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

## 4. スキップと再開

同じ引数でもう一度実行し、`スキップ (既存)` が出て再取得しないことを確認する。`--force` を付けると再取得する。

## 5. 複数話

```powershell
python d_download_pipeline.py "作品名" --device C:\path\to\device.wvd --ep 1-3
```

`結果: 成功 3 / 失敗 0` を確認する。話ごとに KID が変わるため、3 話すべてで復号されていることを 3 の手順で確認する。

## 6. 異常系

| 条件 | 期待 |
|---|---|
| 存在しないキーワード | `検索結果がありません` で終了コード 1 |
| 存在しない話数 | `注意: 存在しない話数を除外します` を出して残りを処理 |
| 不正な `--ep` 書式 | `--ep の書式が不正です` で終了コード 1 |
| `--mp4decrypt` / `--ffmpeg` が無い | 解決できない旨のメッセージで終了コード 1 |
