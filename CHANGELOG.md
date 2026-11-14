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

### Fixed

- `mp4decrypt` へ KID をダッシュ付きで渡すと復号されず rc=0 になる問題を修正した。32 桁 hex で渡し、復号後の `tenc` 残留を検査する。
- 暗号化情報を残したまま多重化して再生できないファイルができる問題を修正した。
- 話数一覧のない古い作品で `contentUrls` に `highest` が無い場合に対応した。
