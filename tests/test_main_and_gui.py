"""main.py および app_window.py のGUI・エントリーポイント動作確認テスト。"""

from __future__ import annotations

import importlib
import logging
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app_window import AppWindow
from config_manager import ConfigManager
import main


@pytest.fixture(scope="module")
def tk_root():
    """Tkinter ルートウィンドウを非表示で生成・破棄するフィクスチャ（モジュール全体で共有）。"""
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


def test_main_module_attributes():
    """main.py に必要なエントリーポイントおよびハンドラが定義されていることを検証。"""
    assert hasattr(main, "main")
    assert callable(main.main)
    assert hasattr(main, "setup_logging")
    assert callable(main.setup_logging)
    assert hasattr(main, "handle_uncaught_exception")
    assert callable(main.handle_uncaught_exception)


def test_main_uncaught_exception_handler():
    """未捕捉例外ハンドラがログ記録とダイアログ表示を行うことを検証。"""
    exc = ValueError("テスト用エラー")
    with patch("main.logger.critical") as mock_log, patch(
        "tkinter.messagebox.showerror"
    ) as mock_msg:
        main.handle_uncaught_exception(ValueError, exc, None)
        assert mock_log.called
        assert mock_msg.called
        assert "テスト用エラー" in mock_msg.call_args[0][1]


def test_main_uncaught_exception_keyboard_interrupt():
    """KeyboardInterrupt の場合は sys.__excepthook__ に委任することを検証。"""
    exc = KeyboardInterrupt()
    with patch("sys.__excepthook__") as mock_sys_hook:
        main.handle_uncaught_exception(KeyboardInterrupt, exc, None)
        assert mock_sys_hook.called


def test_main_function_execution():
    """main() 関数が正常にTk初期化、AppWindow生成、mainloopを実行することを検証。"""
    with patch("main.setup_logging") as mock_logging, patch(
        "tkinter.Tk"
    ) as mock_tk_cls, patch("main.AppWindow") as mock_app_cls:
        mock_root = MagicMock()
        mock_tk_cls.return_value = mock_root

        main.main()

        assert mock_logging.called
        assert mock_tk_cls.called
        assert mock_app_cls.called
        assert mock_root.mainloop.called


def test_app_deprecation_warning():
    """app.py インポート時に DeprecationWarning が発生し、互換エイリアスが提供されることを検証。"""
    if "app" in sys.modules:
        del sys.modules["app"]

    with pytest.deprecated_call():
        import app

    assert hasattr(app, "PDFImageExtractorApp")
    assert app.PDFImageExtractorApp is AppWindow
    assert hasattr(app, "main")
    assert app.main is main.main


def test_app_window_initialization(tk_root: tk.Tk, tmp_path: Path):
    """AppWindow の各UIセクションが正常に構築されることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    # セクション要素の存在検証
    assert hasattr(app_win, "mode_var")
    assert app_win.mode_var.get() == "file"
    assert hasattr(app_win, "file_entry")
    assert hasattr(app_win, "folder_entry")
    assert hasattr(app_win, "output_combobox")
    assert hasattr(app_win, "open_dir_cb")
    assert hasattr(app_win, "run_btn")
    assert hasattr(app_win, "cancel_btn")
    assert hasattr(app_win, "exit_btn")
    assert hasattr(app_win, "progress_bar")
    assert hasattr(app_win, "log_area")
    assert app_win.config_manager is cm


def test_app_window_config_manager_integration(tk_root: tk.Tk, tmp_path: Path):
    """ConfigManager の履歴が Combobox に反映され、実行時に履歴追加が行われることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    dir1 = str(tmp_path / "out1")
    dir2 = str(tmp_path / "out2")
    cm.add_history(dir2)
    cm.add_history(dir1)

    app_win = AppWindow(tk_root, config_manager=cm)

    # コンボボックスに初期履歴が設定されていること
    assert list(app_win.output_combobox["values"]) == [dir1, dir2]

    # 保存先を変更して履歴追加
    dir3 = str(tmp_path / "out3")
    app_win.output_path_var.set(dir3)
    app_win.save_config()

    assert cm.history[0] == dir3
    assert list(app_win.output_combobox["values"]) == [dir3, dir1, dir2]


