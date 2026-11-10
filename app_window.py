"""PDF画像抽出ツールのGUIメインウィンドウモジュール。"""

from __future__ import annotations

import logging
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from config_manager import ConfigManager
from extractor import (
    ExtractionCancelledError,
    extract_images_from_folder,
    extract_images_from_pdf,
)
from update_dialog import UpdateDialog
from updater import fetch_latest_release_info, is_newer_version
from version import GITHUB_REPO_NAME, GITHUB_REPO_OWNER, __version__

logger = logging.getLogger(__name__)


class AppWindow:
    """PDF画像抽出アプリケーションのGUIメインウィンドウクラス。"""

    def __init__(
        self,
        root: tk.Tk,
        config_manager: ConfigManager | None = None,
    ) -> None:
        """AppWindow を初期化します。

        Args:
            root: Tkinter のルートウィンドウ。
            config_manager: 設定マネージャーインスタンス。None の場合は新規生成します。
        """
        self.root = root
        self.root.title("PDF画像抽出ツール (PyMuPDF)")
        self.root.geometry("680x580")
        self.root.minsize(600, 500)

        self.config_manager: ConfigManager = (
            config_manager if config_manager is not None else ConfigManager()
        )
        self.cancel_event = threading.Event()

        # スタイル設定（モダンなclamテーマを使用）
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # メニューバーの構築
        self._create_menu()

        # 全体レイアウト用のメインフレーム
        main_frame = ttk.Frame(root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 各UIセクションの構築
        self._create_mode_section(main_frame)
        self._create_input_section(main_frame)
        self._create_output_section(main_frame)
        self._create_action_buttons(main_frame)
        self._create_log_section(main_frame)

    def _create_menu(self) -> None:
        """メニューバーを構築します。"""
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)

        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="ヘルプ(H)", menu=self.help_menu, underline=4)
        self.help_menu.add_command(
            label="更新を確認(&U)...",
            command=self.check_for_updates,
        )

    def _create_mode_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """動作モード選択セクションを構築します。"""
        mode_lf = ttk.LabelFrame(parent, text=" 処理モードの選択 ", padding="12")
        mode_lf.pack(fill=tk.X, pady=(0, 10))

        self.mode_var = tk.StringVar(value="file")

        self.file_rb = ttk.Radiobutton(
            mode_lf,
            text="単一のPDFファイルから抽出",
            variable=self.mode_var,
            value="file",
            command=self.toggle_mode,
        )
        self.file_rb.grid(row=0, column=0, padx=15, sticky=tk.W)

        self.folder_rb = ttk.Radiobutton(
            mode_lf,
            text="フォルダ内のすべてのPDFファイルから一括抽出",
            variable=self.mode_var,
            value="folder",
            command=self.toggle_mode,
        )
        self.folder_rb.grid(row=0, column=1, padx=15, sticky=tk.W)

        return mode_lf

    def _create_input_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """入力元設定セクションを構築します。"""
        input_lf = ttk.LabelFrame(parent, text=" 入力元の設定 ", padding="12")
        input_lf.pack(fill=tk.X, pady=(0, 10))

        # 単一ファイル入力行
        self.file_label = ttk.Label(input_lf, text="対象PDFファイル:")
        self.file_label.grid(row=0, column=0, sticky=tk.W, pady=5)

        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(
            input_lf, textvariable=self.file_path_var, width=50
        )
        self.file_entry.grid(
            row=0, column=1, padx=(5, 10), pady=5, sticky=tk.EW
        )

        self.file_btn = ttk.Button(
            input_lf, text="ファイル選択...", command=self.select_pdf_file
        )
        self.file_btn.grid(row=0, column=2, pady=5)

        # フォルダ入力行
        self.folder_label = ttk.Label(input_lf, text="対象フォルダ:")
        self.folder_label.grid(row=1, column=0, sticky=tk.W, pady=5)

        self.folder_path_var = tk.StringVar()
        self.folder_entry = ttk.Entry(
            input_lf,
            textvariable=self.folder_path_var,
            width=50,
            state="disabled",
        )
        self.folder_entry.grid(
            row=1, column=1, padx=(5, 10), pady=5, sticky=tk.EW
        )

        self.folder_btn = ttk.Button(
            input_lf,
            text="フォルダ選択...",
            command=self.select_input_folder,
            state="disabled",
        )
        self.folder_btn.grid(row=1, column=2, pady=5)

        input_lf.columnconfigure(1, weight=1)
        return input_lf

    def _create_output_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """保存先設定セクションを構築します。"""
        output_lf = ttk.LabelFrame(parent, text=" 保存先の設定 ", padding="12")
        output_lf.pack(fill=tk.X, pady=(0, 15))

        self.output_label = ttk.Label(output_lf, text="保存先フォルダ:")
        self.output_label.grid(row=0, column=0, sticky=tk.W, pady=5)

        self.output_path_var = tk.StringVar(value="")
        self.output_combobox = ttk.Combobox(
            output_lf, textvariable=self.output_path_var, width=48
        )
        self.output_combobox.grid(
            row=0, column=1, padx=(5, 10), pady=5, sticky=tk.EW
        )

        self.output_btn = ttk.Button(
            output_lf, text="フォルダ選択...", command=self.select_output_folder
        )
        self.output_btn.grid(row=0, column=2, pady=5)

        # 履歴の読み込みと設定（ConfigManager を利用）
        history = self.config_manager.load_history()
        self.output_combobox["values"] = history

        # 抽出完了後の自動オープン用チェックボックス
        self.open_dir_var = tk.BooleanVar(value=True)
        self.open_dir_cb = ttk.Checkbutton(
            output_lf,
            text="抽出完了後に保存先フォルダを開く",
            variable=self.open_dir_var,
        )
        self.open_dir_cb.grid(
            row=1, column=0, columnspan=3, sticky=tk.W, pady=(5, 0)
        )

        output_lf.columnconfigure(1, weight=1)
        return output_lf

    def _create_action_buttons(self, parent: ttk.Frame) -> ttk.Frame:
        """実行コントロールボタン群を構築します。"""
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        # ボタンのカスタムスタイル設定
        self.style.configure(
            "Accent.TButton",
            font=("Helvetica", 10, "bold"),
            background="#2a9d8f",
            foreground="white",
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", "#21867a"), ("disabled", "#dcdcdc")],
            foreground=[("disabled", "#a1a1a1")],
        )

        self.style.configure(
            "Danger.TButton",
            font=("Helvetica", 10, "bold"),
            background="#e76f51",
            foreground="white",
        )
        self.style.map(
            "Danger.TButton",
            background=[("active", "#cf5e43"), ("disabled", "#dcdcdc")],
            foreground=[("disabled", "#a1a1a1")],
        )

        # 画像抽出を実行ボタン
        self.run_btn = ttk.Button(
            btn_frame,
            text="画像抽出を実行",
            command=self.start_extraction,
            style="Accent.TButton",
        )
        self.run_btn.grid(row=0, column=0, padx=5, sticky=tk.EW, ipady=6)

        # 中断ボタン
        self.cancel_btn = ttk.Button(
            btn_frame,
            text="中断",
            command=self.cancel_extraction,
            style="Danger.TButton",
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=1, padx=5, sticky=tk.EW, ipady=6)

        # 終了ボタン
        self.exit_btn = ttk.Button(
            btn_frame,
            text="終了",
            command=self.safe_exit,
            style="Danger.TButton",
        )
        self.exit_btn.grid(row=0, column=2, padx=5, sticky=tk.EW, ipady=6)

        # カラムの幅を配分する
        btn_frame.columnconfigure(0, weight=2)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)
        return btn_frame

    def _create_log_section(self, parent: ttk.Frame) -> ttk.LabelFrame:
        """進捗プログレスバーおよびログ表示エリアを構築します。"""
        # プログレスバーの配置
        self.progress_bar = ttk.Progressbar(
            parent, orient="horizontal", mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        self.progressbar = self.progress_bar

        log_lf = ttk.LabelFrame(parent, text=" 処理ログ ", padding="5")
        log_lf.pack(fill=tk.BOTH, expand=True)

        self.log_area = ScrolledText(
            log_lf, wrap=tk.WORD, height=12, font=("Consolas", 10)
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.config(state="disabled")
        return log_lf

    # ------------------
    # スレッドセーフな通知機構
    # ------------------
    def safe_log(self, message: str) -> None:
        """ログエリアへのメッセージ追記をメインスレッドで安全に実行します。"""
        self.root.after(0, self._append_log, message)

    def _append_log(self, message: str) -> None:
        """ログエリアにメッセージを追記します（メインスレッド実行用）。"""
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def safe_showinfo(self, title: str, message: str) -> None:
        """情報ダイアログをメインスレッドで安全に表示します。"""
        self.root.after(0, messagebox.showinfo, title, message)

    def safe_showerror(self, title: str, message: str) -> None:
        """エラーダイアログをメインスレッドで安全に表示します。"""
        self.root.after(0, messagebox.showerror, title, message)

    def safe_update_progress(self, current: int, total: int) -> None:
        """プログレスバーの進捗更新をメインスレッドで安全に実行します。"""
        self.root.after(0, self._update_progress, current, total)

    def _update_progress(self, current: int, total: int) -> None:
        """プログレスバーの進捗値を更新します（メインスレッド実行用）。"""
        if total > 0:
            self.progress_bar["value"] = (current / total) * 100
        else:
            self.progress_bar["value"] = 0

    def _reset_progress(self) -> None:
        """プログレスバーを 0% にリセットします。"""
        self.progress_bar["value"] = 0

    def _on_extraction_finished(self) -> None:
        """抽出処理終了時（完了・中断・エラー）にボタン状態を復帰します。"""
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")

    def cancel_extraction(self) -> None:
        """実行中の画像抽出処理の中断を要求します。"""
        self.cancel_event.set()
        self.safe_log("\n中断要求を送信しました。現在の処理が完了次第停止します...")
        self.cancel_btn.config(state="disabled")

    def log(self, message: str) -> None:
        """ログエリアにメッセージを追記します（safe_log へのエイリアス）。"""
        self.safe_log(message)

    def clear_log(self) -> None:
        """ログエリアの内容を消去します。"""
        self.log_area.config(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state="disabled")

    # ------------------
    # UI イベントハンドラ
    # ------------------
    def toggle_mode(self) -> None:
        """動作モード（単一ファイル／フォルダ一括）の変更に合わせてUIコントロールを有効／無効化します。"""
        mode = self.mode_var.get()
        if mode == "file":
            self.file_entry.config(state="normal")
            self.file_btn.config(state="normal")
            self.folder_entry.config(state="disabled")
            self.folder_btn.config(state="disabled")
        else:
            self.file_entry.config(state="disabled")
            self.file_btn.config(state="disabled")
            self.folder_entry.config(state="normal")
            self.folder_btn.config(state="normal")

    def select_pdf_file(self) -> None:
        """ファイル選択ダイアログを表示し、対象PDFファイルを設定します。"""
        file_path = filedialog.askopenfilename(
            title="PDFファイルを選択",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")],
        )
        if file_path:
            self.file_path_var.set(os.path.normpath(file_path))

    def select_input_folder(self) -> None:
        """フォルダ選択ダイアログを表示し、対象入力フォルダを設定します。"""
        folder_path = filedialog.askdirectory(title="入力フォルダを選択")
        if folder_path:
            self.folder_path_var.set(os.path.normpath(folder_path))

    def select_output_folder(self) -> None:
        """フォルダ選択ダイアログを表示し、保存先フォルダを設定します。"""
        folder_path = filedialog.askdirectory(title="保存先フォルダを選択")
        if folder_path:
            self.output_path_var.set(os.path.normpath(folder_path))

    def start_extraction(self) -> None:
        """入力値を検証した上で、別スレッドで画像抽出処理を開始します。"""
        mode = self.mode_var.get()
        output_dir = self.output_path_var.get().strip()

        if not output_dir:
            messagebox.showerror("エラー", "保存先フォルダを指定してください。")
            return

        if mode == "file":
            pdf_path = self.file_path_var.get().strip()
            if not pdf_path:
                messagebox.showerror("エラー", "対象PDFファイルを選択してください。")
                return
            if not os.path.exists(pdf_path):
                messagebox.showerror(
                    "エラー", f"指定されたPDFファイルが見つかりません:\n{pdf_path}"
                )
                return
            target_args = (pdf_path, output_dir)
            target_func = self.run_file_extraction
        else:
            input_dir = self.folder_path_var.get().strip()
            if not input_dir:
                messagebox.showerror("エラー", "対象フォルダを選択してください。")
                return
            if not os.path.exists(input_dir):
                messagebox.showerror(
                    "エラー", f"指定された対象フォルダが見つかりません:\n{input_dir}"
                )
                return
            target_args = (input_dir, output_dir)
            target_func = self.run_folder_extraction

        # UI操作のロック（二重起動防止）および中断イベントの初期化
        self.cancel_event.clear()
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self._reset_progress()
        self.clear_log()

        # 履歴の保存とコンボボックス更新
        self.config_manager.add_history(output_dir)
        self.output_combobox["values"] = self.config_manager.history

        # 画像抽出スレッドの起動
        thread = threading.Thread(target=target_func, args=target_args)
        thread.daemon = True
        thread.start()

    def run_file_extraction(self, pdf_path: str, output_dir: str) -> None:
        """単一ファイル画像抽出処理を実行します（ワーカースレッドで実行）。"""
        self.safe_log("=== PDF画像抽出処理を開始します ===")
        self.safe_log(f"対象PDF: {pdf_path}")
        self.safe_log(f"保存先 : {output_dir}\n")

        try:
            count = extract_images_from_pdf(
                pdf_path,
                output_dir,
                progress_callback=self.safe_update_progress,
                cancel_event=self.cancel_event,
            )
            self.safe_log("\n抽出が完了しました。")
            self.safe_log(f"保存された画像の総数: {count}枚")
            self.safe_showinfo(
                "完了", f"画像の抽出が完了しました。\n保存された画像: {count}枚"
            )
            if self.open_dir_var.get():
                try:
                    os.startfile(output_dir)
                except Exception as folder_err:
                    self.safe_log(
                        f"保存先フォルダを開けませんでした: {str(folder_err)}"
                    )
        except ExtractionCancelledError:
            self.safe_log("\n処理がユーザーによって中断されました。")
            self.safe_log("※ 中断までに抽出された画像は保存先フォルダに残されています。")
            self.safe_showinfo("中断", "画像抽出処理が中断されました。")
        except Exception as e:
            self.safe_log(f"\nエラーが発生しました:\n{str(e)}")
            self.safe_showerror(
                "エラー", f"画像抽出中にエラーが発生しました:\n{str(e)}"
            )
        finally:
            self.root.after(0, self._on_extraction_finished)

    def run_folder_extraction(self, input_dir: str, output_dir: str) -> None:
        """フォルダ一括画像抽出処理を実行します（ワーカースレッドで実行）。"""
        self.safe_log("=== フォルダ一括画像抽出処理を開始します ===")
        self.safe_log(f"入力フォルダ: {input_dir}")
        self.safe_log(f"保存先フォルダ: {output_dir}\n")

        try:
            processed_files, total_extracted = extract_images_from_folder(
                input_dir,
                output_dir,
                log_callback=self.safe_log,
                file_progress_callback=self.safe_update_progress,
                page_progress_callback=self.safe_update_progress,
                cancel_event=self.cancel_event,
            )
            self.safe_log("\n一括処理が完了しました。")
            self.safe_log(f"処理されたPDFファイル数: {processed_files}件")
            self.safe_log(f"保存された画像の総数  : {total_extracted}枚")
            self.safe_showinfo(
                "完了",
                f"一括処理が完了しました。\n処理ファイル数: {processed_files}件\n保存画像数: {total_extracted}枚",
            )
            if self.open_dir_var.get():
                try:
                    os.startfile(output_dir)
                except Exception as folder_err:
                    self.safe_log(
                        f"保存先フォルダを開けませんでした: {str(folder_err)}"
                    )
        except ExtractionCancelledError:
            self.safe_log("\n処理がユーザーによって中断されました。")
            self.safe_log("※ 中断までに抽出された画像は保存先フォルダに残されています。")
            self.safe_showinfo("中断", "画像抽出処理が中断されました。")
        except Exception as e:
            self.safe_log(f"\nエラーが発生しました:\n{str(e)}")
            self.safe_showerror(
                "エラー", f"一括処理中にエラーが発生しました:\n{str(e)}"
            )
        finally:
            self.root.after(0, self._on_extraction_finished)

    def safe_exit(self) -> None:
        """画像抽出中の場合は確認ダイアログを表示した上で、安全にアプリを終了します。"""
        if str(self.run_btn["state"]) == tk.DISABLED:
            if not messagebox.askyesno(
                "確認", "画像抽出処理が実行中ですが、強制終了しますか？"
            ):
                return
            self.cancel_event.set()
        self.root.destroy()

    # ------------------
    # 互換性維持用メソッド
    # ------------------
    def load_config(self) -> list[str]:
        """設定ファイルから履歴フォルダのリストを読み込みます（互換用）。"""
        return self.config_manager.load_history()

    def save_config(self) -> None:
        """現在の保存先フォルダを履歴に追加し、設定ファイルに保存します（互換用）。"""
        output_dir = self.output_path_var.get().strip()
        if output_dir:
            self.config_manager.add_history(output_dir)
            self.output_combobox["values"] = self.config_manager.history

    # ------------------
    # アップデート確認処理
    # ------------------
    def check_for_updates(self) -> None:
        """別スレッドでGitHub Releasesから最新バージョン情報を確認します。"""
        self.safe_log("最新バージョンの確認中...")
        thread = threading.Thread(target=self._run_check_updates, daemon=True)
        thread.start()

    def _run_check_updates(self) -> None:
        """ワーカースレッドでリリース情報を取得します。"""
        try:
            info = fetch_latest_release_info(
                owner=GITHUB_REPO_OWNER,
                repo=GITHUB_REPO_NAME,
                current_version=__version__,
            )
            self._safe_dispatch(self._on_check_updates_result, info)
        except Exception as e:
            logger.exception("更新確認中に例外が発生しました")
            self._safe_dispatch(self._on_check_updates_error, str(e))

    def _safe_dispatch(self, callback, *args) -> None:
        """スレッドセーフにメインスレッドでコールバックをスケジュールまたは実行します。"""
        try:
            self.root.after(0, callback, *args)
        except (RuntimeError, tk.TclError):
            try:
                callback(*args)
            except Exception as e:
                logger.warning("safe_dispatch コールバックの実行に失敗しました: %s", e)

    def _on_check_updates_result(self, info: UpdateInfo | None) -> None:
        """更新確認結果をUIに反映します（メインスレッド実行用）。"""
        if info is None:
            self.safe_log("更新情報の取得に失敗しました。")
            messagebox.showerror(
                "更新確認",
                "更新情報の取得に失敗しました。\nネットワーク接続を確認してください。",
            )
            return

        if is_newer_version(__version__, info.latest_version):
            self.safe_log(
                f"新しいバージョンが見つかりました: v{info.latest_version} (現在: v{__version__})"
            )
            UpdateDialog(self.root, info)
        else:
            self.safe_log(f"現在のバージョンは最新です。(v{__version__})")
            messagebox.showinfo(
                "更新確認",
                f"お使いのバージョン (v{__version__}) は最新です。",
            )

    def _on_check_updates_error(self, err_msg: str) -> None:
        """更新確認時のエラーダイアログを表示します（メインスレッド実行用）。"""
        self.safe_log(f"更新確認エラー: {err_msg}")
        messagebox.showerror(
            "更新確認エラー",
            f"更新確認中にエラーが発生しました:\n{err_msg}",
        )

