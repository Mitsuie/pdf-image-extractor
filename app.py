import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

# バックエンド処理のインポート
from extractor import extract_images_from_pdf, extract_images_from_folder

class PDFImageExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF画像抽出ツール (PyMuPDF)")
        self.root.geometry("680x580")
        self.root.minsize(600, 500)
        
        # スタイル設定（モダンなclamテーマを使用）
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 全体レイアウト用のパディング設定
        main_frame = ttk.Frame(root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # ------------------
        # 1. 動作モード選択セクション
        # ------------------
        mode_lf = ttk.LabelFrame(main_frame, text=" 処理モードの選択 ", padding="12")
        mode_lf.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="file")
        
        file_rb = ttk.Radiobutton(
            mode_lf, 
            text="単一のPDFファイルから抽出", 
            variable=self.mode_var, 
            value="file",
            command=self.toggle_mode
        )
        file_rb.grid(row=0, column=0, padx=15, sticky=tk.W)
        
        folder_rb = ttk.Radiobutton(
            mode_lf, 
            text="フォルダ内のすべてのPDFファイルから一括抽出", 
            variable=self.mode_var, 
            value="folder",
            command=self.toggle_mode
        )
        folder_rb.grid(row=0, column=1, padx=15, sticky=tk.W)
        
        # ------------------
        # 2. 入力設定セクション
        # ------------------
        input_lf = ttk.LabelFrame(main_frame, text=" 入力元の設定 ", padding="12")
        input_lf.pack(fill=tk.X, pady=(0, 10))
        
        # 単一ファイル入力行
        self.file_label = ttk.Label(input_lf, text="対象PDFファイル:")
        self.file_label.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(input_lf, textvariable=self.file_path_var, width=50)
        self.file_entry.grid(row=0, column=1, padx=(5, 10), pady=5, sticky=tk.EW)
        
        self.file_btn = ttk.Button(input_lf, text="ファイル選択...", command=self.select_pdf_file)
        self.file_btn.grid(row=0, column=2, pady=5)
        
        # フォルダ入力行
        self.folder_label = ttk.Label(input_lf, text="対象フォルダ:")
        self.folder_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        
        self.folder_path_var = tk.StringVar()
        self.folder_entry = ttk.Entry(input_lf, textvariable=self.folder_path_var, width=50, state="disabled")
        self.folder_entry.grid(row=1, column=1, padx=(5, 10), pady=5, sticky=tk.EW)
        
        self.folder_btn = ttk.Button(input_lf, text="フォルダ選択...", command=self.select_input_folder, state="disabled")
        self.folder_btn.grid(row=1, column=2, pady=5)
        
        input_lf.columnconfigure(1, weight=1)
        
        # ------------------
        # 3. 保存先設定セクション
        # ------------------
        output_lf = ttk.LabelFrame(main_frame, text=" 保存先の設定 ", padding="12")
        output_lf.pack(fill=tk.X, pady=(0, 15))
        
        self.output_label = ttk.Label(output_lf, text="保存先フォルダ:")
        self.output_label.grid(row=0, column=0, sticky=tk.W, pady=5)
        
        self.output_path_var = tk.StringVar()
        self.output_entry = ttk.Entry(output_lf, textvariable=self.output_path_var, width=50)
        self.output_entry.grid(row=0, column=1, padx=(5, 10), pady=5, sticky=tk.EW)
        
        self.output_btn = ttk.Button(output_lf, text="フォルダ選択...", command=self.select_output_folder)
        self.output_btn.grid(row=0, column=2, pady=5)
        
        output_lf.columnconfigure(1, weight=1)
        
        # ------------------
        # 4. 実行コントロール
        # ------------------
        # ボタン格納用のフレーム（均等配置用）
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 15))
        
        # ボタンのカスタムスタイル設定
        self.style.configure(
            "Accent.TButton", 
            font=("Helvetica", 10, "bold"), 
            background="#2a9d8f", 
            foreground="white"
        )
        self.style.map(
            "Accent.TButton", 
            background=[("active", "#21867a"), ("disabled", "#dcdcdc")],
            foreground=[("disabled", "#a1a1a1")]
        )
        
        self.style.configure(
            "Danger.TButton", 
            font=("Helvetica", 10, "bold"), 
            background="#e76f51", 
            foreground="white"
        )
        self.style.map(
            "Danger.TButton", 
            background=[("active", "#cf5e43")]
        )
        
        # 画像抽出を実行ボタン
        self.run_btn = ttk.Button(btn_frame, text="画像抽出を実行", command=self.start_extraction, style="Accent.TButton")
        self.run_btn.grid(row=0, column=0, padx=10, sticky=tk.EW, ipady=6)
        
        # 終了ボタン
        self.exit_btn = ttk.Button(btn_frame, text="終了", command=self.safe_exit, style="Danger.TButton")
        self.exit_btn.grid(row=0, column=1, padx=10, sticky=tk.EW, ipady=6)
        
        # カラムの幅を均等にする
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        # ------------------
        # 5. ログ表示エリア
        # ------------------
        log_lf = ttk.LabelFrame(main_frame, text=" 処理ログ ", padding="5")
        log_lf.pack(fill=tk.BOTH, expand=True)
        
        self.log_area = ScrolledText(log_lf, wrap=tk.WORD, height=12, font=("Consolas", 10))
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self.log_area.config(state="disabled")
        
    def toggle_mode(self):
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
            
    def select_pdf_file(self):
        file_path = filedialog.askopenfilename(
            title="PDFファイルを選択",
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(os.path.normpath(file_path))
            
    def select_input_folder(self):
        folder_path = filedialog.askdirectory(title="入力フォルダを選択")
        if folder_path:
            self.folder_path_var.set(os.path.normpath(folder_path))
            
    def select_output_folder(self):
        folder_path = filedialog.askdirectory(title="保存先フォルダを選択")
        if folder_path:
            self.output_path_var.set(os.path.normpath(folder_path))
            
    def log(self, message):
        """ログエリアにメッセージを追記します（スレッドセーフ対応）"""
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")
        
    def clear_log(self):
        self.log_area.config(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state="disabled")
        
    def start_extraction(self):
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
                messagebox.showerror("エラー", f"指定されたPDFファイルが見つかりません:\n{pdf_path}")
                return
            target_args = (pdf_path, output_dir)
            target_func = self.run_file_extraction
        else:
            input_dir = self.folder_path_var.get().strip()
            if not input_dir:
                messagebox.showerror("エラー", "対象フォルダを選択してください。")
                return
            if not os.path.exists(input_dir):
                messagebox.showerror("エラー", f"指定された対象フォルダが見つかりません:\n{input_dir}")
                return
            target_args = (input_dir, output_dir)
            target_func = self.run_folder_extraction
            
        # UI操作のロック（二重起動防止）
        self.run_btn.config(state="disabled")
        self.clear_log()
        
        # 画像抽出スレッドの起動
        thread = threading.Thread(target=target_func, args=target_args)
        thread.daemon = True
        thread.start()
        
    def run_file_extraction(self, pdf_path, output_dir):
        """単一ファイル画像抽出処理を実行します（別スレッド）"""
        self.log("=== PDF画像抽出処理を開始します ===")
        self.log(f"対象PDF: {pdf_path}")
        self.log(f"保存先 : {output_dir}\n")
        
        try:
            count = extract_images_from_pdf(pdf_path, output_dir)
            self.log(f"\n抽出が完了しました。")
            self.log(f"保存された画像の総数: {count}枚")
            messagebox.showinfo("完了", f"画像の抽出が完了しました。\n保存された画像: {count}枚")
        except Exception as e:
            self.log(f"\nエラーが発生しました:\n{str(e)}")
            messagebox.showerror("エラー", f"画像抽出中にエラーが発生しました:\n{str(e)}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state="normal"))
            
    def run_folder_extraction(self, input_dir, output_dir):
        """フォルダ一括画像抽出処理を実行します（別スレッド）"""
        self.log("=== フォルダ一括画像抽出処理を開始します ===")
        self.log(f"入力フォルダ: {input_dir}")
        self.log(f"保存先フォルダ: {output_dir}\n")
        
        try:
            processed_files, total_extracted = extract_images_from_folder(
                input_dir, output_dir, log_callback=self.log
            )
            self.log(f"\n一括処理が完了しました。")
            self.log(f"処理されたPDFファイル数: {processed_files}件")
            self.log(f"保存された画像の総数  : {total_extracted}枚")
            messagebox.showinfo("完了", f"一括処理が完了しました。\n処理ファイル数: {processed_files}件\n保存画像数: {total_extracted}枚")
        except Exception as e:
            self.log(f"\nエラーが発生しました:\n{str(e)}")
            messagebox.showerror("エラー", f"一括処理中にエラーが発生しました:\n{str(e)}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state="normal"))

    def safe_exit(self):
        """画像抽出中の場合は確認ダイアログを表示した上で、安全にアプリを終了します。"""
        if str(self.run_btn['state']) == tk.DISABLED:
            if not messagebox.askyesno("確認", "画像抽出処理が実行中ですが、強制終了しますか？"):
                return
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PDFImageExtractorApp(root)
    root.mainloop()
