# 判明事項

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

## 実行環境

- Firefox は `MOZ_REMOTE_DEBUGGING_PORT` を設定して起動すると Marionette が有効になる。
- `COMMON-AGENTS.md` はシンボリックリンクの代わりにハードリンクで置いた。この環境ではシンボリックリンクの作成に管理者権限が必要で失敗したため。リンク先を置換すると追随しない点に注意する。
- 実測確認日: 2026-11-15。サイト仕様が変わったら本ファイルを更新する。
