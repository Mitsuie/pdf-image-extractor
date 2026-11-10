# 計画書: Issue #13 ビルド・配布基盤の整備（main.py同期・チェックサム生成）

- 対象 Issue: [#13](https://github.com/Mitsuie/pdf-image-extractor/issues/13)
- 作業ブランチ: `agy/issue-13-build-and-packaging`（`main` の最新から作成）
- 前提となる Issue: **#10 および #12 が `main` にマージ済み**であること（`main.py` および `version.py` / `updater.py` が存在すること）。マージされていない場合は、作業を始めずに報告する。

## 目的

PyInstaller ビルド仕様（`PDFImageExtractor.spec`）を最新の構成（`main.py`、新モジュール）に同期し、ワンクリック／単一コマンドで PyInstaller ビルドから SHA-256 チェックサムファイルの生成、`dists/` への配置までを自動完結させる `build.py` スクリプトを整備する。また、関連ドキュメントを最新手順に更新する。

## 背景・前提

- 現状の課題:
  - `PDFImageExtractor.spec` の設定が古い `app.py` 前提のままとなっている。
  - #12 で実装された自動アップデート機能では、リリースアセットとして `.exe` に加えて完全性照合用の `.sha256` ファイルが必須となる。これを手作業でハッシュ計算・ファイル生成するのはミスを誘発しやすい。
  - 現在 `dists/` に `.exe` や未追跡のショートカットが直接配置されているが、ビルド手順が標準化されていない。
- `build.py` の設計方針（`RL-Log-Comparator` の `packaging/build.py` 準拠）:
  - 事前チェック: テスト（`pytest`）の実行確認オプション（`--skip-tests` でスキップ可能）。
  - ビルド実行: `subprocess.run([sys.executable, "-m", "PyInstaller", "PDFImageExtractor.spec", "--clean"])` を実行。
  - チェックサム自動計算: 生成された `PDFImageExtractor.exe` に対し、`hashlib.sha256()` で SHA-256 ハッシュを計算し、`PDFImageExtractor.exe.sha256`（フォーマット: `<hex_hash> *PDFImageExtractor.exe\n`）を出力。
  - 配布フォルダへの配置: `dists/` フォルダへ `.exe` および `.sha256` を自動コピー。
  - 不要な中間成果物（`build/`）のクリーンアップ。

## 変更対象（ファイル/フォルダ）

- 変更: `PDFImageExtractor.spec`
- 新規: `build.py`
- 変更: `doc/executable_creation_guide.md`
- 変更: `.gitignore`（`build.py` 実行時の一時ファイル除外確認）
- 新規: `tests/test_build_script.py`（チェックサム生成ロジックの単体テスト）
- 新規: `doc/plans/plan_20261109_issue13_build_and_packaging.md`（本計画書。作成済み）

## 手順

1. `PDFImageExtractor.spec` の検証と最適化:
   - エントリーポイントが `main.py` になっていることを確認（#10 で変更済みだが、必要に応じて `hiddenimports` 等を整理）。
   - `name='PDFImageExtractor'`, `console=False`, `onefile=True`（単一exe化設定）が正しく構成されていることを確認。
2. `build.py` をリポジトリ直下に新規作成する:
   - 標準ライブラリのみで構成（`hashlib`, `pathlib`, `subprocess`, `sys`, `shutil`, `argparse`）。
   - 関数 `generate_sha256_file(exe_path: Path) -> Path`:
     - チャンク読み込みで SHA-256 を計算。
     - `<exe_name>.sha256` ファイルを `<hash> *<exe_name>\n`（sha256sum互換形式）で出力。
   - 関数 `run_tests() -> bool`:
     - `pytest` をサブプロセスで実行し、パスした場合のみビルドに進む（テスト失敗時はビルド中止）。
   - 関数 `clean_build_artifacts()`:
     - 既存の `build/`, `dist/` 一時ディレクトリを安全に削除。
   - `main()` 処理:
     - 引数パーサー（`--skip-tests`, `--output-dir`）を定義。
     - テスト実行（`--skip-tests` がない場合）。
     - PyInstaller によるビルド実行。
     - `dist/PDFImageExtractor.exe` の存在確認。
     - `generate_sha256_file` の実行。
     - 成果物（exe と sha256）を `dists/`（または指定フォルダ）へコピー。
     - 完了メッセージとハッシュ値をコンソールに表示。
3. `doc/executable_creation_guide.md` の更新:
   - 旧来のコマンド直叩き手順から、`python build.py` を実行する推奨手順に記述を改定。
   - 手動ビルド手順も併記しつつ、チェックサムファイル（`.sha256`）の必要性と自動生成について解説。
4. 単体テストの追加:
   - `tests/test_build_script.py`:
     - `generate_sha256_file` のテスト（一時ファイルを作成し、計算されたハッシュ文字列およびファイル形式が sha256sum 形式と合致するか検証）。
5. 動作確認とビルド検証:
   - `python -m pytest -q` を実行して全テスト通過を確認。
   - `python build.py --skip-tests` を実行し、`dists/PDFImageExtractor.exe` および `dists/PDFImageExtractor.exe.sha256` が生成されることを確認。
   - 生成された `.exe` を実際に起動し、GUIが表示されること、抽出処理および「ヘルプ > 更新を確認…」が動作することを確認。

## やらないこと（触らない範囲）

- CI（GitHub Actions）による自動リリースワークフローの構築（リポジトリのCI設定方針が決まるまでスコープ外とする）
- アプリケーションロジック（`extractor.py` や `app_window.py`）の変更
- `main` ブランチへの直接コミット

## 完了条件

- [x] `PDFImageExtractor.spec` が `main.py` および最新モジュール群に対応している
- [x] `build.py` が新規作成され、`python build.py` でビルドと `.sha256` 生成・配置が一括実行できる
- [x] `tests/test_build_script.py` が作成され、チェックサム生成のテストが通る
- [x] `doc/executable_creation_guide.md` が最新のビルド手順に更新されている
- [x] 生成された exe が正常に動作する
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` の結果を報告する。
- `python build.py` の実行結果および生成されたファイル一覧・ハッシュ値を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

