"""Issue #12: GitHub Releases を用いた自動アップデートシステムの単体・結合テスト。"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import threading
import tkinter as tk
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, call, patch
import pytest

from app_window import AppWindow
from update_dialog import UpdateDialog
from updater import (
    UpdateCancelledError,
    UpdateInfo,
    UpdateVerificationError,
    compare_versions,
    download_file,
    fetch_latest_release_info,
    is_newer_version,
    launch_executable,
    parse_sha256_text,
    parse_version_tuple,
)
from version import GITHUB_REPO_NAME, GITHUB_REPO_OWNER, __version__


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
# 1. バージョンパースとセマンティック比較テスト
# ---------------------------------------------------------------------------


def test_parse_version_tuple():
    """バージョン文字列が期待通りの整数タプルに変換されること。"""
    assert parse_version_tuple("1.0.0") == (1, 0, 0)
    assert parse_version_tuple("v1.2.3") == (1, 2, 3)
    assert parse_version_tuple("V2.0") == (2, 0)
    assert parse_version_tuple("v1.0.0-beta") == (1, 0, 0)
    assert parse_version_tuple("1.2.3.4") == (1, 2, 3, 4)
    assert parse_version_tuple("v3") == (3,)
    assert parse_version_tuple("") == ()
    assert parse_version_tuple(None) == ()
    assert parse_version_tuple("invalid") == ()


def test_compare_versions():
    """compare_versions がセマンティック比較を行い正しい符号を返すこと。"""
    # 等価
    assert compare_versions("1.0.0", "1.0.0") == 0
    assert compare_versions("v1.2.3", "1.2.3") == 0
    assert compare_versions("1.0", "1.0.0") == 0

    # v1 < v2
    assert compare_versions("1.0.0", "1.0.1") == -1
    assert compare_versions("1.0.9", "1.1.0") == -1
    assert compare_versions("1.9.9", "2.0.0") == -1
    assert compare_versions("v1.0.0", "v1.1.0") == -1

    # v1 > v2
    assert compare_versions("1.0.1", "1.0.0") == 1
    assert compare_versions("1.1.0", "1.0.9") == 1
    assert compare_versions("2.0.0", "1.9.9") == 1
    assert compare_versions("v2.1.0", "v2.0.9") == 1


def test_is_newer_version():
    """is_newer_version が新バージョンの有無を真偽値で正しく返すこと。"""
    assert is_newer_version("1.0.0", "1.0.1") is True
    assert is_newer_version("1.1.0", "1.2.0") is True
    assert is_newer_version("1.0.0", "1.0.0") is False
    assert is_newer_version("1.2.0", "1.1.0") is False
    assert is_newer_version("v1.1.0", "v1.1.0") is False


# ---------------------------------------------------------------------------
# 2. SHA-256 パース処理テスト
# ---------------------------------------------------------------------------


def test_parse_sha256_text():
    """sha256ファイルの内容からハッシュ値が正確に抽出されること。"""
    test_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    # 1. 単体ハッシュ
    assert parse_sha256_text(test_hash) == test_hash

    # 2. 標準的な sha256sum 形式 (<hash> *<filename>)
    line = f"{test_hash} *PDFImageExtractor.exe\n"
    assert parse_sha256_text(line) == test_hash

    # 3. 複数行があり、ファイル名で対象を特定する場合
    multi_line = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa *other.exe\n"
        f"{test_hash.upper()}  *PDFImageExtractor.exe\n"
    )
    assert parse_sha256_text(multi_line, "PDFImageExtractor.exe") == test_hash

    # 4. ハッシュが存在しない場合
    assert parse_sha256_text("invalid content without hash") is None


# ---------------------------------------------------------------------------
# 3. リリース情報取得 (fetch_latest_release_info) テスト
# ---------------------------------------------------------------------------


def test_fetch_latest_release_info_success():
    """GitHub Releases API のレスポンスを正しく UpdateInfo にパースできること。"""
    dummy_release_json = {
        "tag_name": "v1.2.0",
        "name": "Release 1.2.0",
        "body": "## 更新履歴\n- 新機能追加",
        "html_url": "https://github.com/Mitsuie/pdf-image-extractor/releases/tag/v1.2.0",
        "assets": [
            {
                "name": "PDFImageExtractor.exe",
                "size": 12345678,
                "browser_download_url": "https://example.com/download/PDFImageExtractor.exe",
            },
            {
                "name": "PDFImageExtractor.exe.sha256",
                "size": 64,
                "browser_download_url": "https://example.com/download/PDFImageExtractor.exe.sha256",
            },
        ],
    }

    dummy_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    dummy_sha_text = f"{dummy_hash} *PDFImageExtractor.exe".encode("utf-8")

    class MockResponse:
        def __init__(self, data: bytes):
            self.data = data

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=5.0):
        url = req.full_url if hasattr(req, "full_url") else req
        if "releases/latest" in url:
            return MockResponse(json.dumps(dummy_release_json).encode("utf-8"))
        elif "sha256" in url:
            return MockResponse(dummy_sha_text)
        raise ValueError(f"Unexpected url: {url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        info = fetch_latest_release_info("Mitsuie", "pdf-image-extractor", "1.1.0")

    assert info is not None
    assert info.current_version == "1.1.0"
    assert info.latest_version == "1.2.0"
    assert info.release_name == "Release 1.2.0"
    assert "新機能追加" in info.release_notes
    assert info.exe_name == "PDFImageExtractor.exe"
    assert info.exe_size == 12345678
    assert info.exe_download_url == "https://example.com/download/PDFImageExtractor.exe"
    assert info.expected_sha256 == dummy_hash


def test_fetch_latest_release_info_network_error():
    """通信エラー発生時に例外を送出せず None を返すこと。"""
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Network unreachable"),
    ):
        info = fetch_latest_release_info("Mitsuie", "pdf-image-extractor", "1.1.0")
    assert info is None


# ---------------------------------------------------------------------------
# 4. ファイルダウンロード・完全性検証 (download_file) テスト
# ---------------------------------------------------------------------------


class MockDownloadStream:
    """ストリーミングダウンロードをシミュレートするモックレスポンス。"""

    def __init__(self, data: bytes, chunk_size: int = 16):
        self.stream = io.BytesIO(data)
        self.chunk_size = chunk_size
        self.headers = {"Content-Length": str(len(data))}

    def read(self, amt: int | None = None):
        return self.stream.read(amt if amt is not None else self.chunk_size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def test_download_file_success_with_hash(tmp_path: Path):
    """ダウンロードとハッシュ検証が正常に完了し、進捗コールバックが呼ばれること。"""
    data = b"Hello, PDFImageExtractor binary test payload!"
    expected_hash = hashlib.sha256(data).hexdigest()
    dest_path = str(tmp_path / "app.exe")

    progress_calls: list[tuple[int, int]] = []

    def on_progress(downloaded: int, total: int):
        progress_calls.append((downloaded, total))

    with patch(
        "urllib.request.urlopen",
        return_value=MockDownloadStream(data, chunk_size=8),
    ):
        download_file(
            url="https://example.com/app.exe",
            dest_path=dest_path,
            expected_sha256=expected_hash,
            progress_callback=on_progress,
            chunk_size=8,
        )

    assert os.path.exists(dest_path)
    with open(dest_path, "rb") as f:
        assert f.read() == data
    assert len(progress_calls) > 0
    assert progress_calls[-1] == (len(data), len(data))


def test_download_file_hash_mismatch(tmp_path: Path):
    """ハッシュ不一致時に UpdateVerificationError が発生し、ファイルが破棄されること。"""
    data = b"Valid payload data"
    wrong_hash = "0" * 64
    dest_path = str(tmp_path / "app_mismatch.exe")

    with patch(
        "urllib.request.urlopen",
        return_value=MockDownloadStream(data, chunk_size=8),
    ):
        with pytest.raises(UpdateVerificationError) as exc_info:
            download_file(
                url="https://example.com/app.exe",
                dest_path=dest_path,
                expected_sha256=wrong_hash,
            )

    assert "SHA-256ハッシュが一致しません" in str(exc_info.value)
    # ファイルおよび一時ファイルが残っていないこと
    assert not os.path.exists(dest_path)
    assert not os.path.exists(dest_path + ".tmp")


def test_download_file_cancel_before_start(tmp_path: Path):
    """ダウンロード開始前に中断フラグがある場合、即時 UpdateCancelledError が送出されること。"""
    dest_path = str(tmp_path / "app_cancelled.exe")
    cancel_event = threading.Event()
    cancel_event.set()

    with pytest.raises(UpdateCancelledError):
        download_file(
            url="https://example.com/app.exe",
            dest_path=dest_path,
            cancel_event=cancel_event,
        )

    assert not os.path.exists(dest_path)
    assert not os.path.exists(dest_path + ".tmp")


def test_download_file_cancel_during_stream(tmp_path: Path):
    """ダウンロード途中に中断された場合、一時ファイルが削除され UpdateCancelledError が送出されること。"""
    data = b"Chunk1Chunk2Chunk3"
    dest_path = str(tmp_path / "app_cancelled_mid.exe")
    cancel_event = threading.Event()

    def on_progress(downloaded: int, total: int):
        if downloaded >= 6:
            cancel_event.set()

    with patch(
        "urllib.request.urlopen",
        return_value=MockDownloadStream(data, chunk_size=6),
    ):
        with pytest.raises(UpdateCancelledError):
            download_file(
                url="https://example.com/app.exe",
                dest_path=dest_path,
                progress_callback=on_progress,
                cancel_event=cancel_event,
                chunk_size=6,
            )

    assert not os.path.exists(dest_path)
    assert not os.path.exists(dest_path + ".tmp")


# ---------------------------------------------------------------------------
# 5. 実行ファイル起動 (launch_executable) テスト
# ---------------------------------------------------------------------------


def test_launch_executable():
    """独立プロセスとして実行ファイルを起動する Popen が正しく呼ばれること。"""
    with patch("subprocess.Popen") as mock_popen:
        launch_executable("dummy_app.exe")

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        assert os.path.abspath("dummy_app.exe") in args[0]
        assert kwargs.get("close_fds") is True


# ---------------------------------------------------------------------------
# 6. UpdateDialog UI テスト
# ---------------------------------------------------------------------------


def test_update_dialog_init_and_elements(tk_root: tk.Tk):
    """UpdateDialog の UI 要素（ラベル・テキスト・プログレスバー・ボタン）が正しく初期化されること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0 リリース",
        release_notes="テスト用リリースノート",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)

    assert "テスト用リリースノート" in dialog.notes_area.get("1.0", tk.END)
    assert dialog.action_btn["text"] == "今すぐ更新"
    assert dialog.close_btn["text"] == "後で閉じる"
    assert dialog.progress_bar["value"] == 0

    dialog.destroy()


