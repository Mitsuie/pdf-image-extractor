import hashlib
import logging
import os
from pathlib import Path
import pytest
import extractor
from extractor import (
    build_folder_name,
    compute_file_prefix,
    extract_images_from_folder,
    extract_images_from_pdf,
    format_figure_number,
    generate_image_filename,
    parse_figure_number,
    resolve_suffix,
    sanitize_filename,
)

EXPECTED_SAMPLE_FILES = [
    "pdf_image_test_page1_1.jpeg",
    "pdf_image_test_page1_2.png",
    "pdf_image_test_page1_3.png",
    "pdf_image_test_page2_1.jpeg",
    "pdf_image_test_page2_2.png",
]

# PyMuPDF のバージョンによって PNG のバイト列が変わることがある。
# PyMuPDF を更新して失敗した場合は、extractor.py に変更がないことを確認した上で、値を作り直す。
# 作成時の PyMuPDF バージョン: 2.1 (MuPDF 1.28.6)
EXPECTED_SAMPLE_SHA256: dict[str, str] = {
    "pdf_image_test_page1_1.jpeg": "acabeed32a4a5cac1fc080f3ba1a55d4ece299118d1be62ff3d56a1cef2ab16e",
    "pdf_image_test_page1_2.png": "ef03396bd5cc447acc937370ddacd9d368cdc98747286138ffd21ea74db9cada",
    "pdf_image_test_page1_3.png": "38d8faa71ca569a41b3eca7dacae0fffe4a74b62a4b857b872b7f95a4e786cbb",
    "pdf_image_test_page2_1.jpeg": "d6d4f8d1c6ab87c73db03566f28510c22d585177fecd778915acab2ba9e50a6a",
    "pdf_image_test_page2_2.png": "4117fef00827e206b4fc17ec3115772222905130e9306ac1a0343b03bd7fb5a3",
}


def expected_prefix(safe_name: str, output_dir: str | Path) -> str:
    folder_name = safe_name.strip(". ")
    abs_target_dir = os.path.abspath(os.path.join(output_dir, folder_name))
    max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35
    if max_pdf_name_len < 5:
        return ""
    elif len(safe_name) > max_pdf_name_len:
        return safe_name[:max_pdf_name_len].strip(". ")
    else:
        return safe_name


# ---------------------------------------------------------------------------
# parse_figure_number のテスト
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("図1", (1, 0)),
        ("図 1-2", (1, 2)),
        ("Fig 3", (3, 0)),
        ("Fig. 3.4", (3, 4)),
        ("Fig.3", (3, 0)),
        ("Figure 10", (10, 0)),
        ("fig 7", (7, 0)),
        ("写真2", (2, 0)),
        ("Photo 4", (4, 0)),
        ("画像5", (5, 0)),
        ("図1-2: サンプル", (1, 2)),
        ("図面を参照", None),
        ("見出し文", None),
        ("本文...", None),
        ("", None),
    ],
)
def test_parse_figure_number(text: str, expected: tuple[int, int] | None):
    assert parse_figure_number(text) == expected


# ---------------------------------------------------------------------------
# 単一 PDF の回帰テスト
# ---------------------------------------------------------------------------


def test_extract_images_from_pdf_success(tmp_path: Path, copy_sample_pdf):
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))

    assert count == 5
    target_dir = output_dir / "pdf_image_test"
    assert target_dir.is_dir()
    files = sorted(f.name for f in target_dir.iterdir() if f.is_file())
    assert files == EXPECTED_SAMPLE_FILES


def test_sample_output_sha256_unchanged(tmp_path: Path, copy_sample_pdf):
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == len(EXPECTED_SAMPLE_SHA256)

    target_dir = output_dir / "pdf_image_test"
    assert target_dir.is_dir()

    actual_hashes = {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest()
        for f in target_dir.iterdir()
        if f.is_file()
    }
    assert actual_hashes == EXPECTED_SAMPLE_SHA256


def test_extract_images_from_pdf_not_found(tmp_path: Path):
    non_existent = tmp_path / "not_found.pdf"
    output_dir = tmp_path / "output"
    with pytest.raises(FileNotFoundError):
        extract_images_from_pdf(str(non_existent), str(output_dir))


# ---------------------------------------------------------------------------
# フォルダ一括の回帰テスト
# ---------------------------------------------------------------------------


def test_extract_images_from_folder_success(tmp_path: Path, copy_sample_pdf):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    copy_sample_pdf(input_dir, "a.pdf")
    copy_sample_pdf(input_dir, "b.PDF")
    (input_dir / "memo.txt").write_text("memo", encoding="utf-8")

    logs: list[str] = []
    processed_files, total_extracted = extract_images_from_folder(
        str(input_dir), str(output_dir), log_callback=logs.append
    )

    assert (processed_files, total_extracted) == (2, 10)
    assert any("処理中: a.pdf" in log for log in logs)
    assert any("処理中: b.PDF" in log for log in logs)


