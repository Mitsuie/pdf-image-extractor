"""後方互換性のためのラッパーモジュール。

本スクリプト (app.py) は非推奨となりました。今後は main.py を実行してください。
"""

from __future__ import annotations

import warnings

from app_window import AppWindow
from main import main

# 非推奨警告を発行
warnings.warn(
    "app.py is deprecated; please use main.py instead.",
    DeprecationWarning,
    stacklevel=2,
)

# 過去のインポートとの互換性用エイリアス
PDFImageExtractorApp = AppWindow

if __name__ == "__main__":
    main()
