# PDF画像抽出ツール 実行ファイル（.exe）作成・パッケージングガイド

本ガイドでは、Pythonスクリプト（`main.py`）からWindows用のスタンドアロン実行ファイル（`.exe`）および配布用パッケージを作成する方法について説明します。

---

## 1. ビルドの概要と使用するツール

本プロジェクトでは、実行ファイルの生成と配布パッケージングに以下のツール・スクリプトを使用します。

- **`PyInstaller`**: Python スクリプトとその依存ライブラリ（PyMuPDF など）を1つの実行ファイル（`.exe`）にパッケージ化するツールです。
- **`build.py`（ビルド自動化スクリプト）**: プロジェクトルートに配置された標準 Python スクリプトです。自動テスト（`pytest`）の実行、PyInstaller ビルド、リリース用 **SHA-256 チェックサムファイル（`.sha256`）の自動生成**、および配布用フォルダ（`dists/`）への成果物配置を一括して自動実行します。

> [!IMPORTANT]
> **SHA-256 チェックサムファイル（`.sha256`）の必要性**
> 本アプリケーションの自動アップデート機能（GitHub Releases 連携）では、ダウンロードした更新バイナリの完全性・改ざん検知のため、`.exe` と同名の `.sha256` ファイルが必須アセットとなります。
> `build.py` を使用することで、このチェックサムファイルが `sha256sum` 互換フォーマット（`<hash> *<filename>`）で自動生成されます。

---

## 2. 推奨ビルド手順（`build.py` による自動ビルド）

もっとも簡単かつ確実なビルド方法は、プロジェクトルートで `build.py` を実行することです。

### 基本コマンド
```powershell
python build.py
```

このコマンド1つで以下の工程が自動的に連続実行されます：
1. **ビルド前テスト**: `pytest` による単体テストの自動実行（テスト失敗時はビルドを自動中断）
2. **中間生成物のクリーンアップ**: 以前の `build/` や `dist/` 一時ディレクトリを削除
3. **PyInstaller ビルド**: `PDFImageExtractor.spec` を元にスタンドアロン実行ファイルをビルド
4. **成果物配置**: `dists/PDFImageExtractor.exe` にコピー
5. **チェックサム自動生成**: `dists/PDFImageExtractor.exe.sha256` を自動生成
6. **事後クリーンアップ**: 一時作業フォルダ（`build/`）を安全に削除

### 利用可能なオプション
- **`--skip-tests`**: 事前自動テストの実行をスキップして即座にビルドを開始します。
  ```powershell
  python build.py --skip-tests
  ```
- **`--output-dir <フォルダ名>`**: 成果物の出力先ディレクトリを変更します（デフォルト: `dists`）。
  ```powershell
  python build.py --output-dir release
  ```

---

## 3. 仮想環境でのビルド（推奨）

グローバルな Python 環境でビルドを行うと、PC にインストールされている無関係な外部パッケージ（PyTorch や OpenCV 等）を PyInstaller が検知・同梱してしまい、ファイルサイズが数十〜数百MBに肥大化するおそれがあります（本ツールの spec ファイルでは主要な不要モジュールを除外設定済みですが、仮想環境の利用が最も安全です）。

最小限の依存関係のみを持つ**仮想環境（venv）**を作成してビルドすることを推奨します。

### ① 仮想環境の作成と有効化
```powershell
# 仮想環境の作成 (.venv フォルダが未作成の場合)
python -m venv .venv

# 仮想環境の有効化 (PowerShell)
.venv\Scripts\Activate.ps1
```
> [!NOTE]
> 有効化されると、ターミナルのプロンプト先頭に `(.venv)` と表示されます。

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
python build.py
```

---

## 4. 手動ビルド手順（参考）

何らかの理由で `build.py` を使わずに手動でビルドおよびチェックサム生成を行う場合の手順です。

### ① PyInstaller の手動実行
プロジェクトルートで `PDFImageExtractor.spec` を指定して実行します。
```powershell
pyinstaller PDFImageExtractor.spec --clean
```
※ ビルドが成功すると、`dist/PDFImageExtractor.exe` が生成されます。

### ② 手動での SHA-256 チェックサム計算
PowerShell でチェックサムを計算し、`sha256sum` 互換形式で保存します。
```powershell
$hash = (Get-FileHash dist\PDFImageExtractor.exe -Algorithm SHA256).Hash.ToLower()
"$hash *PDFImageExtractor.exe" | Out-File -Encoding utf8 dist\PDFImageExtractor.exe.sha256
```

### ③ 配布フォルダ（`dists/`）へのコピー
```powershell
Copy-Item dist\PDFImageExtractor.exe dists\
Copy-Item dist\PDFImageExtractor.exe.sha256 dists\
```

---

## 5. ビルド後の成果物について

ビルドが完了すると、`dists/` フォルダ内に以下のファイルが配置されます。

* **`dists/PDFImageExtractor.exe`** : 単一ファイル化された実行ファイル本体です。Python 未導入の環境でもそのまま起動可能です。
* **`dists/PDFImageExtractor.exe.sha256`** : GitHub Releases のアセットとして `.exe` と一緒に公開するチェックサムファイルです。
* **`PDFImageExtractor.spec`** : PyInstaller の構成ファイルです。エントリーポイント（`main.py`）や除外モジュール、ウィンドウ設定などが定義されています。

---

## 6. 注意事項とトラブルシューティング

* **設定ファイル（`config.json`）について**:
  本アプリケーションでは出力先パス等の設定保存用に `config.json` を使用していますが、このファイルはアプリ初回起動時に自動生成されます。手動で同梱・配布する必要はありません。
* **Windows Defender / SmartScreen によるセキュリティ警告**:
  コード署名（有料証明書）を行っていない野良 exe であるため、初回起動時に「Windows によって PC が保護されました」等の警告が表示される場合があります。
  * **対応方法**: 画面内の「詳細情報」をクリックし、「実行」ボタンを押すことで通常通り起動します。