def test_app_window_thread_safe_notification(tk_root: tk.Tk, tmp_path: Path):
    """safe_log, safe_showinfo, safe_showerror が root.after を介して実行されることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    with patch.object(tk_root, "after", wraps=tk_root.after) as mock_after:
        app_win.safe_log("テストログ")
        assert mock_after.called
        assert mock_after.call_args[0][0] == 0

    # イベントループを処理してログが ScrolledText に反映されることを確認
    tk_root.update()
    content = app_win.log_area.get("1.0", tk.END)
    assert "テストログ" in content

    # safe_showinfo / safe_showerror の after 呼び出し
    with patch.object(tk_root, "after") as mock_after:
        app_win.safe_showinfo("完了", "完了メッセージ")
        assert mock_after.called

    with patch.object(tk_root, "after") as mock_after:
        app_win.safe_showerror("エラー", "エラーメッセージ")
        assert mock_after.called


def test_app_window_toggle_mode(tk_root: tk.Tk, tmp_path: Path):
    """処理モード切り替えで入力欄の活性・非活性が正しくトグルされることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    # 初期状態: file
    assert str(app_win.file_entry["state"]) == "normal"
    assert str(app_win.folder_entry["state"]) == "disabled"

    # folder に変更
    app_win.mode_var.set("folder")
    app_win.toggle_mode()
    assert str(app_win.file_entry["state"]) == "disabled"
    assert str(app_win.folder_entry["state"]) == "normal"

    # file に戻す
    app_win.mode_var.set("file")
    app_win.toggle_mode()
    assert str(app_win.file_entry["state"]) == "normal"
    assert str(app_win.folder_entry["state"]) == "disabled"


def test_app_window_safe_exit_idle(tk_root: tk.Tk, tmp_path: Path):
    """処理待機時の safe_exit が確認なしで root.destroy を呼ぶことを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)

    with patch.object(tk_root, "destroy") as mock_destroy, patch(
        "tkinter.messagebox.askyesno"
    ) as mock_confirm:
        app_win.safe_exit()
        assert not mock_confirm.called
        assert mock_destroy.called


def test_app_window_safe_exit_running(tk_root: tk.Tk, tmp_path: Path):
    """処理実行中の safe_exit が確認ダイアログを表示することを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)
    app_win.run_btn.config(state="disabled")

    with patch.object(tk_root, "destroy") as mock_destroy, patch(
        "tkinter.messagebox.askyesno", return_value=False
    ) as mock_confirm:
        app_win.safe_exit()
        assert mock_confirm.called
        assert not mock_destroy.called

    with patch.object(tk_root, "destroy") as mock_destroy, patch(
        "tkinter.messagebox.askyesno", return_value=True
    ) as mock_confirm:
        app_win.safe_exit()
        assert mock_confirm.called
        assert mock_destroy.called


def test_app_window_run_file_extraction(
    tk_root: tk.Tk, tmp_path: Path, sample_pdf: Path
):
    """単一PDFの抽出処理が正常に完了し、safe_showinfo および safe_log が呼ばれることを検証。"""
    config_file = tmp_path / "config.json"
    cm = ConfigManager(config_path=str(config_file))
    app_win = AppWindow(tk_root, config_manager=cm)
    app_win.open_dir_var.set(False)  # テスト中にエクスプローラーを開かない

    out_dir = str(tmp_path / "output")
    with patch.object(app_win, "safe_showinfo") as mock_info, patch.object(
        app_win, "safe_showerror"
    ) as mock_err:
        app_win.run_file_extraction(str(sample_pdf), out_dir)
        assert mock_info.called
        assert not mock_err.called

    tk_root.update()
    content = app_win.log_area.get("1.0", tk.END)
    assert "抽出が完了しました" in content

