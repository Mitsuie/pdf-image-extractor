import os
from pathlib import Path
import pytest
import extractor
from extractor import (
    extract_images_from_folder,
    extract_images_from_pdf,
    parse_figure_number,
)

EXPECTED_SAMPLE_FILES = [
    "pdf_image_test_page1_1.jpeg",
    "pdf_image_test_page1_2.png",
    "pdf_image_test_page1_3.png",
    "pdf_image_test_page2_1.jpeg",
    "pdf_image_test_page2_2.png",
]


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

