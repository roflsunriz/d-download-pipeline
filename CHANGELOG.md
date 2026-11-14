# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/lang/ja/).

## [Unreleased]

## [0.1.0] - 2026-11-15

### Added

- 作品名または workId を指定して、対象話をまとめて保存できる CLI を追加した。
- 解像度(`1080p` / `720p` / `480p` / `360p`)を選択できるようにした。
- Cookie をファイルへキャッシュし、2 回目以降はブラウザを必要としないようにした。
- 既存の出力をスキップする再開機能と、`--force` による再取得を追加した。
- ダウンロードは Range による再開に対応し、通信断で最初からやり直さないようにした。
- `--catalog` で新着・ジャンル・五十音・ランキング・特集・検索・workId から作品と話数を対話で選べるようにした。一覧はページ送りでき、選択後に続けて別の作品も選べる。
- `--youtube` で無料公開の YouTube 動画を MP4 として保存できるようにした。`availability` を見て有料・メンバー限定を除外し、映像は H.264、音声は AAC を優先する。

### Changed

- `--quality` の既定を「最高画質」に変えた。省略時は最も高い解像度と最も高い音声ビットレートを選ぶ。
- `--device` を省略できるようにした。指定 → 記憶したパス → スクリプトと同じフォルダ → NTFS の MFT 列挙の順に `.wvd` を探し、見つけたパスを次回以降のために保存する。記憶したパスが消えていた場合は再検索する。

### Fixed

- `mp4decrypt` へ KID をダッシュ付きで渡すと復号されず rc=0 になる問題を修正した。32 桁 hex で渡し、復号後の `tenc` 残留を検査する。
- 暗号化情報を残したまま多重化して再生できないファイルができる問題を修正した。
- 話数一覧のない古い作品で `contentUrls` に `highest` が無い場合に対応した。
- 英語版 Windows のコンソール(cp1252 など)で日本語出力が `UnicodeEncodeError` になる問題を修正した。日本語を出せないコンソールでは出力を UTF-8 に切り替える。
