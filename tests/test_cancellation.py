"""Issue #11: 抽出進捗通知およびキャンセル機能の単体・結合テスト。"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import tkinter as tk
from unittest.mock import MagicMock, patch
import pytest

from app_window import AppWindow
from config_manager import ConfigManager
import extractor
from extractor import (
    ExtractionCancelledError,
    extract_images_from_folder,
    extract_images_from_pdf,
)


@pytest.fixture(scope="module")
def tk_root():
    """Tkinter ルートウィンドウを非表示で生成・破棄するフィクスチャ。"""
    try:
        root = tk.Tk()
        root.withdraw()
    except tk.TclError as e:
        pytest.skip(f"Tkinter root cannot be initialized: {e}")
    yield root
    try:
        root.destroy()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def cleanup_widgets(tk_root: tk.Tk):
    """各テスト実行後に子ウィジェットをクリーンアップします。"""
    yield
    for widget in tk_root.winfo_children():
        try:
            widget.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# extractor.py: 単体PDF抽出の進捗・キャンセルテスト
# ---------------------------------------------------------------------------


def test_extract_images_from_pdf_cancellation_before_start(
    tmp_path: Path, copy_sample_pdf
):
    """開始前に cancel_event がセットされている場合、即座に ExtractionCancelledError が発生する。"""
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(ExtractionCancelledError) as exc_info:
        extract_images_from_pdf(
            str(pdf_path), str(output_dir), cancel_event=cancel_event
        )

    assert "中断されました" in str(exc_info.value)

    # 1ページ目処理前に中断されたため、画像ファイルは出力されていないこと
    target_dir = output_dir / "pdf_image_test"
    if target_dir.exists():
        files = list(target_dir.glob("*"))
        assert len(files) == 0


def test_extract_images_from_pdf_cancellation_during_execution(
    tmp_path: Path, copy_sample_pdf
):
    """1ページ目完了後にキャンセルされた場合、ExtractionCancelledError が発生し、2ページ目は抽出されない。"""
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    cancel_event = threading.Event()
    progress_history: list[tuple[int, int]] = []

    def on_progress(current: int, total: int) -> None:
        progress_history.append((current, total))
        if current == 1:
            cancel_event.set()

    with pytest.raises(ExtractionCancelledError):
        extract_images_from_pdf(
            str(pdf_path),
            str(output_dir),
            progress_callback=on_progress,
            cancel_event=cancel_event,
        )

    # 進捗は1ページ目まで記録されていること
    assert progress_history == [(1, 2)]

    # 1ページ目の画像のみ保存され、2ページ目の画像は保存されていないこと
    target_dir = output_dir / "pdf_image_test"
    assert target_dir.exists()
    saved_files = sorted(f.name for f in target_dir.glob("*"))

    # サンプルPDFの1ページ目の画像（page1）は含まれるが、page2 は含まれない
    assert any("page1" in f for f in saved_files)
    assert not any("page2" in f for f in saved_files)


def test_extract_images_from_pdf_backward_compatibility(
    tmp_path: Path, copy_sample_pdf
):
    """進捗コールバックや cancel_event を渡さない従来の呼び出しが後方互換で動作する。"""
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    count = extract_images_from_pdf(str(pdf_path), str(output_dir))
    assert count == 5


def test_extract_images_from_pdf_progress_callback(
    tmp_path: Path, copy_sample_pdf
):
    """全ページの進捗コールバックが正しく呼び出されることを検証。"""
    pdf_path = copy_sample_pdf(tmp_path)
    output_dir = tmp_path / "output"

    calls: list[tuple[int, int]] = []

    def on_progress(current: int, total: int) -> None:
        calls.append((current, total))

    count = extract_images_from_pdf(
        str(pdf_path), str(output_dir), progress_callback=on_progress
    )

    assert count == 5
    assert calls == [(1, 2), (2, 2)]


# ---------------------------------------------------------------------------
# extractor.py: フォルダ一括抽出の進捗・キャンセルテスト
# ---------------------------------------------------------------------------


def test_extract_images_from_folder_cancellation_before_start(
    tmp_path: Path, copy_sample_pdf
):
    """フォルダ抽出開始前にキャンセルされた場合、ExtractionCancelledError が発生する。"""
    in_dir = tmp_path / "inputs"
    in_dir.mkdir()
    copy_sample_pdf(in_dir, "test1.pdf")
    copy_sample_pdf(in_dir, "test2.pdf")
    out_dir = tmp_path / "output"

    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(ExtractionCancelledError):
        extract_images_from_folder(
            str(in_dir), str(out_dir), cancel_event=cancel_event
        )


def test_extract_images_from_folder_cancellation_during_execution(
    tmp_path: Path, copy_sample_pdf
):
    """1ファイル目処理後に中断された場合、2ファイル目は処理されずに ExtractionCancelledError が発生する。"""
    in_dir = tmp_path / "inputs"
    in_dir.mkdir()
    copy_sample_pdf(in_dir, "a_test1.pdf")
    copy_sample_pdf(in_dir, "b_test2.pdf")
    out_dir = tmp_path / "output"

    cancel_event = threading.Event()
    file_progress_calls: list[tuple[int, int]] = []

    def on_file_progress(current: int, total: int) -> None:
        file_progress_calls.append((current, total))
        if current == 1:
            cancel_event.set()

    with pytest.raises(ExtractionCancelledError):
        extract_images_from_folder(
            str(in_dir),
            str(out_dir),
            file_progress_callback=on_file_progress,
            cancel_event=cancel_event,
        )

    # 1ファイル目の進捗のみ記録され、2ファイル目は処理されないこと
    assert file_progress_calls == [(1, 2)]
    assert (out_dir / "a_test1").exists()
    assert not (out_dir / "b_test2").exists()


# ---------------------------------------------------------------------------
# app_window.py: プログレスバーおよび中断ボタンのGUI連携テスト
# ---------------------------------------------------------------------------


def test_app_window_cancellation_ui_components(tk_root: tk.Tk, tmp_path: Path):
    """AppWindow に中断ボタンとプログレスバーが存在し、初期状態が正しいことを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    # 中断ボタン
    assert hasattr(app_win, "cancel_btn")
    assert str(app_win.cancel_btn["state"]) == "disabled"
    assert app_win.cancel_btn["text"] == "中断"

    # プログレスバー
    assert hasattr(app_win, "progress_bar")
    assert hasattr(app_win, "progressbar")
    assert app_win.progress_bar["value"] == 0

    # cancel_event
    assert hasattr(app_win, "cancel_event")
    assert not app_win.cancel_event.is_set()


