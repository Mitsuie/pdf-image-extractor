# 計画書: Issue #7 単体テスト環境（pytest）の構築と主要ロジックのテスト実装

- 対象 Issue: [#7](https://github.com/Mitsuie/pdf-image-extractor/issues/7)
- 作業ブランチ: `agy/issue-7-pytest`（`main` の最新から作成）
- 前提となる Issue: なし（最初に着手する）

## 目的

`pytest` を導入し、**現在の `extractor.py` の振る舞いをそのまま記録する**テスト（特性テスト）を作る。以降のリファクタリング（#8〜#13）で、振る舞いが変わっていないことを自動で確認できるようにする。

## 背景・前提

- Issue 本文の「Issue 1〜7」は、GitHub 上の **#7〜#13** に対応する（Issue 1 = #7, Issue 2 = #8, Issue 3 = #9, Issue 4 = #10, Issue 5 = #11, Issue 6 = #12, Issue 7 = #13）。
- **本 Issue では、`extractor.py` と `app.py` を一切変更しない。** テストは、今のコードのまま通るように書く。
- 既存の `.venv` は壊れている（`.venv/pyvenv.cfg` が存在しない `C:\Python314` を指している）。開発機には `py -3.13`（PyMuPDF 2.1 インストール済み）がある。手順 1 で `.venv` を作り直す。
- サンプル PDF `example_files/pdf_image_test.pdf` から抽出すると、次の 5 ファイルが `<出力先>/pdf_image_test/` に作られる（`example_files/example_output/pdf_image_test/` と同じ名前）。
  - `pdf_image_test_page1_1.jpeg`
  - `pdf_image_test_page1_2.png`
  - `pdf_image_test_page1_3.png`
  - `pdf_image_test_page2_1.jpeg`
  - `pdf_image_test_page2_2.png`
- ファイル名のサニタイズとパス長の短縮は、`extract_images_from_pdf`（[extractor.py](../../extractor.py) 119〜143 行目）の中に直接書かれていて、独立した関数がない。そのため、**`extract_images_from_pdf` を呼んで、出力されたフォルダ名・ファイル名を確認する**形でテストする。
  - 短縮の計算式: `max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35`
    - `abs_target_dir` = `os.path.abspath(os.path.join(output_dir, folder_name))`
    - `folder_name` = サニタイズ後の PDF 名から、両端の `.` と空白を除いたもの（**フォルダ名は短縮されない**）
  - `max_pdf_name_len < 5` → ファイル名の接頭辞は空（`page1_1.jpeg` の形）
  - `len(safe_pdf_name) > max_pdf_name_len` → `safe_pdf_name[:max_pdf_name_len].strip(". ")` を接頭辞にする
  - それ以外 → `safe_pdf_name` をそのまま接頭辞にする
- Windows では、禁止文字（`<>:"/\|?*`）を含むファイルを実際には作れない。そのため、禁止文字のテストでは、`monkeypatch` で `os.path.basename` を差し替える（手順 4 を参照）。
- `import fitz` で PyMuPDF の `FutureWarning` が出るが、本 Issue では対応しない。

## 変更対象（ファイル/フォルダ）

- 新規: `requirements-dev.txt`
- 新規: `tests/__init__.py`（空ファイル）
- 新規: `tests/conftest.py`
- 新規: `tests/test_extractor.py`
- 新規: `doc/plans/plan_20261109_issue07_pytest.md`（本計画書。作成済み）

## 手順

1. 開発環境を作り直す（`.venv` は Git 管理外）。
   ```powershell
   py -3.13 -m venv --clear .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```
   （`requirements-dev.txt` は手順 2 で作る。この後のコマンドは、すべて `.\.venv\Scripts\python.exe` で実行する。）
2. `requirements-dev.txt` を作る。
   ```text
   -r requirements.txt
   pytest>=8.0
   ```
3. `tests/__init__.py`（空）と `tests/conftest.py` を作る。`conftest.py` には、次のフィクスチャを定義する。
   - `repo_root`: リポジトリ直下の `Path`（`Path(__file__).resolve().parent.parent`）
   - `sample_pdf`: `repo_root / "example_files" / "pdf_image_test.pdf"`
   - `copy_sample_pdf(tmp_path)`: サンプル PDF を、指定したディレクトリ・ファイル名にコピーして、その `Path` を返すファクトリー関数
   - `tests/__init__.py` があり、`python -m pytest` をリポジトリ直下で実行すれば、`import extractor` ができる。できない場合は、`conftest.py` で `sys.path` にリポジトリ直下を追加する。
4. `tests/test_extractor.py` を作り、次のテストを書く。
   - **`parse_figure_number`**（`pytest.mark.parametrize` を使う）
     - マッチする: `"図1"`→`(1, 0)`、`"図 1-2"`→`(1, 2)`、`"Fig 3"`→`(3, 0)`、`"Fig. 3.4"`→`(3, 4)`、`"Fig.3"`→`(3, 0)`、`"Figure 10"`→`(10, 0)`、`"fig 7"`→`(7, 0)`（大文字・小文字を区別しない）、`"写真2"`→`(2, 0)`、`"Photo 4"`→`(4, 0)`、`"画像5"`→`(5, 0)`、`"図1-2: サンプル"`→`(1, 2)`
     - マッチしない（`None`）: `"図面を参照"`、`"見出し文"`、`"本文..."`、`""`
   - **単一 PDF の回帰テスト**
     - サンプル PDF を `tmp_path` にコピーして `extract_images_from_pdf(pdf, out)` を実行すると、戻り値が `5` で、`out/pdf_image_test/` 内のファイル名一覧（ソート済み）が、上記の 5 件と一致する。
     - 存在しない PDF パスを渡すと `FileNotFoundError` になる。
   - **フォルダ一括の回帰テスト**
     - 入力フォルダに、サンプル PDF のコピー 2 つ（`a.pdf` と、拡張子が大文字の `b.PDF`）と、`memo.txt` を置く。`extract_images_from_folder(in, out, log_callback=list.append)` の戻り値が `(2, 10)` で、ログに `処理中: a.pdf ...` などのメッセージが記録される。
     - 空のフォルダを渡すと `(0, 0)` を返し、ログに `入力フォルダ内にPDFファイルが見つかりませんでした。` が記録される。
     - 存在しないフォルダを渡すと `FileNotFoundError` になる。
     - 中身が壊れた PDF（`broken.pdf`、中身は `b"not a pdf"`）と正常な PDF を置くと、戻り値は `(1, 5)` で、ログに `エラー: broken.pdf` を含む行がある。（PyMuPDF が壊れたファイルで例外を出さない場合は、このテストを書かずに「質問」欄に記入する。）
   - **ファイル名のサニタイズ**
     - `monkeypatch` で `extractor.os.path.basename` を、「引数がコピーした PDF のパスと一致するときだけ `'a<b>c:d"e|f?g*h.pdf'` を返し、それ以外のときは元の関数に処理を任せる」ラッパーに差し替える。実行後、出力フォルダ `out/a_b_c_d_e_f_g_h/` ができ、その中のファイル名が `a_b_c_d_e_f_g_h_page1_1.jpeg` などで始まる。
     - 同じ方法で `'  test. .pdf'` を返すようにすると、出力フォルダ名が `test` になる（両端の `.` と空白が除かれる）。
   - **パス長の短縮**（`tmp_path` の長さは環境によって変わるため、PDF 名の長さを、テストの中で計算して決める）
     - 期待値を計算するヘルパー関数 `expected_prefix(safe_name, output_dir)` を、テストファイルの中に作る（上記の計算式を、そのまま書く）。
     - 短縮なし: サンプル PDF の名前のまま → 接頭辞は `pdf_image_test`。
     - 短縮あり: `5 <= max_pdf_name_len < len(name)` になる長さの名前（`"a" * N`）を使う。ファイル名の接頭辞が `expected_prefix(...)` と一致する。また、出力されたすべてのファイルについて、`len(os.path.abspath(path)) <= 200` である。
     - 接頭辞なし: `max_pdf_name_len < 5` になる長さの名前を使う。すべてのファイル名が `page` で始まる。
     - どのケースでも、Windows のパス長上限（260 文字）を超えないことを、テストの最初に `assert` で確認する。条件を満たす `N` が作れない環境の場合は、`pytest.skip` する。
5. テストを実行して、全件が成功することを確認する。
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```

## やらないこと（触らない範囲）

- `extractor.py`、`app.py` の変更（バグに気づいても直さず、「質問」欄に記入する）
- `pytest.ini`、`pyproject.toml`、Ruff、mypy、CI（GitHub Actions）の追加
- `import fitz` を `import pymupdf` に変更すること
- `example_files/` 内のファイルの変更
- GUI のテスト
- 他の計画書（`doc/plans/` 内の、本計画書以外のファイル）のコミット
- `main` ブランチへの直接のコミット

## 完了条件

- [x] `requirements-dev.txt`、`tests/__init__.py`、`tests/conftest.py`、`tests/test_extractor.py` が追加されている
- [x] `.\.venv\Scripts\python.exe -m pytest -q` で全件が成功する
- [x] `parse_figure_number` の、マッチするケースとマッチしないケースが網羅されている
- [x] 単一 PDF・フォルダ一括の抽出件数とファイル名の回帰テストがある
- [x] サニタイズ（禁止文字、両端の `.` と空白）とパス長の短縮（短縮なし・短縮あり・接頭辞なし）のテストがある
- [x] `git diff --stat main...HEAD` に、`extractor.py` と `app.py` が含まれていない
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `.\.venv\Scripts\python.exe -m pytest -q` の最終行を報告する。
- `git diff --stat main...HEAD` を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

