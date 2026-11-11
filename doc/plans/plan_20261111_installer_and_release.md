# 計画書: Inno Setup によるインストーラー作成基盤の整備と GitHub Release v1.1.0 の準備

- 作業ブランチ: `agy/installer-and-release`（`main` の最新から作成）
- 前提条件: **Issue #7〜#13 がすべて `main` にマージ済み**であること。
- ターゲットバージョン: **`v1.1.0`**（`version.py` の現行定義 `1.1.0` を維持）

---

## 1. 目的

Windows 向けデスクトップアプリケーションとして一般的なインストール体験（スタートメニュー登録、デスクトップショートカット作成、アンインストーラー提供、一般ユーザー／管理者両対応）を提供する **Inno Setup スクリプト（`installer.iss`）** を整備する。  
さらに、既存の `build.py` を拡張して PyInstaller による単体 `.exe` ビルドから Inno Setup による `Setup.exe` 生成、および双方の SHA-256 チェックサム生成までをワンコマンドで自動完結できるようにする。  
あわせて、GitHub Release `v1.1.0` 公開に必要なリリースノートおよびドキュメントを整備する。

---

## 2. 背景・前提

- **現状**:
  - Issue #13 で `build.py` が整備され、`dists/PDFImageExtractor.exe` およびその SHA-256 チェックサム（`PDFImageExtractor.exe.sha256`）が自動生成される環境が整った。
  - 現在の成果物はポータブル版単体実行ファイルのみであり、Program Files やスタートメニューへのインストール機能がない。
  - 端末環境には `C:\Program Files (x86)\Inno Setup 6\ISCC.exe` がインストール済みであり、Inno Setup 6 によるインストーラー生成が可能である。
- **配布方針（GitHub Release v1.1.0）**:
  - リリースアセットとして以下の4成果物をセットで提供する：
    1. `PDFImageExtractor_Setup_v1.1.0.exe`（インストーラー本体）
    2. `PDFImageExtractor_Setup_v1.1.0.exe.sha256`（インストーラーのチェックサム）
    3. `PDFImageExtractor.exe`（ポータブル版単体実行ファイル。`updater.py` による自動更新でも利用）
    4. `PDFImageExtractor.exe.sha256`（ポータブル版のチェックサム）

---

## 3. 変更対象（ファイル/フォルダ）

| 操作 | パス | 内容 |
| :---: | :--- | :--- |
| **新規** | `installer.iss` | Inno Setup 6 用インストーラー定義スクリプト |
| **変更** | `build.py` | Inno Setup コンパイラ（`ISCC.exe`）の探索・インストーラー自動ビルド機能（`--installer` / `--skip-pyinstaller`）の追加 |
| **変更** | `tests/test_build_script.py` | `build.py` の ISCC 探索ロジックおよびコマンドライン引数のテスト追加 |
| **変更** | `doc/executable_creation_guide.md` | インストーラー作成手順・Inno Setup 連携手順の追記 |
| **変更** | `README.md` | インストーラー版・ポータブル版の使い分け、自動更新・進捗バー機能の追記 |
| **新規** | `doc/releases/release_notes_v1.1.0.md` | GitHub Release `v1.1.0` 用の公式リリースノート案 |
| **更新** | `doc/plans/plan_20261111_installer_and_release.md` | 本計画書の完了チェックリスト |

---

## 4. 詳細設計・手順

### ステップ 1: Inno Setup 定義ファイル（`installer.iss`）の作成
プロジェクトルートに `installer.iss` を新規作成する。
- **基本定義**:
  - `#define MyAppName "PDF Image Extractor"`
  - `#define MyAppPublisher "Mitsuie"`
  - `#define MyAppURL "https://github.com/Mitsuie/pdf-image-extractor"`
  - `#define MyAppExeName "PDFImageExtractor.exe"`
  - `#ifndef MyAppVersion` でデフォルト `"1.1.0"` を設定（`ISCC.exe /DMyAppVersion=...` による動的オーバーライドを許容）
- **Setup セクション**:
  - `AppId={{E68A8D2A-94B5-4D6C-81F8-6A2CEB701D29}}`（固定UUID）
  - `AppName={#MyAppName}`
  - `AppVersion={#MyAppVersion}`
  - `DefaultDirName={autopf}\{#MyAppName}`（64bit/32bit自動解決）
  - `DefaultGroupName={#MyAppName}`
  - `OutputBaseFilename=PDFImageExtractor_Setup_v{#MyAppVersion}`
  - `OutputDir=dists`
  - `Compression=lzma2/ultra`
  - `SolidCompression=yes`
  - `PrivilegesRequired=lowest` および `PrivilegesRequiredOverridesAllowed=dialog`（一般ユーザー環境ではユーザーディレクトリにインストールでき、管理者権限があればProgram Filesにインストール可能なハイブリッド設定）
- **Languages セクション**:
  - `Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"`
  - `Name: "english"; MessagesFile: "compiler:Default.isl"`
- **Tasks / Icons セクション**:
  - スタートメニューへのショートカット自動登録
  - デスクトップアイコン作成タスク（`desktopicon`、デフォルトOFF）
- **Files セクション**:
  - `Source: "dists\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion`