def test_app_window_cancel_extraction_method(tk_root: tk.Tk, tmp_path: Path):
    """cancel_extraction を呼び出すと cancel_event がセットされ、ボタンが無効化されることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    app_win.cancel_btn.config(state="normal")
    app_win.cancel_extraction()

    assert app_win.cancel_event.is_set()
    assert str(app_win.cancel_btn["state"]) == "disabled"

    tk_root.update()
    content = app_win.log_area.get("1.0", tk.END)
    assert "中断要求を送信しました" in content


def test_app_window_progress_update(tk_root: tk.Tk, tmp_path: Path):
    """safe_update_progress によりプログレスバーの値が正しく更新されることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    app_win.safe_update_progress(1, 4)
    tk_root.update()
    assert pytest.approx(app_win.progress_bar["value"]) == 25.0

    app_win.safe_update_progress(4, 4)
    tk_root.update()
    assert pytest.approx(app_win.progress_bar["value"]) == 100.0

    app_win._reset_progress()
    assert app_win.progress_bar["value"] == 0


def test_app_window_run_file_extraction_cancelled_handling(
    tk_root: tk.Tk, tmp_path: Path, sample_pdf: Path
):
    """抽出処理が ExtractionCancelledError で終了した場合に適切なメッセージが表示され、UI状態が復帰する。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)
    app_win.open_dir_var.set(False)

    out_dir = str(tmp_path / "output")

    # 事前に中断をセットしておく
    app_win.cancel_event.set()
    app_win.run_btn.config(state="disabled")
    app_win.cancel_btn.config(state="normal")

    with patch.object(app_win, "safe_showinfo") as mock_info:
        app_win.run_file_extraction(str(sample_pdf), out_dir)
        assert mock_info.called
        assert "中断" in mock_info.call_args[0][0]

    tk_root.update()
    content = app_win.log_area.get("1.0", tk.END)
    assert "処理がユーザーによって中断されました" in content
    assert "中断までに抽出された画像は保存先フォルダに残されています" in content

    # UI状態が復帰していること
    assert str(app_win.run_btn["state"]) == "normal"
    assert str(app_win.cancel_btn["state"]) == "disabled"
