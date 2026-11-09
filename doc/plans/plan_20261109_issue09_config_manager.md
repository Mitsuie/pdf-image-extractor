# 計画書: Issue #9 設定ファイル管理ロジックの独立クラス化（ConfigManager）

- 対象 Issue: [#9](https://github.com/Mitsuie/pdf-image-extractor/issues/9)
- 作業ブランチ: `agy/issue-9-config-manager`（`main` の最新から作成）
- 前提となる Issue: **#7 が `main` にマージ済み**であること（#8 とは独立しているため、#8 と並行して作業してよい）。

## 目的

`app.py` の `get_config_path`、`load_config`、`save_config`（[app.py](../../app.py) 309〜385 行目）と同じ処理を、GUI に依存しない `ConfigManager` クラスとして `config_manager.py` に作り、単体テストを書く。

## 背景・前提

- **本 Issue では `app.py` を変更しない。** `app.py` から `ConfigManager` を使うように切り替えるのは、#10（`app_window.py` を作るとき）で行う。
- 今の振る舞い（そのまま再現する）
  - 設定ファイルのパス: 単体 exe の場合（`sys.frozen` が真）は exe があるフォルダ、スクリプトの場合はソースがあるフォルダの `config.json`。そのフォルダに `.write_test` を作れない場合は、`%APPDATA%\pdf-image-extractor\config.json`（`APPDATA` がなければ `~`）にする。
  - 読み込み: ファイルが存在する場合は、`history_output_dirs` キーのリストのうち、空でない文字列だけを `os.path.normpath` して、順序を保ったまま重複を除き、先頭 3 件にする。読み込みに失敗した場合は `[]`。
  - 保存: 前後の空白を除いたパスが空なら何もしない。`normpath` した上で、すでに履歴にあれば一度削除し、先頭に追加して 3 件にする。`{"history_output_dirs": [...]}` を UTF-8、`ensure_ascii=False`、`indent=4` で書く。書き込みに失敗しても例外を出さない（今は `print`）。
  - GUI のコンボボックスは、保存に失敗しても更新される。そのため、`ConfigManager` は、履歴をメモリー上にも持つ。
- `config_manager.py` は、`app.py` と同じリポジトリ直下に置く。そのため、`os.path.dirname(os.path.abspath(__file__))` の結果は、今と変わらない。
- 変更点（1 つだけ）: 保存するときに、既存の `config.json` にほかのキーがあれば、それを残す（#12 以降で設定項目を増やせるようにするため）。

## 変更対象（ファイル/フォルダ）

- 新規: `config_manager.py`
- 新規: `tests/test_config_manager.py`
- 新規: `doc/plans/plan_20261109_issue09_config_manager.md`（本計画書。作成済み）

## 手順

1. `config_manager.py` を作る。標準ライブラリ（`json`、`logging`、`os`、`sys`）だけを使う。`from __future__ import annotations` を付ける。
   - 定数: `APP_DIR_NAME = "pdf-image-extractor"`、`CONFIG_FILENAME = "config.json"`、`HISTORY_KEY = "history_output_dirs"`、`DEFAULT_MAX_HISTORY = 3`
   - `logger = logging.getLogger(__name__)`
   - 関数 `get_app_dir() -> str`: `getattr(sys, "frozen", False)` なら `os.path.dirname(os.path.abspath(sys.executable))`、そうでなければ `os.path.dirname(os.path.abspath(__file__))`。
   - 関数 `is_dir_writable(path: str) -> bool`: `path` に `.write_test` を作って消せれば `True`、`OSError`（`PermissionError` を含む）が出れば `False`。
   - 関数 `get_appdata_dir() -> str`: `os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_DIR_NAME)`。
   - 関数 `resolve_config_path(app_dir: str | None = None) -> str`: `app_dir` が `None` なら `get_app_dir()` を使う。`is_dir_writable(app_dir)` なら `app_dir/config.json`。そうでなければ、`get_appdata_dir()` を `os.makedirs(..., exist_ok=True)` で作り、その中の `config.json`。
   - クラス `ConfigManager`
     - `__init__(self, config_path: str | None = None, max_history: int = DEFAULT_MAX_HISTORY)`: `config_path` が `None` なら `resolve_config_path()` を使う。`max_history` が 1 未満なら `ValueError`。内部の履歴 `self._history: list[str] = []`。
     - プロパティ `config_path -> str`
     - プロパティ `max_history -> int`
     - プロパティ `history -> list[str]`: 内部の履歴の**コピー**を返す。
     - `load_history(self) -> list[str]`: ファイルから読み込み（上記の規則）、内部の履歴を更新して、そのコピーを返す。読み込みに失敗した場合（`OSError`、`json.JSONDecodeError`、`UnicodeDecodeError`）は `logger.warning` を出力して `[]` を返す。JSON の最上位が `dict` でない場合や、キーの値が `list` でない場合も `[]`。
     - `add_history(self, path: str) -> None`: 上記の「保存」の規則で、内部の履歴を更新してから `_save()` を呼ぶ。
     - `_save(self) -> None`: 既存のファイルが読めて、最上位が `dict` なら、それをもとに `HISTORY_KEY` だけを書き換える。読めない場合は新しい `dict` を使う。書き込みに失敗した場合（`OSError`）は `logger.warning` を出力し、例外を出さない。
   - すべての関数とメソッドに、型ヒントと日本語の docstring を付ける。
2. `tests/test_config_manager.py` を作る（GUI は使わない。`tmp_path`、`monkeypatch`、`caplog` を使う）。
   - パスの解決
     - `is_dir_writable(tmp_path)` が `True` で、実行後に `.write_test` が残っていない。
     - 存在しないディレクトリでは `is_dir_writable` が `False`。
     - `resolve_config_path(str(tmp_path))` が `tmp_path/config.json`。
     - `monkeypatch` で `config_manager.is_dir_writable` を常に `False` にし、`APPDATA` を `tmp_path/"appdata"` に設定すると、`tmp_path/appdata/pdf-image-extractor/config.json` を返し、そのフォルダが作られている。
     - `APPDATA` を削除し（`monkeypatch.delenv("APPDATA", raising=False)`）、`USERPROFILE` と `HOME` を `tmp_path` に設定すると、`tmp_path/pdf-image-extractor/config.json` になる。
     - `monkeypatch.setattr(sys, "frozen", True, raising=False)` と `sys.executable` の差し替えで、`get_app_dir()` が exe のフォルダを返す。
   - 読み込み
     - ファイルがない → `[]`
     - 壊れた JSON → `[]`、かつ WARNING が記録される
     - 最上位が `list`、またはキーの値が `str` → `[]`
     - 空文字列・空白だけの文字列・数値・`None` が除かれ、`normpath` され（`"C:/a/b"` → `"C:\\a\\b"`）、重複が除かれ、先頭 3 件になる
   - 追加・保存
     - 新しいパスが先頭に追加され、ファイルにも保存される
     - すでにあるパスを追加すると先頭に移動し、重複しない
     - 4 件目を追加すると、最も古いものが消えて 3 件になる
     - `max_history=5` を指定すると 5 件まで残る。`max_history=0` は `ValueError`
     - 空文字列・空白だけの文字列は、無視される（ファイルも作られない）
     - 日本語を含むパスが、ファイルに `\u` のエスケープではなくそのまま書かれ、読み直しても一致する
     - 既存のファイルにある別のキー（例: `{"other": 1}`）が、保存後も残っている
     - 保存先のディレクトリが存在しない `config_path` でも、`add_history` は例外を出さず、`history` は更新され、WARNING が記録される
     - `history` の戻り値を変更しても、内部の履歴は変わらない
3. `python -m pytest -q` で全件が成功することを確認する。

## やらないこと（触らない範囲）

- `app.py` の変更（`ConfigManager` への切り替えは #10 で行う）
- 履歴以外の新しい設定項目の追加
- 設定ファイルの形式やキー名の変更
- `extractor.py`、ドキュメントの変更
- 他の計画書のコミット
- `main` ブランチへの直接のコミット

## 完了条件

- [x] `config_manager.py` に `ConfigManager`（`load_history`、`add_history`、`history`）と、パスを解決する関数がある
- [x] 履歴の上限件数が定数 `DEFAULT_MAX_HISTORY = 3` になっていて、引数で変えられる
- [x] `tests/test_config_manager.py` に、パスの解決（書き込みできない場合の `%APPDATA%` へのフォールバックを含む）、読み込み、重複の除去、上限件数、保存失敗のテストがある
- [x] GUI を起動せずに `python -m pytest -q` で全件が成功する
- [x] `git diff --stat main...HEAD` に `app.py` が含まれていない
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` の最終行を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

