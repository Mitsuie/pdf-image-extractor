# 計画書: Issue #8 extractor.py のコード重複解消、定数化、および型ヒントの導入

- 対象 Issue: [#8](https://github.com/Mitsuie/pdf-image-extractor/issues/8)
- 作業ブランチ: `agy/issue-8-extractor-refactor`（`main` の最新から作成）
- 前提となる Issue: **#7 が `main` にマージ済み**であること（`tests/test_extractor.py` が `main` にあること）。マージされていない場合は、作業を始めずに報告する。

## 目的

`extractor.py` の**外から見た振る舞い（出力されるファイル名・ファイルの内容・戻り値）を変えずに**、内部の構造を整理する。具体的には、重複している保存処理を 1 つにまとめ、マジックナンバーを定数にし、データ構造を `dataclass` にし、型ヒントを付ける。

## 背景・前提

- 現状の問題点（[extractor.py](../../extractor.py)）
  - 197〜201 行目と 213〜217 行目: ファイル名の組み立てとパスの結合が重複している。
  - 122〜143 行目: サニタイズとパス長の計算がインラインで書かれていて、`200`・`35`・`5` が直接書かれている。
  - 59 行目と 65 行目: キャプションとの距離の判定に、`80` が直接書かれている。
  - 207〜209 行目: `except Exception: pass` で、フォールバックした理由が残らない。
  - 34〜38 行目と 75〜80 行目: `captions` と `mapped_images` が `dict` になっている。
- **既存のバグ（本 Issue で直す）**: 透過マスクがある画像（`smask > 0`）では、191 行目で `image_ext = "png"` に書き換えた後に Pixmap の処理が失敗すると、フォールバックのバイナリ保存で、元の画像のバイト列（例: JPEG）が `.png` という拡張子で保存されてしまう。リファクタリング後は、**フォールバック時は元の拡張子（`base_image["ext"]`）を使う**。サンプル PDF ではフォールバックが起きないため、回帰テストの結果は変わらない。
- 外部から使われている関数のシグネチャと戻り値は、変更しない。
  - `parse_figure_number(text) -> tuple[int, int] | None`
  - `get_sorted_images_on_page(page, image_list) -> list[tuple[tuple, str | None]]`（`(img, fig_num_str)` のリスト）
  - `extract_images_from_pdf(pdf_path, output_dir) -> int`
  - `extract_images_from_folder(input_dir, output_dir, log_callback=None) -> tuple[int, int]`
- `app.py` は、`extract_images_from_pdf` と `extract_images_from_folder` だけを import している。

## 変更対象（ファイル/フォルダ）

- 変更: `extractor.py`
- 変更: `tests/test_extractor.py`
- 新規: `doc/plans/plan_20261109_issue08_extractor_refactor.md`（本計画書。作成済み）

## 手順

1. **リファクタリングの前に**、出力ファイルの内容が変わらないことを確認するテストを追加して、コミットする（コミットメッセージの例: `test: サンプルPDF抽出結果のゴールデンハッシュを追加`）。
   - `extractor.py` を変更していない状態で、サンプル PDF を抽出し、5 つの出力ファイルそれぞれの SHA-256 を計算する。
   - `tests/test_extractor.py` に、`EXPECTED_SAMPLE_SHA256 = {"pdf_image_test_page1_1.jpeg": "...", ...}` という定数と、それと比較するテスト `test_sample_output_sha256_unchanged` を追加する。
   - 定数の上に、「PyMuPDF のバージョンによって PNG のバイト列が変わることがある。PyMuPDF を更新して失敗した場合は、`extractor.py` に変更がないことを確認した上で、値を作り直す」というコメントと、ハッシュを作ったときの PyMuPDF のバージョンを書いておく。
   - `python -m pytest -q` で、全件が成功することを確認する。
2. `extractor.py` の先頭部分を整理する。
   - `from __future__ import annotations` を追加する。
   - `import logging` を追加し、`logger = logging.getLogger(__name__)` を定義する（`basicConfig` やハンドラーの設定は**しない**）。
   - 次の定数を定義する（それぞれに、日本語で 1 行のコメントを付ける）。
     - `MAX_PATH_LENGTH = 200`
     - `PATH_BUFFER_LENGTH = 35`
     - `MIN_PREFIX_LENGTH = 5`
     - `CAPTION_DISTANCE_THRESHOLD = 80.0`
     - `INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')`
     - `FIGURE_NUMBER_PATTERN = re.compile(r'(?:図|Fig(?:ure)?\.?|画像|写真|Photo)\s*(\d+)(?:[-.](\d+))?', re.IGNORECASE)`
   - 型の別名 `FigureNumber = tuple[int, int]` を定義する。
3. `dataclass` を導入する。
   - `@dataclass(frozen=True) class Caption`: `rect: fitz.Rect`、`text: str`、`fig_num: FigureNumber`
   - `@dataclass class PageImage`: `img: tuple`、`rect: fitz.Rect`、`has_rect: bool`、`fig_num: FigureNumber | None`
   - `get_sorted_images_on_page` の中で使っている `dict` を、これらに置き換える。並べ替えの規則は変えない。
4. 次の関数を新しく作り、`extract_images_from_pdf` から使う。
   - `sanitize_filename(name: str) -> str`: 禁止文字を `_` に置き換えるだけにする（両端の除去はしない。今の `safe_pdf_name` と同じ結果にする）。
   - `build_folder_name(safe_name: str) -> str`: `safe_name.strip(". ")` を返す。
   - `compute_file_prefix(safe_name: str, abs_target_dir: str) -> str`: 122〜143 行目の計算を、定数を使って書き直したもの。
   - `format_figure_number(fig_num: FigureNumber | None) -> str | None`: `(1, 2)`→`"1-2"`、`(3, 0)`→`"3"`、`None`→`None`（96〜101 行目の処理を移動する）。
   - `resolve_suffix(base_suffix: str, suffix_counts: dict[str, int]) -> str`: 173〜179 行目の連番処理。1 回目は `base_suffix`、2 回目以降は `f"{base_suffix}_{n}"`（n は 1 から始まる）を返し、`suffix_counts` を更新する。
   - `generate_image_filename(prefix: str, page_number: int, suffix: str, ext: str) -> str`: `prefix` が空なら `f"page{page_number}_{suffix}.{ext}"`、空でなければ `f"{prefix}_page{page_number}_{suffix}.{ext}"`（`page_number` は 1 から始まる）。
   - `_build_pixmap(doc, xref: int, smask: int) -> fitz.Pixmap`: 185〜195 行目の Pixmap 作成処理（マスクの結合と RGB への変換）。
   - `_save_image(doc, img, base_image, page_number, suffix, prefix, target_dir) -> None`: 画像 1 枚を保存する処理をまとめたもの。
     - `smask > 0` または拡張子が `png` の場合は、`_build_pixmap` → 拡張子を決める（`smask > 0` なら `png`、そうでなければ元の拡張子）→ `generate_image_filename` → `pix.save`。
     - 上の処理で例外が出た場合は、`logger.warning("Pixmapでの保存に失敗したため、元データのまま保存します (page=%d, xref=%d): %s", page_number, xref, e)` を出力して、バイナリ保存に進む。
     - バイナリ保存では、**元の拡張子**（`base_image["ext"]`）で `generate_image_filename` を呼んで書き込む。
     - ファイル名を組み立てる処理は、`generate_image_filename` の 1 か所だけにする。
5. すべての関数に型ヒントを付け、docstring を、`Args` と `Returns` を含む形で整える（既存の docstring の説明は残す）。`fitz.Page`、`fitz.Document` などの型は、そのまま注釈に使ってよい。
6. `tests/test_extractor.py` に、次の単体テストを追加する。
   - `sanitize_filename`: 9 種類の禁止文字が、それぞれ `_` になる。禁止文字がない文字列（日本語を含む）は変わらない。
   - `build_folder_name`: `"  test. "`→`"test"`。
   - `compute_file_prefix`（`abs_target_dir` に、長さを指定した文字列を渡す）:
     - 上限ちょうど（`len(safe_name) == max_len`）→ そのまま
     - 上限を 1 文字超える → 短縮される
     - 短縮した結果の末尾が `.` や空白 → 除かれる
     - `max_len == 5` → 短縮される（空にならない）
     - `max_len == 4` → `""`
   - `format_figure_number`、`resolve_suffix`（`fig1`→`fig1`、`fig1_1`、`fig1_2` の順になる）、`generate_image_filename`（接頭辞あり・なし）。
   - フォールバック: `monkeypatch` で `extractor._build_pixmap` を、常に例外を出す関数に差し替えてサンプル PDF を抽出する。件数は 5 で、PNG だった画像は元の拡張子で保存され、`caplog` に WARNING が記録される。
     - 実装前に、`doc.extract_image(xref)["ext"]` の値を確認して、期待されるファイル名をテストに書く。
7. `python -m pytest -q` で、全件（手順 1 のハッシュのテストを含む）が成功することを確認する。

## やらないこと（触らない範囲）

- 出力されるファイル名の規則、並べ替えの規則、キャプションの判定条件の変更（上記のバグ修正を除く）
- 進捗コールバックや中断機能の追加（#11 で行う）
- `app.py`、`README.md`、ドキュメントの変更
- `import fitz` を `import pymupdf` に変更すること
- #7 で作ったテストの、期待値の変更（テストの追加とヘルパーの整理だけ行う）
- `logging.basicConfig` の呼び出し（ログの設定は #10 の `main.py` で行う）
- 他の計画書のコミット
- `main` ブランチへの直接のコミット

## 完了条件

- [x] 手順 1 のゴールデンハッシュのテストが、リファクタリング前のコミットで追加されている
- [x] 定数（`MAX_PATH_LENGTH`、`PATH_BUFFER_LENGTH`、`MIN_PREFIX_LENGTH`、`CAPTION_DISTANCE_THRESHOLD`）が定義され、`200`・`35`・`80` が直接書かれていない
- [x] `sanitize_filename`、`generate_image_filename` などの関数があり、ファイル名を組み立てる処理が 1 か所にまとまっている
- [x] `except Exception: pass` がなくなり、フォールバック時に `logging` の WARNING が出る
- [x] `Caption`、`PageImage` の `dataclass` が使われている
- [x] すべての関数に型ヒントがある
- [x] `python -m pytest -q` で全件が成功する（#7 のテストとゴールデンハッシュのテストを含む）
- [x] この計画書の「完了条件」のチェックリストが更新されている

## 検証方法

- `python -m pytest -q` の最終行を報告する。
- `git diff --stat main...HEAD` を報告する。
- `Select-String -Path extractor.py -Pattern "\b(200|35|80)\b"` の結果（定数定義の行以外にないこと）を報告する。

## 質問（実装側が詰まったら記入）

- （なし）

