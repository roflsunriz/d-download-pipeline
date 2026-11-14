# AGENTS.md

## 最初に読む

- `COMMON-AGENTS.md`(このファイルと同じ階層)を先頭から末尾まで全文読む。これは `%USERPROFILE%\Documents\myAGENTS\AGENTS.md` へのシンボリックリンクで、Git 管理外である。
- `findings.md` を全文読む。構成、環境、コマンド、調査結果はここに集約する。
- 読了後、最初の進捗報告で全文読了を明示する。

## このリポジトリでの指示

- 応答は日本語で行う。
- `README.md` は利用手順だけを書く。目的・仕組みの説明は載せない。
- 利用者向けの挙動、引数、出力を変えたら、同じ作業で `README.md`、`CHANGELOG.md`、`verification.md`、`how-to-update.md` を更新する。
- 認証情報(Cookie、`.wvd`、トークン、ライセンス)を commit しない。`downloads/`、`work_*/`、`.cache/` も commit しない。
- 変更は日本語の Conventional Commits(`type(scope): 要約`)で 1 変更 1 commit とし、push 先は `main` とする。
- 検証は `verification.md` の手順に従う。実サイトへの追加試行の上限は共通指針に従う。
- 依存を追加・更新したら `requirements.txt` と `how-to-update.md` を合わせて直す。
