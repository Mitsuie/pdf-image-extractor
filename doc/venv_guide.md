# 仮想環境（venv）の作成・利用ガイド

このワークスペース（`pdf-image-extractor`）でPythonの仮想環境を作成し、有効化（アクティベート）して開発を行うための手順書です。

---

## 1. 仮想環境（.venv）の作成方法

ワークスペースのルートディレクトリで以下のコマンドを実行し、仮想環境を作成します。通常、仮想環境フォルダの名前は `.venv` とします。

### Windows (PowerShell / コマンドプロンプト)
```powershell
python -m venv .venv
```

※ Pythonのバージョンが複数インストールされている場合は、使用したいバージョンを指定して実行してください（例：`py -3.10 -m venv .venv` など）。

---

## 2. 仮想環境への入り方（アクティベート）

作成した仮想環境を有効化することで、その環境内にパッケージをインストールしたり、プログラムを実行したりできるようになります。

ご使用のシェル（端末）に合わせて、以下のコマンドを実行してください。

### ① Windows PowerShell（推奨）
```powershell
.venv\Scripts\Activate.ps1
```

> [!IMPORTANT]
> **PowerShellでスクリプトの実行エラーが発生する場合**
> 「このシステムではスクリプトの実行が禁止されているため、ファイル...を読み込むことができません」というエラーが表示された場合は、現在起動しているPowerShellプロセスのみ一時的に実行を許可するために、以下のコマンドを実行した後に再度アクティベートを行ってください。
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
> ```

### ② Windows コマンドプロンプト（cmd）
```cmd
.venv\Scripts\activate.bat
```

### ③ macOS / Linux（参考）
```bash
source .venv/bin/activate
```

---

## 3. 依存ライブラリのインストール

仮想環境に入った（アクティベートした）状態で、以下のコマンドを実行して必要な外部パッケージ（`PyMuPDF` など）を一括インストールします。

```powershell
pip install -r requirements.txt
```

---

## 4. 仮想環境の確認

仮想環境が正しく有効化されている場合、ターミナルのプロンプトの先頭に `(.venv)` と表示されます。
また、以下のコマンドを実行して、環境内のPythonパスが仮想環境内のものを指しているか確認できます。

### Windows PowerShell
```powershell
Get-Command python | Select-Object Source
# 出力結果が `...pdf-image-extractor\.venv\Scripts\python.exe` になっていることを確認
```

### Windows コマンドプロンプト
```cmd
where python
# リストの一番上が `...pdf-image-extractor\.venv\Scripts\python.exe` になっていることを確認
```

---

## 5. 仮想環境の抜け方（デアクティベート）

仮想環境での作業を終了し、通常のシステム環境に戻るには以下のコマンドを実行します。

```powershell
deactivate
```
