# 判明事項

## 構成

- `d_download_pipeline.py`: CLI とパイプライン本体。
- `device.py`: `.wvd` の解決、NTFS MFT 検索、`config.json` の読み書き。昇格した走査の入口もここ。
- `common.py`: ログ、終了、対話入力。

## 認証 (Cookie)

- 認証に必要な Cookie は HttpOnly を含む全件で、`JSESSIONID` が欠けると再生情報 API が `resultCd: 86` を返す。
- `document.cookie` では HttpOnly を取得できない。Marionette の `WebDriver:GetCookies`(`get_cookies()`)で取得できる。`navigator.cookieStore` は本環境の Firefox では未定義だった。
- 取得した Cookie ヘッダは MPD・トークン・ライセンスの取得にもそのまま使える。
- 根拠: `danime_license_test3.py`、`danime_ws010105_plaintest.py`(d-anime 側の試作)。確認日 2026-11-15。

## ライセンス取得

- 2 段階。`GET <castCustomDataUrl>?&keyId=<KID>&oneTimeKey=<key>` で `tokenInfo` を得て、`POST <laUrl>` のヘッダ `AcquireLicenseAssertion: <tokenInfo>` に載せる。
- アサーションに `oneTimeKey` を直接入れると `400 0003|no assertion in payload.` になる。
- `oneTimeKey` は `WS010105` のたびに発行され、1 回限り。取得後すぐライセンスを要求する。
- `parse_license()` は戻り値が `None`。鍵は `get_keys(session_id)` から読む。
- KID は話ごとに異なる。KID と PSSH は MPD の `ContentProtection` から取る。
- MPD の映像は 240p〜1080p(9 段階)、音声は 128k/192k の 2 段階だった(2026-11-15 時点)。`--quality` 省略時は映像の `height` 最大、同率なら `bandwidth` 最大を選ぶ。音声は常に `bandwidth` 最大を選ぶ。

## 再生情報 API

- `WS010105` の `resultCd: 22` は一時的なレート制限で、数秒待つと `00` に戻る。3 回まで再試行する。
- `contentUrls` は新しい作品が `highest`/`high`/`low`/`lowest`、古い作品が `high`/`middle`/`low`/`lowest`。`highest` がなければ `high` を使う。
- 検索は `WS000105`(`searchKey`)。`WS000119` は検索キーを受け付けない(`resultCd: 21`)。

## 復号

- Bento4 1.6 の `mp4decrypt` は `--key <KID>:<KEY>` の KID にダッシュ付き UUID を渡すと、track ID と誤解釈して **何も復号せず rc=0** で終わる。先頭が数字の KID では無言で失敗するため気付きにくい。
- 32 桁 hex(ダッシュなし)を渡す。復号後は暗号化情報の `tenc` ボックスが消えるので、これで無言失敗を検出できる。
- `ffmpeg -c copy` は暗号化入力を多重化すると `tenc` を落とす。復号前に mux すると、後から復号できず再生もできないファイルになる。
- 確認方法: `ffmpeg -v error -i <file> -t 120 -f null -` の出力行数が 0 なら復号済み。暗号化されたままなら数千行のデコードエラーになる。

## 依存関係

- `construct` は 2.8.8 に固定する。`pymp4` 1.4.0 が `construct==2.8.8` を厳密に要求し、2.9 以降では `pymp4` が `String` 不在で失敗し、`pywidevine` も `Const` の引数順が変わる。
- Python 3.14 で `construct 2.8.8` をソースから入れる場合は `--no-build-isolation` が必要だった。
- `pywidevine` 1.9 の `Cdm` に `close_all()` はない。`close(session_id)` を使う。

## カタログ

- 全作品の一覧は `WS000108`。`initialCollectionKey`(行 1〜10 = あ/か/さ/た/な/は/ま/や/ら/わ・英数)と `consonantKey`(列 1〜5 = あ/い/う/え/お)、`workTypeList=anime` が必須。どちらかを欠くと `resultCd: 21`。
- ジャンルのコードと名前は `/animestore/CF/search_index` のリンクから取れる。WS000107 は `genreCd` ごとに存在し、1・2 など未使用のコードは `resultCd: 21`。
- 特集は `WS000104?themeId=CO...`。応答の `title` が特集名になる。`CO00000002` は「新着」で 800 件以上ある。
- ランキングは `WS000103?rankingType=..`。`01` デイリー、`02` ウィークリー、`08` デイリー(コンプリート)、`04` ウィークリー(コンプリート)。一覧の `maxCount` は作品数ではなくランキングの母数になる。
- 話数一覧のラベルには `&times;` などの HTML 実体参照が含まれる。`html.unescape` で戻す。

## YouTube

