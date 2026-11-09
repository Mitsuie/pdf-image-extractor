"""PDF画像抽出ツールのエントリーポイント。"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from tkinter import messagebox
from typing import Any

from app_window import AppWindow

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """ロギング設定を初期化します。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def handle_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: Any,
) -> None:
    """未捕捉の例外をログに出力し、ユーザーにエラーダイアログを表示します。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical(
        "未捕捉の例外が発生しました",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    try:
        messagebox.showerror(
            "予期せぬエラー",
            f"予期せぬエラーが発生しました:\n{exc_value}",
        )
    except Exception:
        # Tkinter のウィンドウが利用できない場合などのフォールバック
        pass


def main() -> None:
    """アプリケーションのメインエントリーポイント。"""
    setup_logging()
    sys.excepthook = handle_uncaught_exception

    root = tk.Tk()
    _app = AppWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
