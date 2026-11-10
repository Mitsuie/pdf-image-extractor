"""Tkinter によるアップデート確認・進捗表示ダイアログモジュール。

最新バージョンのリリースノートを表示し、ユーザーの指示でダウンロード、
SHA-256完全性検証、および新バージョンの自動起動を行います。
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from updater import (
    UpdateCancelledError,
    UpdateInfo,
    UpdateVerificationError,
    download_file,
    launch_executable,
)

logger = logging.getLogger(__name__)


class UpdateDialog(tk.Toplevel):
    """アップデート確認・ダウンロードダイアログ。"""

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        update_info: UpdateInfo,
    ) -> None:
        """UpdateDialog を初期化します。

        Args:
            parent: 親ウィンドウ。
            update_info: 更新情報オブジェクト。
        """
        super().__init__(parent)
        self.parent = parent
        self.update_info = update_info

        self.title("アップデートの確認")
        self.transient(parent)
        self.grab_set()

        self.cancel_event: threading.Event | None = None
        self.download_thread: threading.Thread | None = None
        self.is_downloading = False

        self._setup_ui()
        self._center_window(520, 480)
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _setup_ui(self) -> None:
        """UIコンポーネントを初期化して配置します。"""
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. タイトル／ヘッダーセクション
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_label = ttk.Label(
            header_frame,
            text=f"新しいバージョンが利用可能です（v{self.update_info.latest_version}）",
            font=("Helvetica", 11, "bold"),
        )
        title_label.pack(anchor=tk.W, pady=(0, 4))

        version_info = (
            f"現在のバージョン: v{self.update_info.current_version}  ->  "
            f"最新バージョン: v{self.update_info.latest_version}"
        )
        ver_label = ttk.Label(header_frame, text=version_info)
        ver_label.pack(anchor=tk.W)

        if self.update_info.release_name and self.update_info.release_name != self.update_info.latest_version:
            rel_name_label = ttk.Label(
                header_frame,
                text=f"リリース: {self.update_info.release_name}",
                font=("Helvetica", 9, "italic"),
            )
            rel_name_label.pack(anchor=tk.W, pady=(2, 0))

        # 2. リリースノートセクション
        notes_lf = ttk.LabelFrame(main_frame, text=" リリースノート ", padding="8")
        notes_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.notes_area = ScrolledText(
            notes_lf, wrap=tk.WORD, height=10, font=("Consolas", 9)
        )
        self.notes_area.pack(fill=tk.BOTH, expand=True)
        notes_text = self.update_info.release_notes.strip() or "（リリースノートはありません）"
        self.notes_area.insert(tk.END, notes_text)
        self.notes_area.config(state="disabled")

        # 3. 進捗表示セクション
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(
            progress_frame,
            text="更新ボタンをクリックするとダウンロードを開始します。",
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 4))

        self.progress_bar = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X)

        # 4. 操作ボタンセクション
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        self.action_btn = ttk.Button(
            btn_frame,
            text="今すぐ更新",
            command=self.start_update,
            style="Accent.TButton",
        )
        self.action_btn.pack(side=tk.RIGHT, padx=(5, 0))

        self.close_btn = ttk.Button(
            btn_frame,
            text="後で閉じる",
            command=self._on_window_close,
        )
        self.close_btn.pack(side=tk.RIGHT)

    def _center_window(self, width: int, height: int) -> None:
        """親ウィンドウの中央にダイアログを配置します。"""
        self.parent.update_idletasks()
        p_x = self.parent.winfo_rootx()
        p_y = self.parent.winfo_rooty()
        p_w = self.parent.winfo_width()
        p_h = self.parent.winfo_height()

        x = max(0, p_x + (p_w - width) // 2)
        y = max(0, p_y + (p_h - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def start_update(self) -> None:
        """アップデートのダウンロード処理を開始します。"""
        if not self.update_info.exe_download_url:
            if messagebox.askyesno(
                "手動更新",
                "直接ダウンロード可能な実行ファイルが見つかりませんでした。\n"
                "ブラウザでGitHubのリリースベージを開きますか？",
            ):
                webbrowser.open(self.update_info.html_url)
            self.destroy()
            return

        self.is_downloading = True
        self.cancel_event = threading.Event()

        # ボタン表示を「中断」に変更
        self.action_btn.config(
            text="中断",
            command=self.cancel_update,
            style="Danger.TButton",
            state="normal",
        )
        self.close_btn.config(state="disabled")
        self.progress_bar["value"] = 0
        self.status_label.config(text="ダウンロードを準備中...")

        filename = self.update_info.exe_name or "PDFImageExtractor_new.exe"
        dest_path = os.path.join(tempfile.gettempdir(), filename)

        self.download_thread = threading.Thread(
            target=self._run_download,
            args=(dest_path,),
            daemon=True,
        )
        self.download_thread.start()

    def cancel_update(self) -> None:
        """ダウンロードの中断を要求します。"""
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.status_label.config(text="中断要求を送信しました...")
            self.action_btn.config(state="disabled")

    def _safe_after(self, callback: Callable, *args: Any) -> None:
        """スレッドセーフかつメインループ未実行時にも安全にコールバックを実行します。"""
        try:
            self.after(0, callback, *args)
        except (RuntimeError, tk.TclError):
            try:
                callback(*args)
            except Exception as e:
                logger.warning("safe_after コールバックの実行に失敗しました: %s", e)

    def _run_download(self, dest_path: str) -> None:
        """ワーカースレッドでファイルをダウンロードし、検証します。"""
        try:
            assert self.update_info.exe_download_url is not None
            download_file(
                url=self.update_info.exe_download_url,
                dest_path=dest_path,
                expected_sha256=self.update_info.expected_sha256,
                progress_callback=self._safe_update_progress,
                cancel_event=self.cancel_event,
            )
            self._safe_after(self._on_download_success, dest_path)
        except UpdateCancelledError:
            self._safe_after(self._on_download_cancelled)
        except UpdateVerificationError as e:
            self._safe_after(self._on_download_verification_error, str(e))
        except Exception as e:
            self._safe_after(self._on_download_error, str(e))

    def _safe_update_progress(self, downloaded: int, total: int) -> None:
        """ダウンロード進捗をメインスレッドで更新します。"""
        self._safe_after(self._update_progress_ui, downloaded, total)

    def _update_progress_ui(self, downloaded: int, total: int) -> None:
        """プログレスバーと進捗テキストを更新します。"""
        if total > 0:
            pct = (downloaded / total) * 100
            self.progress_bar["value"] = pct
            mb_curr = downloaded / (1024 * 1024)
            mb_total = total / (1024 * 1024)
            self.status_label.config(
                text=f"ダウンロード中: {mb_curr:.1f} MB / {mb_total:.1f} MB ({pct:.1f}%)"
            )
        else:
            mb_curr = downloaded / (1024 * 1024)
            self.status_label.config(text=f"ダウンロード中: {mb_curr:.1f} MB")

    def _on_download_success(self, dest_path: str) -> None:
        """ダウンロード・検証完了時の後続処理を実行します。"""
        self.is_downloading = False
        self.progress_bar["value"] = 100
        self.status_label.config(text="ダウンロードおよび検証が完了しました。")

        messagebox.showinfo(
            "更新完了",
            "最新バージョンのダウンロードと整合性検証が完了しました。\n"
            "アプリケーションを終了し、新しいバージョンを起動します。",
        )
        try:
            launch_executable(dest_path)
        except Exception as e:
            messagebox.showerror(
                "起動エラー",
                f"新しいバージョンの起動に失敗しました:\n{e}\n\n保存先: {dest_path}",
            )
            self._reset_buttons()
            return

        # 親ウィンドウを終了してアプリを安全に閉じる
        self.parent.destroy()

    def _on_download_cancelled(self) -> None:
        """ダウンロード中断時のUI復帰処理。"""
        self.is_downloading = False
        self.status_label.config(text="ダウンロードが中断されました。")
        self.progress_bar["value"] = 0
        self._reset_buttons()

    def _on_download_verification_error(self, message: str) -> None:
        """SHA-256検証失敗時のエラー通知およびUI復帰処理。"""
        self.is_downloading = False
        self.status_label.config(text="完全性検証エラー: ファイルは破棄されました。")
        self.progress_bar["value"] = 0
        messagebox.showerror(
            "整合性エラー",
            f"ダウンロードしたファイルの完全性検証（SHA-256）に失敗しました。\n\n"
            f"{message}\n\n"
            "破損または改ざんの可能性があるため、ダウンロードされたファイルは安全に破棄されました。",
        )
        self._reset_buttons()

    def _on_download_error(self, message: str) -> None:
        """通信エラー等の異常発生時のエラー通知およびUI復帰処理。"""
        self.is_downloading = False
        self.status_label.config(text="ダウンロード中にエラーが発生しました。")
        messagebox.showerror(
            "ダウンロードエラー",
            f"ファイルのダウンロード中にエラーが発生しました:\n{message}",
        )
        self._reset_buttons()

    def _reset_buttons(self) -> None:
        """ボタンの状態を通常状態に戻します。"""
        self.action_btn.config(
            text="今すぐ更新",
            command=self.start_update,
            style="Accent.TButton",
            state="normal",
        )
        self.close_btn.config(state="normal")

    def _on_window_close(self) -> None:
        """ウィンドウの閉じる要求を処理します。"""
        if self.is_downloading:
            if not messagebox.askyesno(
                "確認",
                "ダウンロードが進行中です。中断してウィンドウを閉じますか？",
            ):
                return
            if self.cancel_event is not None:
                self.cancel_event.set()
        self.destroy()