- 無料公開の判定は `yt-dlp --dump-single-json` の `availability` を使う。`public` / `unlisted` を許可し、`premium` / `subscriber_only` / `needs_auth` / `private` は中止する。`is_live` が真なら対象外。
- `-S "vcodec:h264,acodec:aac"` を付けると、360p では `avc1` + `mp4a`(format 18)が選ばれた。付けない場合は AV1 + AAC が選ばれることがある。
- 出力名に解像度を入れておかないと、別の `--quality` で再実行したときに別ファイルにならず、既存ファイルをスキップしてしまう。
- `yt-dlp` は YouTube 側の変更に追随する必要があり、version を固定しない。
- 通常の無料公開動画は DRM で暗号化されていない。yt-dlp が署名・cipher を処理し、ffmpeg で結合した時点で平文の H.264/AAC になる。
- 無料公開でも **YouTube Movies の映画は Widevine 保護** されている。通常の `--dump-single-json` では storyboard しか返らないので、`--allow-unplayable-formats --extractor-args "youtube:formats=dashy"` で DRM 形式を取得する。DRM 形式は `has_drm: true` を持つ。
- DRM のライセンス URL は `https://www.youtube.com/youtubei/v1/player/get_drm_license`。要求は JSON で、`context` / `drmSystem`(DRM_SYSTEM_WIDEVINE)/ `videoId` / `cpn` / `sessionId` / `licenseRequest`(base64 チャレンジ)/ `drmParams` を含む。応答の `license` は URL-safe base64。
- ライセンス要求には `Authorization`(SAPISIDHASH)などのヘッダが必要。ブラウザでの再生から採取したひな形を使い、`licenseRequest` だけ自前 CDM のチャレンジに差し替えると 200 が返り、キーが得られる(実測)。
- ブラウザが受け取ったライセンスの鍵はセッション鍵で暗号化されており、そのままでは使えない。自前 CDM で `parse_license` した `get_keys()` の 16 バイト鍵を使う。
- 映像は `cenc`、音声は `cbcs` だった(2026-11-15 時点)。Bento4 1.6 の `mp4decrypt` は cbcs の音声を正しく復号できなかったが、`ffmpeg -decryption_key <32hex> -i <in> -c copy <out>` は映像・音声とも復号できた。
- PSSH は暗号化ストリームの init セグメントに含まれる(`pssh` ボックス)。YouTube の PSSH は `YOUTUBE:<16桁>` の KID を持つ。
- ライセンス採取は Firefox の page realm で行う必要がある。YouTube は **Trusted Types** (`require-trusted-types-for 'script'`) を有効にしており、`script.textContent = "..."` は CSP 違反になる。`trustedTypes.createPolicy(...).createScript(...)` を経由すると注入できる。`document.defaultView` への代入や sandbox の `window` への代入はページに反映されない。
- 保存後の再生確認は `ffmpeg -v error -t 10 -i <file> -f null -` の stderr 行数で判定する。暗号化されたままなら数千行、正常なら 0 行になる。
- 実測確認日: 2026-11-15。

## 実行環境

- デバイスファイルの解決順は「`--device` → `config.json` の `device` → スクリプトと同じフォルダの `*.wvd` → MFT 列挙」。記憶したパスが存在しない場合は、そのまま次の手段へ進んで再探索し、見つかったパスで `config.json` を上書きする。
- PC 全体の検索は NTFS の MFT を `FSCTL_ENUM_USN_DATA` で列挙する。`GENERIC_READ` でボリュームを開くため管理者権限が必要で、非昇格時は自分自身を `runas` で起動して結果を JSON で受け取る。MFT 6,687,643 件で約 10〜12 秒、`where /R` は同じ環境で約 172 秒だった(2026-11-15 実測)。昇格できない場合は `where /R` へフォールバックする。
- `FSCTL_ENUM_USN_DATA` の `HighUsn` に `0xFFFFFFFFFFFFFFFF` を渡すと `ERROR_HANDLE_EOF (38)` で 0 件になる。`FSCTL_QUERY_USN_JOURNAL` の `NextUsn` を渡すと列挙できる。入力は `MFT_ENUM_DATA_V0`(24 バイト)を使う。
- 記憶先は Cookie と同じ `%USERPROFILE%\.cache\d-download-pipeline\config.json`。`D_DOWNLOAD_CACHE_DIR` で両方の置き場所を変えられる。

- Firefox は `MOZ_REMOTE_DEBUGGING_PORT` を設定して起動すると Marionette が有効になる。
- `COMMON-AGENTS.md` はシンボリックリンクの代わりにハードリンクで置いた。この環境ではシンボリックリンクの作成に管理者権限が必要で失敗したため。リンク先を置換すると追随しない点に注意する。
- 日本語を含む CLI 出力は、コンソールのコードページが cp932 なら問題ないが、cp1252 などでは `UnicodeEncodeError` になる。`sys.stdout.reconfigure()` は変換可否を判定してから使う。無条件に UTF-8 へ変えると cp932 コンソールで文字化けする。
- 実測確認日: 2026-11-15。サイト仕様が変わったら本ファイルを更新する。
