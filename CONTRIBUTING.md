# コントリビューション

## 変更の流れ

1. Issue で変更内容を共有する(小さな修正は不要)。
2. `main` から branch を切る。
3. 変更と検証を行い、`CHANGELOG.md` の `[Unreleased]` に追記する。
4. Pull Request を出す。本文には変更、検証結果、未検証の点を書く。

## コード

- Python 3.12 以上。1 ファイル 1000 行以下を保つ。
- 型ヒントを付け、追加した関数には短い docstring かコメントで意図を書く。
- 利用者向けのメッセージは日本語にする。
- 例外を握りつぶさない。失敗したら理由と次の行動を示す。

## 検証

`verification.md` の手順を実行する。少なくとも次を確認する。

```powershell
python -m compileall -q d_download_pipeline.py
python d_download_pipeline.py --help
```

## 秘密情報

Cookie、`.wvd`、トークン、ライセンス、実出力ファイルを commit しない。`.gitignore` の対象を確認する。

## コミット

日本語の Conventional Commits を使う。

```
fix(decrypt): KID を 32 桁 hex で渡す
docs(readme): --force の説明を追加
```

## ドキュメント

利用手順を変えたら `README.md` を、挙動や検証を変えたら `verification.md` と `findings.md` を更新する。
