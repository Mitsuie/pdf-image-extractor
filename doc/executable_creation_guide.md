# PDF画像抽出ツール 実行ファイル（.exe）作成・インストーラーパッケージングガイド

本ガイドでは、Pythonスクリプト（`main.py`）からWindows用のスタンドアロン実行ファイル（`.exe`）、Inno Setup によるインストーラー（`Setup.exe`）、および配布用パッケージを作成する方法について説明します。

---

## 1. ビルドの概要と使用するツール

本プロジェクトでは、実行ファイルの生成と配布パッケージングに以下のツール・スクリプトを使用します。

- **`PyInstaller`**: Python スクリプトとその依存ライブラリ（PyMuPDF など）を1つの実行ファイル（`.exe`）にパッケージ化するツールです。
- **`Inno Setup 6`**: Windows 向け標準インストーラー作成ツールです。スタートメニュー登録、デスクトップショートカット作成、アンインストーラーの同梱、一般ユーザー／管理者のハイブリッドインストールに対応した `PDFImageExtractor_Setup_v<version>.exe` を作成します。
- **`build.py`（ビルド自動化スクリプト）**: プロジェクトルートに配置された標準 Python スクリプトです。自動テスト（`pytest`）の実行、PyInstaller ビルド、Inno Setup によるインストーラー生成、および完全性照合用 **SHA-256 チェックサムファイル（`.sha256`）の自動生成**を一括して自動実行します。

> [!IMPORTANT]
> **SHA-256 チェックサムファイル（`.sha256`）の必要性**
> 本アプリケーションの自動アップデート機能（GitHub Releases 連携）では、ダウンロードした更新バイナリの完全性・改ざん検知のため、`.exe` と同名の `.sha256` ファイルが必須アセットとなります。
> `build.py` を使用することで、このチェックサムファイルが `sha256sum` 互換フォーマット（`<hash> *<filename>`）で自動生成されます。

---

## 2. 推奨ビルド手順（`build.py` による自動ビルド）

もっとも簡単かつ確実なビルド方法は、プロジェクトルートで `build.py` を実行することです。

### ① インストーラーと単体実行ファイルの両方を一括ビルド（推奨）
```powershell
python build.py --installer
```

このコマンド1つで以下の工程が自動的に連続実行されます：
1. **ビルド前テスト**: `pytest` による単体テストの自動実行（テスト失敗時はビルドを自動中断）
2. **中間生成物のクリーンアップ**: 以前の `build/` や `dist/` 一時ディレクトリを削除
3. **PyInstaller ビルド**: `PDFImageExtractor.spec` を元にスタンドアロン実行ファイル（ポータブル版）をビルド
4. **成果物配置**: `dists/PDFImageExtractor.exe` にコピー
5. **ポータブル版チェックサム生成**: `dists/PDFImageExtractor.exe.sha256` を自動生成
6. **Inno Setup インストーラービルド**: `installer.iss` を元に `dists/PDFImageExtractor_Setup_v<version>.exe` を生成
7. **インストーラー版チェックサム生成**: `dists/PDFImageExtractor_Setup_v<version>.exe.sha256` を自動生成
8. **事後クリーンアップ**: 一時作業フォルダ（`build/`）を安全に削除

### ② 単体実行ファイル（ポータブル版）のみビルド
```powershell
python build.py
```
`dists/PDFImageExtractor.exe` およびその `.sha256` のみを生成します。

### ③ インストーラーのみ高速ビルド（PyInstaller の再ビルドをスキップ）
```powershell
python build.py --skip-pyinstaller
```
すでに `dists/PDFImageExtractor.exe` がビルド済みの場合、PyInstaller の処理をスキップして Inno Setup インストーラーのみを短時間で再ビルドできます。

### 利用可能なオプション一覧
- **`--installer`**: Inno Setup によるインストーラー（`Setup.exe`）を生成します。
- **`--skip-pyinstaller`**: PyInstaller ビルドをスキップし、既存の実行ファイルを使用してインストーラーのみ生成します。
- **`--skip-tests`**: 事前自動テストの実行をスキップして即座にビルドを開始します。
- **`--output-dir <フォルダ名>`**: 成果物の出力先ディレクトリを変更します（デフォルト: `dists`）。
- **`--spec <ファイル名>`**: PyInstaller spec ファイルを指定します（デフォルト: `PDFImageExtractor.spec`）。
- **`--iss <ファイル名>`**: Inno Setup スクリプトを指定します（デフォルト: `installer.iss`）。

---

## 3. Inno Setup の環境準備

インストーラー（`Setup.exe`）の作成には、環境に **Inno Setup 6** がインストールされている必要があります。

