"""設定ファイル (config.json) の管理を行うモジュール。

アプリケーションの設定（出力先フォルダの履歴など）の永続化と読み込みを提供します。
GUI（Tkinter）に依存せず、ポータブル動作および権限制限環境に対応しています。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

APP_DIR_NAME = "pdf-image-extractor"
CONFIG_FILENAME = "config.json"
HISTORY_KEY = "history_output_dirs"
DEFAULT_MAX_HISTORY = 3

logger = logging.getLogger(__name__)


def get_app_dir() -> str:
    """アプリケーションの実行ディレクトリを取得します。

    PyInstaller 等でフリーズされている場合は実行可能ファイル (exe) のあるディレクトリ、
    通常実行時は本スクリプトが存在するディレクトリを返します。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_dir_writable(path: str | os.PathLike[str]) -> bool:
    """指定されたディレクトリへの書き込み権限があるか検証します。

    一時ファイル (.write_test) の作成および削除を試行して判定します。
    """
    test_file = os.path.join(path, ".write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("")
        try:
            os.remove(test_file)
        except OSError:
            pass
        return True
    except OSError:
        return False


def get_appdata_dir() -> str:
    """APPDATA 配下のアプリケーション専用ディレクトリのパスを取得します。

    環境変数 APPDATA が存在しない場合はユーザーのホームディレクトリ配下を使用します。
    """
    base_dir = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base_dir, APP_DIR_NAME)


def resolve_config_path(app_dir: str | None = None) -> str:
    """設定ファイル (config.json) の適切なパスを解決して返します。

    指定ディレクトリ（省略時は get_app_dir()）に書き込み可能な場合はその直下の config.json、
    書き込み不可の場合は get_appdata_dir() のディレクトリを作成してその配下の config.json を返します。
    """
    if app_dir is None:
        app_dir = get_app_dir()

    if is_dir_writable(app_dir):
        return os.path.join(app_dir, CONFIG_FILENAME)

    appdata_dir = get_appdata_dir()
    os.makedirs(appdata_dir, exist_ok=True)
    return os.path.join(appdata_dir, CONFIG_FILENAME)


class ConfigManager:
    """設定ファイルの読み書きおよび設定状態を保持・管理するクラス。"""

    def __init__(
        self,
        config_path: str | None = None,
        max_history: int = DEFAULT_MAX_HISTORY,
    ) -> None:
        """ConfigManager を初期化します。

        Args:
            config_path: 設定ファイルのパス。None の場合は resolve_config_path() で自動解決します。
            max_history: 保持する履歴の最大件数（1 以上）。

        Raises:
            ValueError: max_history が 1 未満の場合。
        """
        if max_history < 1:
            raise ValueError(f"max_history must be at least 1, got {max_history}")

        self._config_path: str = (
            config_path if config_path is not None else resolve_config_path()
        )
        self._max_history: int = max_history
        self._history: list[str] = []

    @property
    def config_path(self) -> str:
        """設定ファイルのパスを取得します。"""
        return self._config_path

    @property
    def max_history(self) -> int:
        """履歴の最大保持件数を取得します。"""
        return self._max_history

    @property
    def history(self) -> list[str]:
        """内部で保持している出力先ディレクトリ履歴のコピーを取得します。"""
        return list(self._history)

    def load_history(self) -> list[str]:
        """設定ファイルから履歴を読み込み、内部状態を更新して返します。

        ファイルが存在しない、または読み取り・パースに失敗した場合は
        内部状態を空にして空リストを返します。
        """
        if not os.path.exists(self._config_path):
            self._history = []
            return []

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(
                "設定ファイルの読み込みに失敗しました: %s (path: %s)",
                e,
                self._config_path,
            )
            self._history = []
            return []

        if not isinstance(data, dict):
            logger.warning(
                "設定ファイルの最上位が dict ではありません: %s (path: %s)",
                type(data),
                self._config_path,
            )
            self._history = []
            return []

        raw_history = data.get(HISTORY_KEY, [])
        if not isinstance(raw_history, list):
            logger.warning(
                "設定ファイル内の %s が list ではありません: %s (path: %s)",
                HISTORY_KEY,
                type(raw_history),
                self._config_path,
            )
            self._history = []
            return []

        # 空白除去・正規化・非空文字列のみ抽出
        valid_paths = [
            os.path.normpath(item.strip())
            for item in raw_history
            if isinstance(item, str) and item.strip()
        ]
        # 順序を保ったまま重複排除
        unique_paths = list(dict.fromkeys(valid_paths))
        self._history = unique_paths[: self._max_history]
        return list(self._history)

    def add_history(self, path: str) -> None:
        """指定されたパスを履歴の先頭に追加し、設定ファイルに保存します。

        前後の空白を除いて空文字列になるパスは無視されます。

        Args:
            path: 追加するディレクトリパス。
        """
        stripped_path = path.strip()
        if not stripped_path:
            return

        normed_path = os.path.normpath(stripped_path)
        if normed_path in self._history:
            self._history.remove(normed_path)
        self._history.insert(0, normed_path)
        self._history = self._history[: self._max_history]

        self._save()

    def _save(self) -> None:
        """現在の履歴状態を設定ファイルに保存します。

        既存のファイルが読めて最上位が dict の場合は、他のキーを維持したまま
        HISTORY_KEY のみを書き換えます。
        書き込み失敗時は警告ログを出力し、例外は送出しません。
        """
        data: dict[str, Any] = {}
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                data = {}

        data[HISTORY_KEY] = list(self._history)

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except OSError as e:
            logger.warning(
                "設定ファイルの保存に失敗しました: %s (path: %s)",
                e,
                self._config_path,
            )