- **Run セクション**:
  - インストール完了時の「アプリケーションを起動する」チェックボックス（`Flags: nowait postinstall skipifsilent`）

### ステップ 2: `build.py` への Inno Setup 連携拡張
`build.py` に以下の関数および CLI オプションを追加する：
1. **関数 `find_iscc_exe() -> Path | None`**:
   - `shutil.which("ISCC.exe")` または `shutil.which("iscc")`
   - `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
   - `C:\Program Files\Inno Setup 6\ISCC.exe`
   - 見つかった `Path` を返し、存在しなければ `None` を返す。
2. **関数 `build_installer(iscc_path: Path, iss_path: Path, version: str, output_dir: Path) -> Path`**:
   - `subprocess.run([str(iscc_path), f"/DMyAppVersion={version}", f"/O{output_dir}", str(iss_path)])` を実行。
   - 生成された `PDFImageExtractor_Setup_v{version}.exe` の存在を確認。
   - `generate_sha256_file()` を呼び出し、`PDFImageExtractor_Setup_v{version}.exe.sha256` を生成。
3. **引数パーサー（`parse_args`）の拡張**:
   - `--installer`: Inno Setup によるインストーラーをビルドする。
   - `--skip-pyinstaller`: PyInstaller による実行ファイルビルドをスキップし、既存の `dists/PDFImageExtractor.exe` を使ってインストーラーのみビルドする（開発時やテスト時の高速化用）。
4. **バージョン取得**:
   - `version.py` から `__version__` をインポートし、Inno Setup に渡す。

### ステップ 3: テストの追加・更新（`tests/test_build_script.py`）
1. `find_iscc_exe` のユニットテスト（実機環境またはモックを用いたテスト）。
2. `parse_args` に `--installer` や `--skip-pyinstaller` を渡した際の引数パーステスト。
3. `pytest` を実行し、全テスト（112件＋追加分）がグリーンであることを確認。

### ステップ 4: ビルドおよびインストーラー生成の動作確認
1. `python build.py --installer` を実行。
2. 以下の成果物が `dists/` 配下に生成されることを確認：
   - `dists/PDFImageExtractor.exe`
   - `dists/PDFImageExtractor.exe.sha256`
   - `dists/PDFImageExtractor_Setup_v1.1.0.exe`
   - `dists/PDFImageExtractor_Setup_v1.1.0.exe.sha256`
3. 生成されたインストーラー `PDFImageExtractor_Setup_v1.1.0.exe` のテスト起動確認（ウィザードが正常に開き、日本語表記・バージョン `1.1.0` が表示されること）。

### ステップ 5: ドキュメントの整備
1. **`doc/executable_creation_guide.md`**:
   - Inno Setup の概要とインストール方法の案内。
   - `python build.py --installer` によるインストーラー生成手順の追記。
   - 手動で Inno Setup GUI / CLI を叩く場合の補足。
2. **`README.md`**:
   - 起動方法に「インストーラー（推奨）」と「ポータブル版」の2種類の入手・実行手順を明記。
   - 主な特徴に「抽出進捗のプログレスバー表示と即時中断」「GitHub Releases 連携による自動アップデート」を追加。
3. **`doc/releases/release_notes_v1.1.0.md`**:
   - GitHub Release `v1.1.0` 用のリリースノート本文を作成。
   - ハイライト、新機能・改善点一覧、配布アセット一覧、チェックサム照合手順を記載。

---

## 5. やらないこと（触らない範囲）

- `version.py` のバージョン番号変更（`1.1.0` のまま維持）
- GitHub Release の本番発行（タグ打ち・`gh release create` の実行は、本PRが `main` にマージされた後に実施する）
- コア抽出ロジック（`extractor.py`）および GUI ウィンドウロジック（`app_window.py`）の変更
- `main` ブランチへの直接コミット

---

## 6. 完了条件

- [x] `installer.iss` が作成され、Inno Setup 6 でエラーなくコンパイルできること
- [x] `build.py` に `--installer` および `--skip-pyinstaller` が追加され、単一コマンドでインストーラーと `.sha256` まで生成できること
- [x] `tests/test_build_script.py` にテストが追加され、`pytest` がすべてパスすること
- [x] `dists/` に `PDFImageExtractor.exe`, `PDFImageExtractor.exe.sha256`, `PDFImageExtractor_Setup_v1.1.0.exe`, `PDFImageExtractor_Setup_v1.1.0.exe.sha256` が生成されること
- [x] `doc/executable_creation_guide.md` および `README.md` が最新の配布形態に更新されていること
- [x] `doc/releases/release_notes_v1.1.0.md` が作成されていること
- [x] 本計画書の完了チェックリストが更新されていること

---

## 7. 検証方法

1. `python -m pytest -v` を実行し、全テストの通過を確認する。
2. `python build.py --installer` を実行し、4つの成果物が正常に生成されることを確認する。
3. `Get-FileHash` でインストーラーおよび実行ファイルの SHA-256 を計算し、それぞれの `.sha256` ファイルの内容と完全一致することを確認する。
4. `git status` および `git diff --stat main...HEAD` を確認し、余計なファイル変更がないことを報告する。

---

## 8. 質問（実装側が詰まったら記入）

- （なし）

