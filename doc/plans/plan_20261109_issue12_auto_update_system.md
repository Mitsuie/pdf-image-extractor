# 計画書: Issue #12 GitHub Releases を用いた自動アップデートシステムの実装

- 対象 Issue: [#12](https://github.com/Mitsuie/pdf-image-extractor/issues/12)
- 作業ブランチ: `agy/issue-12-auto-update-system`（`main` の最新から作成）
- 前提となる Issue: **#10 が `main` にマージ済み**であること（`app_window.py` が存在すること。#11 との依存関係は任意だが、推奨順序は #10 -> #11 -> #12）。マージされていない場合は、作業を始めずに報告する。

## 目的

`RL-Log-Comparator` のアーキテクチャに準拠し、外部ライブラリを追加することなく、GitHub Releases API を利用して最新バージョンの検出・リリースノート表示・最新 exe のダウンロード・SHA-256 完全性検証・自動起動を行うアップデートシステムを実装する。

## 背景・前提

- 現状の課題:
  - アプリケーションにバージョン更新通知や自動アップデート機能がなく、新バージョンが出ても利用者が手動でGitHubのReleasesを確認して再ダウンロードする必要がある。
- `RL-Log-Comparator` 準拠の設計仕様:
  - **ゼロ外部依存**: `requests` などのサードパーティ製ライブラリを使わず、Python標準ライブラリ（`urllib.request`, `json`, `hashlib`, `subprocess`, `re`, `logging`）のみで完結させる。
  - **セマンティックバージョニングの比較**: `v1.2.0` や `1.1.0` などのバージョン文字列をタプル比較し、新バージョンがあるかを判定。
  - **SHA-256 完全性検証の徹底**: リリースアセットに添付された `.sha256` ファイル（または GitHub release asset digest）を取得し、ダウンロードした `.exe` の SHA-256 ハッシュと照合。不一致時は実行せず中断しエラー通知。
  - **進捗通知と中断機能**: ダウンロードをチャンク単位で行い、進捗コールバックと `threading.Event` による中断に対応。
  - **Windowsでの独立起動**: アップデート適用時、既存アプリ終了後に新exeを `subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP` で起動。
  - **UIダイアログ**: Tkinter による `UpdateDialog`（モーダル）。新バージョンの説明（リリースノート）を表示し、同意を得た上でダウンロード・更新を実行。

## 変更対象（ファイル/フォルダ）

- 新規: `version.py`（バージョン定数およびリポジトリ識別子）
- 新規: `updater.py`（更新確認・ダウンロード・検証・起動コアロジック）
- 新規: `update_dialog.py`（Tkinter用アップデート確認・進捗ダイアログ）
- 変更: `app_window.py`（メニューバー「ヘルプ」>「更新を確認…」の追加）
- 新規: `tests/test_updater.py`（バージョン比較、APIパース、ハッシュ検証の単体テスト）
- 新規: `doc/plans/plan_20261109_issue12_auto_update_system.md`（本計画書。作成済み）

## 手順

1. `version.py` を新規作成する。
   - `__version__ = "1.1.0"`（既存コミットに合わせたバージョン番号）
   - `GITHUB_REPO_OWNER = "Mitsuie"`
   - `GITHUB_REPO_NAME = "pdf-image-extractor"`
2. `updater.py` を新規作成し、以下のコンポーネントを実装する。
   - 例外クラス: `UpdateVerificationError(Exception)`, `UpdateCancelledError(Exception)`
   - データクラス:
     ```python
     @dataclass
     class UpdateInfo:
         current_version: str
         latest_version: str
         release_name: str
         release_notes: str
         html_url: str
         exe_download_url: str | None
         exe_name: str | None
         exe_size: int | None
         expected_sha256: str | None
     ```
   - バージョン比較ユーティリティ:
     - `parse_version_tuple(v_str: str | None) -> tuple[int, ...]`: `"v1.2.3"` -> `(1, 2, 3)`
     - `compare_versions(v1: str, v2: str) -> int`: v1 < v2 なら -1, v1 == v2 なら 0, v1 > v2 なら 1
     - `is_newer_version(current: str, latest: str) -> bool`
   - リリース取得関数:
     - `fetch_latest_release_info(owner: str, repo: str, current_version: str, timeout_sec: float = 5.0) -> UpdateInfo | None`
     - GitHub API: `https://api.github.com/repos/{owner}/{repo}/releases/latest`
     - User-Agent ヘッダーの付与（`{repo}-AppUpdater/{current_version}`）
     - アセット走査: `*.exe` ファイルおよび対応する `*.sha256` ファイルの探索。
     - `.sha256` ファイルの内容（`<hash> *<filename>` または `<hash>` 単体）をパースして `expected_sha256` に格納。
   - ダウンロード関数:
     - `download_file(url: str, dest_path: str, expected_sha256: str | None = None, progress_callback: Callable[[int, int], None] | None = None, cancel_event: threading.Event | None = None, chunk_size: int = 65536) -> None`
     - ストリーミングダウンロードを行い、ダウンロードしながら `hashlib.sha256()` を更新。
     - ダウンロード完了後にハッシュ照合。不一致時は `dest_path` を削除して `UpdateVerificationError` を送出。
   - 起動関数:
     - `launch_executable(exe_path: str) -> None`: Windows環境で `subprocess.Popen([exe_path], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)` を実行。
3. `update_dialog.py` を新規作成する。
   - `tk.Toplevel` を継承した `UpdateDialog` クラスを実装。
   - 親ウィンドウの中央にモーダル配置。
   - UI構成:
     - タイトル/ヘッダー: 「新しいバージョンが利用可能です（vX.Y.Z）」
     - リリースノート表示エリア（読み取り専用の `ScrolledText`）
     - プログレスバー（ダウンロード中のみ表示または常に配置）
     - ボタングループ: 「今すぐ更新」「後で閉じる」（ダウンロード中は「中断」に変化）
   - ダウンロード処理はバックグラウンドスレッドで実行し、UIへの進捗更新は `self.after(0, ...)` で行う。
   - 検証成功後、「アプリを終了して新しいバージョンを起動します」と通知し、`launch_executable` を呼んでアプリを安全に終了（`os._exit(0)` または `root.destroy()`）。
4. `app_window.py` への統合:
   - メニューバー（`tk.Menu`）を作成。
   - 「ヘルプ(&H)」メニューに「更新を確認…」を追加し、クリック時に更新確認スレッドを起動。
   - 更新がない場合は `messagebox.showinfo("更新確認", "お使いのバージョンは最新です。")` を表示。
   - 更新がある場合は `UpdateDialog` を表示。
5. 単体テストの実装:
   - `tests/test_updater.py`:
     - `parse_version_tuple`: `"1.0.0"`, `"v1.2.3"`, `"v2.0"`, 不正文字列等のテスト。
     - `compare_versions` / `is_newer_version`: 等価、メジャー更新、マイナー更新、パッチ更新等のテスト。
     - `.sha256` ファイルパース処理のテスト。
     - `download_file` のハッシュ照合（正常一致、不一致時の例外とファイル削除）のモックテスト。
6. 全体テストの実行:
   - `python -m pytest -q` を実行し、全件成功することを確認。

## やらないこと（触らない範囲）

- Inno Setup などの本格的インストーラーの作成（単体exeの更新に対応）
- PyInstaller specの更新やビルドスクリプトの作成（#13 で行う）
- GitHub API への認証トークン必須化（パブリックリポジトリのため認証なしアクセス）
- `main` ブランチへの直接コミット

## 完了条件

- [x] `version.py`、`updater.py`、`update_dialog.py` が新規作成され、標準ライブラリのみで構成されている
- [x] セマンティックバージョニング比較ロジックが正確に機能し、単体テストが通る
- [x] SHA-256 完全性検証がダウンロード時に実行され、不一致時はファイルが破棄される
- [x] GUIの「ヘルプ > 更新を確認…」からダイアログが表示され、最新版情報が確認できる
- [x] `python -m pytest -q` で全テストが成功する
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` のテスト結果を報告する。
- GUIを起動し、メニューバーおよび更新確認ダイアログの挙動を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