def test_update_dialog_start_update_ui(tk_root: tk.Tk):
    """UpdateDialog で更新を開始した際、スレッド起動とボタン状態の変化が正しく行われること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)

    with patch("threading.Thread.start") as mock_thread_start:
        dialog.start_update()

        assert dialog.is_downloading is True
        assert dialog.cancel_event is not None
        assert not dialog.cancel_event.is_set()
        assert dialog.action_btn["text"] == "中断"
        assert str(dialog.close_btn["state"]) == "disabled"
        assert mock_thread_start.called

    dialog.destroy()


def test_update_dialog_cancel_update_method(tk_root: tk.Tk):
    """cancel_update 呼び出し時に cancel_event がセットされボタンが無効化されること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)
    dialog.cancel_event = threading.Event()
    dialog.action_btn.config(state="normal")

    dialog.cancel_update()

    assert dialog.cancel_event.is_set()
    assert str(dialog.action_btn["state"]) == "disabled"
    assert "中断要求を送信しました" in dialog.status_label["text"]

    dialog.destroy()


def test_update_dialog_on_download_success(tk_root: tk.Tk):
    """ダウンロード成功時に通知ダイアログ表示、実行ファイル起動、親ウィンドウ破棄が行われること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)

    with patch("update_dialog.launch_executable") as mock_launch, \
         patch("update_dialog.messagebox.showinfo") as mock_showinfo, \
         patch.object(dialog.parent, "destroy") as mock_parent_destroy:

        dialog._on_download_success("C:/temp/app.exe")

        assert dialog.is_downloading is False
        assert dialog.progress_bar["value"] == 100
        mock_showinfo.assert_called_once()
        mock_launch.assert_called_once_with("C:/temp/app.exe")
        mock_parent_destroy.assert_called_once()


def test_update_dialog_on_download_cancelled(tk_root: tk.Tk):
    """ダウンロード中断時にボタン状態とステータス表示が正常に復帰すること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)
    dialog.action_btn.config(text="中断", state="disabled")
    dialog.close_btn.config(state="disabled")

    dialog._on_download_cancelled()

    assert dialog.is_downloading is False
    assert dialog.action_btn["text"] == "今すぐ更新"
    assert str(dialog.action_btn["state"]) == "normal"
    assert str(dialog.close_btn["state"]) == "normal"
    assert "中断されました" in dialog.status_label["text"]

    dialog.destroy()


