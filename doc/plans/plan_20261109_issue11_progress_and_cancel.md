# 計画書: Issue #11 抽出進捗通知 (プログレスバー) とキャンセル機能の実装

- 対象 Issue: [#11](https://github.com/Mitsuie/pdf-image-extractor/issues/11)
- 作業ブランチ: `agy/issue-11-progress-and-cancel`（`main` の最新から作成）
- 前提となる Issue: **#10 が `main` にマージ済み**であること（`app_window.py` が存在し、スレッドセーフなUI更新機構が備わっていること）。マージされていない場合は、作業を始めずに報告する。

## 目的

大量ページを持つPDFや複数ファイルの一括抽出処理において、処理進捗を視覚的に把握できるプログレスバーと、処理を安全に中断できるキャンセルボタンを実装する。

## 背景・前提

- 現状の課題:
  - ページ数が多いPDFやフォルダ一括処理時に、ログエリアに開始メッセージが出るだけで進捗割合が分からず、フリーズしているように見えやすい。
  - 誤って巨大なPDFや大量のPDFが入ったフォルダを指定した場合、アプリを強制終了する以外に途中で止める手段がない。
- 設計方針:
  - `extractor.py`:
    - `extract_images_from_pdf` の引数に `progress_callback: Callable[[int, int], None] | None = None`（引数: `current_page: int`, `total_pages: int`）と `cancel_event: threading.Event | None = None` を追加（デフォルト `None` で既存コードとの後方互換性を維持）。
    - ページ走査ループの各ステップ開始時に `if cancel_event and cancel_event.is_set():` を判定し、中断時はループを抜けて中断されたことを示す例外（例: `ExtractionCancelledError`）を送出するか、またはそれまでに抽出された枚数を返して正常終了する。
    - 中断時の挙動: 中断されたページまでのファイルは保存されたまま残し、ログに「処理がユーザーによって中断されました」と明示する。
    - `extract_images_from_folder` も同様に、ファイル走査ループおよび各PDF抽出呼び出しに `cancel_event` を伝搬させ、即時中断できるようにする。
  - `app_window.py`:
    - ログフレームの上部に `ttk.Progressbar(mode="determinate")` を配置。
    - 実行ボタンの横に「中断」ボタン（`cancel_btn`）を配置（初期状態は `state="disabled"`）。
    - 処理開始時: 「実行」ボタンを `disabled`、「中断」ボタンを `normal` にし、プログレスバーを 0% に初期化。
    - 進捗更新時: `progress_callback` から `self.root.after(0, self._update_progress, current, total)` を呼び出してプログレスバーを更新。
    - 中断ボタン押下時: `self.cancel_event.set()` を呼び出し、ボタンを `disabled` にして安全な停止を待機。
    - 処理完了/中断後: ボタンの状態を復帰し、プログレスバーをリセットまたは 100% に設定。

## 変更対象（ファイル/フォルダ）

- 変更: `extractor.py`
- 変更: `app_window.py`
- 変更: `tests/test_extractor.py`
- 新規: `tests/test_cancellation.py`
- 新規: `doc/plans/plan_20261109_issue11_progress_and_cancel.md`（本計画書。作成済み）

## 手順

1. `extractor.py` の拡張:
   - 例外クラス `ExtractionCancelledError(Exception)` を定義。
   - `extract_images_from_pdf`:
     - 引数に `progress_callback: Callable[[int, int], None] | None = None`, `cancel_event: threading.Event | None = None` を追加。
     - ページループ冒頭で `if cancel_event and cancel_event.is_set(): raise ExtractionCancelledError("ユーザーにより処理が中断されました。")` を判定。
     - 各ページの処理直後（または直前）に `if progress_callback: progress_callback(page_num + 1, total_pages)` を呼び出し。
   - `extract_images_from_folder`:
     - 引数に `file_progress_callback: Callable[[int, int], None] | None = None`, `page_progress_callback: Callable[[int, int], None] | None = None`, `cancel_event: threading.Event | None = None` を追加。
     - ファイル走査ループ冒頭で `if cancel_event and cancel_event.is_set(): raise ExtractionCancelledError(...)` を判定。
     - `extract_images_from_pdf` の呼び出しに `cancel_event` と `page_progress_callback` を渡す。
2. `app_window.py` のGUI拡張:
   - `AppWindow.__init__` に `self.cancel_event = threading.Event()` を用意。
   - `_create_action_buttons` に「中断」ボタン（`self.cancel_btn`、スタイル `Danger.TButton` 等）を追加（初期状態 disabled、command=`self.cancel_extraction`）。
   - `_create_log_section` の上部に `ttk.Progressbar(parent, orient="horizontal", mode="determinate")` を配置。
   - `_update_progress(self, current: int, total: int)` メソッドを追加し、プログレスバーの `value = (current / total) * 100` を設定。
   - `start_extraction`: `self.cancel_event.clear()` を行い、`self.cancel_btn.config(state="normal")`。
   - `cancel_extraction`: `self.cancel_event.set()` を呼び出し、ログに「中断要求を送信しました...」を出力、`self.cancel_btn.config(state="disabled")`。
   - `run_file_extraction` / `run_folder_extraction`:
     - `ExtractionCancelledError` を `except` し、「処理が中断されました」のメッセージとログをUIに通知。
     - `finally` で「実行」ボタンを `normal`、「中断」ボタンを `disabled` に戻す。
3. 単体テストの追加:
   - `tests/test_cancellation.py`:
     - `cancel_event` を最初から `set()` して `extract_images_from_pdf` を呼ぶと、即座に `ExtractionCancelledError` が発生すること。
     - 1ページ目完了後に `cancel_event.set()` を呼ぶような `progress_callback` を渡し、2ページ目以降が処理されずに中断されること。
     - 既存の引数指定なしでの呼び出し（後方互換性）がそのまま動作すること。
   - `tests/test_extractor.py` の既存テストがすべてパスすることを確認。
4. 動作確認:
   - `python -m pytest -q` で全テストが通ることを確認。
   - `python main.py` を起動し、複数ページのPDFを抽出してプログレスバーが動くこと、および途中で中断ボタンを押して安全に停止することを確認。

## やらないこと（触らない範囲）

- 中断時にすでにディスクへ書き出された画像の自動削除（部分的に抽出された画像を必要とするケースもあるため、無理なロールバックは行わず、ログで案内する）
- GitHub Releases アップデート機能（#12 で行う）
- ビルド設定の変更（#13 で行う）
- `main` ブランチへの直接コミット

## 完了条件

- [x] `extractor.py` の関数に進捗コールバックおよび `cancel_event` のサポートが追加されている
- [x] 中断時に `ExtractionCancelledError` が送出され、安全に処理が停止する
- [x] GUIに `ttk.Progressbar` と「中断」ボタンが追加され、処理中に進捗が表示される
- [x] 中断ボタンを押すと現在ページ終了時点で処理が停止し、UI状態が安全に復帰する
- [x] 既存のテストおよび新規キャンセルテストを含む `python -m pytest -q` が全件パスする
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` のテスト結果を報告する。
- 中断テストの実行ログおよびGUI手動確認の結果を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