1. **公式サイトからインストーラーをダウンロード**:  
   [Inno Setup 公式ダウンロードページ](https://jrsoftware.org/isdl.php) から最新版のインストーラー（例: `innosetup-6.x.x.exe`）をダウンロードしてインストールします。
2. **コンパイラの自動検出**:  
   `build.py` は以下の順序で Inno Setup コンパイラ（`ISCC.exe`）を自動探索します。
   - コマンドラインの `PATH` 環境変数（`ISCC.exe` / `iscc`）
   - `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`
   - `C:\Program Files\Inno Setup 6\ISCC.exe`

※ 標準の場所にインストールされていれば、特別な環境変数の設定は不要です。

---

## 4. 仮想環境でのビルド（推奨）

グローバルな Python 環境でビルドを行うと、PC にインストールされている無関係な外部パッケージ（PyTorch や OpenCV 等）を PyInstaller が検知・同梱してしまい、ファイルサイズが肥大化するおそれがあります（本ツールの spec ファイルでは主要な不要モジュールを除外設定済みですが、仮想環境の利用が最も安全です）。

### ① 仮想環境の作成と有効化
```powershell
# 仮想環境の作成 (.venv フォルダが未作成の場合)
python -m venv .venv

# 仮想環境の有効化 (PowerShell)
.venv\Scripts\Activate.ps1
```

### ② 依存ライブラリのインストール
```powershell
# pip の更新
python -m pip install --upgrade pip

# requirements.txt からアプリ依存ライブラリをインストール
pip install -r requirements.txt

# ビルド・テストツールのインストール
pip install pyinstaller pytest
```

### ③ ビルドスクリプトの実行
```powershell
python build.py --installer
```

---

## 5. 手動ビルド手順（参考）

何らかの理由で `build.py` を使わずに手動でビルドおよびインストーラー生成を行う場合の手順です。

### ① PyInstaller の手動実行
```powershell
pyinstaller PDFImageExtractor.spec --clean
```
※ ビルドが成功すると、`dist/PDFImageExtractor.exe` が生成されます。

### ② 手動での SHA-256 チェックサム計算
```powershell
$hash = (Get-FileHash dist\PDFImageExtractor.exe -Algorithm SHA256).Hash.ToLower()
"$hash *PDFImageExtractor.exe" | Out-File -Encoding utf8 dist\PDFImageExtractor.exe.sha256
```

### ③ 配布フォルダ（`dists/`）へのコピー
```powershell
Copy-Item dist\PDFImageExtractor.exe dists\
Copy-Item dist\PDFImageExtractor.exe.sha256 dists\
```

### ④ Inno Setup の手動実行
Inno Setup Compiler GUI で `installer.iss` を開いて「Compile」を押すか、以下の CLI コマンドを実行します：
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.1.0 /Odists installer.iss
```
生成されたインストーラーのチェックサムも同様に手動計算します：
```powershell
$instHash = (Get-FileHash dists\PDFImageExtractor_Setup_v1.1.0.exe -Algorithm SHA256).Hash.ToLower()
"$instHash *PDFImageExtractor_Setup_v1.1.0.exe" | Out-File -Encoding utf8 dists\PDFImageExtractor_Setup_v1.1.0.exe.sha256
```

---

## 6. ビルド後の成果物について

ビルドが完了すると、`dists/` フォルダ内に以下の4つのファイルが配置されます。

* **`dists/PDFImageExtractor_Setup_v1.1.0.exe`** : Inno Setup 製インストーラー本体です。一般ユーザーの利用に最も推奨されます。
* **`dists/PDFImageExtractor_Setup_v1.1.0.exe.sha256`** : インストーラーの完全性照合用チェックサムです。
* **`dists/PDFImageExtractor.exe`** : 単一ファイル化されたポータブル実行ファイルです。インストール不要で即座に起動できます（自動更新機能でも利用されます）。
* **`dists/PDFImageExtractor.exe.sha256`** : ポータブル版の完全性照合用チェックサムです。

---

## 7. 注意事項とトラブルシューティング

* **設定ファイル（`config.json`）について**:
  本アプリケーションでは出力先パス等の設定保存用に `config.json` を使用していますが、このファイルはアプリ初回起動時に自動生成されます（書き込み権限がない場合は `%APPDATA%\pdf-image-extractor` にフォールバックします）。手動で同梱・配布する必要はありません。
* **Windows Defender / SmartScreen によるセキュリティ警告**:
  コード署名（有料証明書）を行っていない実行ファイルであるため、初回起動時に「Windows によって PC が保護されました」等の警告が表示される場合があります。
  * **対応方法**: 画面内の「詳細情報」をクリックし、「実行」ボタンを押すことで通常通り起動します。