def test_extract_images_from_folder_empty(tmp_path: Path):
    input_dir = tmp_path / "empty_input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"

    logs: list[str] = []
    result = extract_images_from_folder(
        str(input_dir), str(output_dir), log_callback=logs.append
    )
    assert result == (0, 0)
    assert "入力フォルダ内にPDFファイルが見つかりませんでした。" in logs


def test_extract_images_from_folder_not_found(tmp_path: Path):
    input_dir = tmp_path / "non_existent_input"
    output_dir = tmp_path / "output"
    with pytest.raises(FileNotFoundError):
        extract_images_from_folder(str(input_dir), str(output_dir))


def test_extract_images_from_folder_with_broken_pdf(tmp_path: Path, copy_sample_pdf):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"

    copy_sample_pdf(input_dir, "valid.pdf")
    broken_pdf = input_dir / "broken.pdf"
    broken_pdf.write_bytes(b"not a pdf")

    logs: list[str] = []
    processed_files, total_extracted = extract_images_from_folder(
        str(input_dir), str(output_dir), log_callback=logs.append
    )

    assert (processed_files, total_extracted) == (1, 5)
    assert any("エラー: broken.pdf" in log for log in logs)


# ---------------------------------------------------------------------------
# ファイル名のサニタイズ
# ---------------------------------------------------------------------------


def test_sanitize_forbidden_characters(tmp_path: Path, copy_sample_pdf, monkeypatch):
    pdf_path = copy_sample_pdf(tmp_path, "normal.pdf")
    output_dir = tmp_path / "output"

    real_basename = os.path.basename

    def fake_basename(path: str) -> str:
        if os.path.abspath(path) == os.path.abspath(pdf_path):
            return 'a<b>c:d"e|f?g*h.pdf'
        return real_basename(path)

    monkeypatch.setattr(extractor.os.path, "basename", fake_basename)

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5

    target_dir = output_dir / "a_b_c_d_e_f_g_h"
    assert target_dir.is_dir()
    files = sorted(f.name for f in target_dir.iterdir() if f.is_file())
    assert len(files) == 5
    for filename in files:
        assert filename.startswith("a_b_c_d_e_f_g_h_")


def test_sanitize_strip_dots_and_spaces(tmp_path: Path, copy_sample_pdf, monkeypatch):
    pdf_path = copy_sample_pdf(tmp_path, "normal.pdf")
    output_dir = tmp_path / "output"

    real_basename = os.path.basename

    def fake_basename(path: str) -> str:
        if os.path.abspath(path) == os.path.abspath(pdf_path):
            return "  test. .pdf"
        return real_basename(path)

    monkeypatch.setattr(extractor.os.path, "basename", fake_basename)

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5

    target_dir = output_dir / "test"
    assert target_dir.is_dir()
    files = sorted(f.name for f in target_dir.iterdir() if f.is_file())
    assert len(files) == 5
    for filename in files:
        # 現在の実装では、短縮されない場合は safe_pdf_name ("  test. ") がそのまま接頭辞に使われる
        assert filename.startswith("  test. _")


# ---------------------------------------------------------------------------
# パス長の短縮
# ---------------------------------------------------------------------------


def test_path_length_no_truncation(tmp_path: Path, copy_sample_pdf):
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    expected = expected_prefix("pdf_image_test", output_dir)
    assert expected == "pdf_image_test"

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5

    target_dir = output_dir / "pdf_image_test"
    files = list(target_dir.iterdir())
    assert len(files) == 5
    for f in files:
        assert f.name.startswith("pdf_image_test_")
        assert len(str(f.resolve())) <= 200


def test_path_length_with_truncation(tmp_path: Path, copy_sample_pdf):
    output_dir = tmp_path / "output"

    # 5 <= max_pdf_name_len < N となる N を探索
    chosen_n = None
    for n in range(5, 200):
        name = "a" * n
        folder_name = name.strip(". ")
        abs_target_dir = os.path.abspath(os.path.join(output_dir, folder_name))
        max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35
        if 5 <= max_pdf_name_len < n:
            sample_file_path = os.path.join(
                abs_target_dir, f"{name[:max_pdf_name_len]}_page1_1.jpeg"
            )
            if len(sample_file_path) < 260 and len(abs_target_dir) < 240:
                chosen_n = n
                break

    if chosen_n is None:
        pytest.skip("この環境のパス長では短縮ありのテスト条件を満たす N を生成できません")

    name = "a" * chosen_n
    exp_prefix = expected_prefix(name, output_dir)
    assert 5 <= len(exp_prefix) < chosen_n

    pdf_path = copy_sample_pdf(tmp_path, f"{name}.pdf")
    assert len(str(pdf_path.resolve())) < 260

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5

    target_dir = output_dir / name
    assert target_dir.is_dir()
    files = list(target_dir.iterdir())
    assert len(files) == 5
    for f in files:
        assert f.name.startswith(f"{exp_prefix}_")
        assert len(str(f.resolve())) <= 200