def test_update_dialog_on_download_verification_error(tk_root: tk.Tk):
    """ハッシュ検証失敗時にエラーダイアログが表示され、ボタン状態が復帰すること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)
    with patch("update_dialog.messagebox.showerror") as mock_showerror:
        dialog._on_download_verification_error("Hash mismatch")

        assert dialog.is_downloading is False
        assert dialog.action_btn["text"] == "今すぐ更新"
        assert str(dialog.action_btn["state"]) == "normal"
        mock_showerror.assert_called_once()
        assert "整合性エラー" in mock_showerror.call_args[0][0]

    dialog.destroy()


def test_update_dialog_progress_ui(tk_root: tk.Tk):
    """進捗更新メソッドによりプログレスバーとラベルが正しく更新されること。"""
    info = UpdateInfo(
        current_version="1.1.0",
        latest_version="1.2.0",
        release_name="v1.2.0",
        release_notes="notes",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=1000,
        expected_sha256="abc",
    )

    dialog = UpdateDialog(tk_root, info)

    # 1. total > 0
    dialog._update_progress_ui(524288, 1048576)  # 50%
    assert pytest.approx(dialog.progress_bar["value"]) == 50.0
    assert "50.0%" in dialog.status_label["text"]

    # 2. total == 0
    dialog._update_progress_ui(1048576, 0)
    assert "1.0 MB" in dialog.status_label["text"]

    dialog.destroy()


# ---------------------------------------------------------------------------
# 7. AppWindow メニューバー統合テスト
# ---------------------------------------------------------------------------


def test_app_window_menu_bar(tk_root: tk.Tk):
    """AppWindow にメニューバーと「ヘルプ > 更新を確認...」が存在すること。"""
    app = AppWindow(tk_root)

    assert hasattr(app, "menubar")
    assert hasattr(app, "help_menu")

    # ヘルプメニューのコマンド数を確認
    entry_count = app.help_menu.index("end")
    assert entry_count is not None and entry_count >= 0
    # 登録されているコマンドのラベル確認
    labels = [
        app.help_menu.entrycget(i, "label")
        for i in range(entry_count + 1)
    ]
    assert any("更新を確認" in label for label in labels)


def test_app_window_check_for_updates_latest(tk_root: tk.Tk):
    """更新確認でバージョンが最新の場合、案内ダイアログが表示されること。"""
    app = AppWindow(tk_root)

    latest_info = UpdateInfo(
        current_version=__version__,
        latest_version=__version__,
        release_name="Current Release",
        release_notes="",
        html_url="",
        exe_download_url=None,
        exe_name=None,
        exe_size=None,
        expected_sha256=None,
    )

    with patch("app_window.fetch_latest_release_info", return_value=latest_info), \
         patch("tkinter.messagebox.showinfo") as mock_showinfo:
        app._run_check_updates()
        tk_root.update()

        mock_showinfo.assert_called_once()
        args, _ = mock_showinfo.call_args
        assert "最新です" in args[1]


def test_app_window_check_for_updates_newer_available(tk_root: tk.Tk):
    """新しいバージョンが存在する場合、UpdateDialog が表示されること。"""
    app = AppWindow(tk_root)

    newer_info = UpdateInfo(
        current_version=__version__,
        latest_version="99.0.0",
        release_name="v99.0.0",
        release_notes="New features",
        html_url="https://example.com",
        exe_download_url="https://example.com/app.exe",
        exe_name="app.exe",
        exe_size=123,
        expected_sha256="abc",
    )

    with patch("app_window.fetch_latest_release_info", return_value=newer_info), \
         patch("app_window.UpdateDialog") as mock_dialog:
        app._run_check_updates()
        tk_root.update()

        mock_dialog.assert_called_once_with(app.root, newer_info)
