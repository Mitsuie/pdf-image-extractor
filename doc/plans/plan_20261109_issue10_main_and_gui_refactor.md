# 計画書: Issue #10 起動スクリプトの main.py 化と GUI 構造化・スレッドセーフ化

- 対象 Issue: [#10](https://github.com/Mitsuie/pdf-image-extractor/issues/10)
- 作業ブランチ: `agy/issue-10-main-and-gui-refactor`（`main` の最新から作成）
- 前提となる Issue: **#8 および #9 が `main` にマージ済み**であること（`extractor.py` の定数化・型定義および `config_manager.py` が存在すること）。マージされていない場合は、作業を始めずに報告する。

## 目的

起動スクリプトを `app.py` から `main.py` へ移行し、GUI本体を `app_window.py` へ分離・構造化する。あわせて Tkinter のシングルスレッド制約を遵守するスレッドセーフなUI更新機構を導入し、#9 で作成した `ConfigManager` をGUIへ統合する。

## 背景・前提

- 現状の課題（[app.py](../../app.py)）:
  - `app.py` がエントリーポイント（`if __name__ == "__main__":`）と GUI 定義、設定管理、ワーカースレッド処理をすべて抱えている。
  - ワーカースレッド内（`run_file_extraction`, `run_folder_extraction`）から Tkinter ウィジェット（`ScrolledText`）へのログ追記や `messagebox.showinfo` / `showerror` を直接呼び出しており、マルチスレッドでのUI操作に関するTkinter制約に違反している。
  - `README.md`、`doc/executable_creation_guide.md`、`doc/venv_guide.md`、`PDFImageExtractor.spec` で `app.py` が直接指定されている。
- 方針:
  - `main.py`: アプリケーションの最小エントリーポイントとする。未捕捉例外ハンドラ（`sys.excepthook`）、ロギング初期化、Tk ルートの生成、`AppWindow` の呼び出し、イベントループ（`mainloop`）の実行を担当。
  - `app_window.py`: メインウィンドウクラス `AppWindow` を定義。`__init__` に集中しているUI構築処理を機能ごとのプライベートメソッドに分割する。
  - スレッドセーフティ: ワーカースレッドからのログ更新やダイアログ表示は、すべて `self.root.after(0, ...)` を介してメインスレッドで実行されるようにする。
  - 設定管理: `app.py` 内に直書きされていた設定関連処理を廃止し、`config_manager.ConfigManager` を利用する。
  - `app.py` の扱い: 後方互換性のため、`app.py` を即座に削除せず、`main.py` を呼び出す薄いラッパーとして残すか、非推奨警告を表示して `main()` を呼ぶ形にする。

## 変更対象（ファイル/フォルダ）

- 新規: `main.py`
- 新規: `app_window.py`
- 変更: `app.py`（`main.py` への移譲ラッパー化）
- 変更: `PDFImageExtractor.spec`（エントリーポイントを `main.py` に変更）
- 変更: `README.md`（起動コマンドを `python main.py` に更新、構成図を更新）
- 変更: `doc/executable_creation_guide.md`（`app.py` から `main.py` への言及変更）
- 変更: `doc/venv_guide.md`（必要に応じた記載更新）
- 新規: `tests/test_main_and_gui.py`（エントリーポイント呼び出し、設定統合のテスト）
- 新規: `doc/plans/plan_20261109_issue10_main_and_gui_refactor.md`（本計画書。作成済み）

## 手順

1. `main.py` を新規作成する。
   - `logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")` を設定。
   - 未捕捉例外をキャッチしてログ出力・必要に応じて `messagebox.showerror` を表示する `sys.excepthook` を設定。
   - `def main() -> None:` 関数を定義:
     - `root = tk.Tk()` を初期化。
     - `app = AppWindow(root)` を生成。
     - `root.mainloop()` を呼び出す。
   - `if __name__ == "__main__": main()` を配置。
2. `app_window.py` を新規作成し、`AppWindow` クラスを実装する。
   - [app.py](../../app.py) の `PDFImageExtractorApp` をベースに移行し、クラス名を `AppWindow` とする。
   - `ConfigManager` をインスタンス変数として保持（`self.config_manager = ConfigManager()`）。
   - UI構築処理を以下のメソッドに分割:
     - `_create_mode_section(parent)`: モード選択（単一/フォルダ）
     - `_create_input_section(parent)`: 入力元設定（ファイル/フォルダパス選択）
     - `_create_output_section(parent)`: 保存先設定（履歴コンボボックス、フォルダ選択、自動オープンチェックボックス）
     - `_create_action_buttons(parent)`: 実行・終了ボタン
     - `_create_log_section(parent)`: ログ表示エリア（ScrolledText）
   - スレッドセーフな通知機構の実装:
     - `safe_log(self, message: str) -> None`: `self.root.after(0, self._append_log, message)`
     - `safe_showinfo(self, title: str, message: str) -> None`: `self.root.after(0, messagebox.showinfo, title, message)`
     - `safe_showerror(self, title: str, message: str) -> None`: `self.root.after(0, messagebox.showerror, title, message)`
     - ワーカースレッド（`run_file_extraction`, `run_folder_extraction`）内のUI操作・ダイアログ呼び出しを上記 `safe_*` 経由に変更。
   - 履歴管理の切り替え:
     - コンボボックス初期値: `self.config_manager.load_history()`
     - 抽出実行時: `self.config_manager.add_history(output_dir)` を呼び出し、コンボボックスの `values` を `self.config_manager.history` で更新。
3. `app.py` を後方互換ラッパーに更新する。
   - `import warnings`
   - `warnings.warn("app.py is deprecated; please use main.py instead.", DeprecationWarning, stacklevel=2)`
   - `from main import main; if __name__ == "__main__": main()`
4. `PDFImageExtractor.spec` を更新する。
   - `Analysis(['app.py'], ...)` を `Analysis(['main.py'], ...)` に変更。
5. ドキュメント類の更新:
   - `README.md`: `python app.py` を `python main.py` に更新。ファイル構成図に `main.py`, `app_window.py`, `config_manager.py` を反映。
   - `doc/executable_creation_guide.md`: `app.py` を `main.py` に置き換え。
   - `doc/venv_guide.md`: 起動コマンド例がある場合、`main.py` に更新。
6. テストを作成・実行する:
   - `tests/test_main_and_gui.py`:
     - `main.py` のインポートおよび `main` 関数が存在することのテスト。
     - `AppWindow` の初期化テスト（ヘッドレス環境向けに `tkinter.Tk` が動作するか、またはモック化して確認）。
     - `ConfigManager` が `AppWindow` に組み込まれ、履歴がコンボボックスに渡されることのテスト。
   - `python -m pytest -q` を実行し、既存テスト含め全件パスすることを確認。
   - 手動起動確認: `python main.py` を起動し、UIレイアウトが崩れていないこと、単一抽出が動作することを確認。

## やらないこと（触らない範囲）

- プログレスバーや中断ボタンのUI追加（#11 で行う）
- GitHub Releases アップデートメニューの追加（#12 で行う）
- 自動ビルドスクリプト `build.py` の作成（#13 で行う）
- `extractor.py` のロジック変更
- `main` ブランチへの直接コミット

## 完了条件

- [x] `main.py` が新規作成され、`python main.py` でアプリケーションが正常に起動する
- [x] `app_window.py` に `AppWindow` が切り出され、UIセクション構築メソッドが分割されている
- [x] ワーカースレッドからのログ更新やダイアログ表示が `self.root.after` を介してスレッドセーフに行われている
- [x] `ConfigManager` がGUIに統合され、保存先履歴の読み込み・追加が正常に機能する
- [x] `app.py` が `main.py` を呼び出す互換ラッパーになっている
- [x] `PDFImageExtractor.spec` のエントリーポイントが `main.py` に変更されている
- [x] `README.md` および関連ガイド内の `app.py` の記述が `main.py` に更新されている
- [x] `python -m pytest -q` で全テストが成功する
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` の結果を報告する。
- `python main.py` を起動し、GUIの表示と動作確認結果を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