def test_path_length_no_prefix(tmp_path: Path, copy_sample_pdf):
    output_dir = tmp_path / "output"

    chosen_n = None
    for n in range(5, 200):
        name = "a" * n
        folder_name = name.strip(". ")
        abs_target_dir = os.path.abspath(os.path.join(output_dir, folder_name))
        max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35
        if max_pdf_name_len < 5:
            sample_file_path = os.path.join(abs_target_dir, "page1_1.jpeg")
            if len(sample_file_path) < 260 and len(abs_target_dir) < 240:
                chosen_n = n
                break

    if chosen_n is None:
        pytest.skip("この環境のパス長では接頭辞なしのテスト条件を満たす N を生成できません")

    name = "a" * chosen_n
    exp_prefix = expected_prefix(name, output_dir)
    assert exp_prefix == ""

    pdf_path = copy_sample_pdf(tmp_path, f"{name}.pdf")
    assert len(str(pdf_path.resolve())) < 260

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5

    target_dir = output_dir / name
    assert target_dir.is_dir()
    files = list(target_dir.iterdir())
    assert len(files) == 5
    for f in files:
        assert f.name.startswith("page")


# ---------------------------------------------------------------------------
# リファクタリング後のヘルパー関数の単体テスト (Issue #8)
# ---------------------------------------------------------------------------


def test_sanitize_filename_all_forbidden_chars():
    for ch in '<>:"/\\|?*':
        assert sanitize_filename(f"prefix{ch}suffix") == "prefix_suffix"
    assert sanitize_filename('<>:"/\\|?*') == "_________"


def test_sanitize_filename_allowed_chars():
    assert sanitize_filename("normal_file-123.pdf") == "normal_file-123.pdf"
    assert sanitize_filename("日本語のファイル名（サンプル）") == "日本語のファイル名（サンプル）"


def test_build_folder_name():
    assert build_folder_name("  test. ") == "test"
    assert build_folder_name("...test...") == "test"
    assert build_folder_name("normal_folder") == "normal_folder"


def test_compute_file_prefix():
    # max_pdf_name_len = 200 - len(abs_target_dir) - 1 - 35 = 164 - len(abs_target_dir)
    # len(abs_target_dir) = 150 のとき max_pdf_name_len = 14
    dir_150 = "x" * 150

    # 上限ちょうど（len(safe_name) == max_len） -> そのまま
    assert compute_file_prefix("a" * 14, dir_150) == "a" * 14

    # 上限を 1 文字超える -> 短縮される
    assert compute_file_prefix("a" * 15, dir_150) == "a" * 14

    # 短縮した結果の末尾が . や空白 -> 除かれる
    assert compute_file_prefix("a" * 13 + ".extra", dir_150) == "a" * 13
    assert compute_file_prefix("a" * 13 + " extra", dir_150) == "a" * 13

    # max_len == 5 (len(abs_target_dir) = 159) -> 短縮される（空にならない）
    dir_159 = "x" * 159
    assert compute_file_prefix("abcdef", dir_159) == "abcde"
    assert compute_file_prefix("abcde", dir_159) == "abcde"

    # max_len == 4 (len(abs_target_dir) = 160) -> ""
    dir_160 = "x" * 160
    assert compute_file_prefix("abcdef", dir_160) == ""


def test_format_figure_number():
    assert format_figure_number((1, 2)) == "1-2"
    assert format_figure_number((3, 0)) == "3"
    assert format_figure_number(None) is None


def test_resolve_suffix():
    counts: dict[str, int] = {}
    assert resolve_suffix("fig1", counts) == "fig1"
    assert resolve_suffix("fig1", counts) == "fig1_1"
    assert resolve_suffix("fig1", counts) == "fig1_2"


def test_generate_image_filename():
    assert generate_image_filename("my_doc", 1, "fig1", "png") == "my_doc_page1_fig1.png"
    assert generate_image_filename("", 2, "1", "jpeg") == "page2_1.jpeg"


def test_extract_images_fallback_on_pixmap_error(
    tmp_path: Path, copy_sample_pdf, monkeypatch, caplog
):
    def fake_build_pixmap(*args, **kwargs):
        raise RuntimeError("Pixmap creation failed intentionally")

    monkeypatch.setattr(extractor, "_build_pixmap", fake_build_pixmap)

    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    with caplog.at_level(logging.WARNING):
        count = extract_images_from_pdf(str(pdf_path), str(output_dir))

    assert count == 5
    target_dir = output_dir / "pdf_image_test"
    assert target_dir.is_dir()
    files = sorted(f.name for f in target_dir.iterdir() if f.is_file())
    # サンプル PDF 内の全画像 (xref 4, 5, 6, 9, 10) の元の extract_image(xref)["ext"] は
    # jpeg または png であり、フォールバック時も元の拡張子で EXPECTED_SAMPLE_FILES と同等に保存される
    assert files == EXPECTED_SAMPLE_FILES

    # Pixmap による保存を試みる画像（smask > 0 または ext == 'png'）について WARNING が記録される
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 3
    assert all("Pixmapでの保存に失敗したため、元データのまま保存します" in w.message for w in warnings)

