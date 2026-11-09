"""ConfigManager の単体テスト。"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest

import config_manager
from config_manager import (
    APP_DIR_NAME,
    CONFIG_FILENAME,
    DEFAULT_MAX_HISTORY,
    HISTORY_KEY,
    ConfigManager,
    get_app_dir,
    is_dir_writable,
    resolve_config_path,
)


class TestConfigPathResolution:
    """設定ファイルパス解決のテスト。"""

    def test_is_dir_writable_success(self, tmp_path: Path) -> None:
        """書き込み可能なディレクトリで True を返し、テストファイルが残らないこと。"""
        assert is_dir_writable(tmp_path) is True
        assert not (tmp_path / ".write_test").exists()

    def test_is_dir_writable_nonexistent(self, tmp_path: Path) -> None:
        """存在しないディレクトリでは False を返すこと。"""
        nonexistent = tmp_path / "nonexistent"
        assert is_dir_writable(nonexistent) is False

    def test_resolve_config_path_writable(self, tmp_path: Path) -> None:
        """書き込み可能なディレクトリの場合、その直下の config.json を返すこと。"""
        expected = str(tmp_path / CONFIG_FILENAME)
        assert resolve_config_path(str(tmp_path)) == expected

    def test_resolve_config_path_appdata_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ディレクトリ書き込み不可の場合、%APPDATA% 配下にディレクトリを作成してパスを返すこと。"""
        appdata_dir = tmp_path / "appdata"
        monkeypatch.setattr(config_manager, "is_dir_writable", lambda _path: False)
        monkeypatch.setenv("APPDATA", str(appdata_dir))

        result = resolve_config_path(str(tmp_path))
        expected_dir = appdata_dir / APP_DIR_NAME
        expected_file = expected_dir / CONFIG_FILENAME

        assert result == str(expected_file)
        assert expected_dir.is_dir()

    def test_resolve_config_path_home_fallback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """APPDATA が未設定の場合、ホームディレクトリ配下にフォールバックすること。"""
        monkeypatch.setattr(config_manager, "is_dir_writable", lambda _path: False)
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))

        result = resolve_config_path(str(tmp_path))
        expected_dir = tmp_path / APP_DIR_NAME
        expected_file = expected_dir / CONFIG_FILENAME

        assert result == str(expected_file)
        assert expected_dir.is_dir()

    def test_get_app_dir_frozen(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """frozen 状態（exe化）の場合、sys.executable のディレクトリを返すこと。"""
        fake_exe = tmp_path / "bin" / "app.exe"
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(fake_exe))

        assert get_app_dir() == str(fake_exe.parent)

    def test_get_app_dir_normal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """通常スクリプト実行の場合、config_manager.py のディレクトリを返すこと。"""
        monkeypatch.delattr(sys, "frozen", raising=False)
        expected = os.path.dirname(os.path.abspath(config_manager.__file__))
        assert get_app_dir() == expected


class TestConfigManagerLoad:
    """ConfigManager の読み込み機能のテスト。"""

    def test_load_history_no_file(self, tmp_path: Path) -> None:
        """設定ファイルが存在しない場合は空リストを返すこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))
        assert cm.load_history() == []
        assert cm.history == []

    def test_load_history_broken_json(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """壊れた JSON の場合は空リストを返し WARNING がログ出力されること。"""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("{broken json content", encoding="utf-8")
        cm = ConfigManager(config_path=str(config_file))

        with caplog.at_level(logging.WARNING):
            assert cm.load_history() == []
        assert "設定ファイルの読み込みに失敗しました" in caplog.text

    def test_load_history_root_not_dict(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """最上位要素が dict ではない場合、空リストを返すこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text(json.dumps(["item1", "item2"]), encoding="utf-8")
        cm = ConfigManager(config_path=str(config_file))

        with caplog.at_level(logging.WARNING):
            assert cm.load_history() == []
        assert "dict ではありません" in caplog.text

    def test_load_history_key_not_list(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """キーの値が list ではない場合、空リストを返すこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text(
            json.dumps({HISTORY_KEY: "string_value"}), encoding="utf-8"
        )
        cm = ConfigManager(config_path=str(config_file))

        with caplog.at_level(logging.WARNING):
            assert cm.load_history() == []
        assert "list ではありません" in caplog.text

    def test_load_history_filtering_and_normalization(self, tmp_path: Path) -> None:
        """不正値・空白が除外され、normpath および重複排除された先頭 3 件が返ること。"""
        config_file = tmp_path / CONFIG_FILENAME
        p1 = "C:/path/a"
        p2 = "C:/path/a/"  # normpath すると p1 と重複
        p3 = "D:/path/b"
        p4 = "E:/path/c"
        p5 = "F:/path/d"
        raw_list = [p1, "", "   ", None, 12345, p2, p3, p4, p5]

        config_file.write_text(
            json.dumps({HISTORY_KEY: raw_list}), encoding="utf-8"
        )
        cm = ConfigManager(config_path=str(config_file))
        result = cm.load_history()

        expected = [
            os.path.normpath(p1),
            os.path.normpath(p3),
            os.path.normpath(p4),
        ]
        assert result == expected
        assert cm.history == expected
        assert len(result) == 3


class TestConfigManagerAddAndSave:
    """ConfigManager の追加・保存機能のテスト。"""

    def test_add_history_new_path(self, tmp_path: Path) -> None:
        """新しいパスが先頭に追加され、ファイルにも正しく保存されること。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))

        cm.add_history("C:/target/dir")
        expected = [os.path.normpath("C:/target/dir")]

        assert cm.history == expected
        assert config_file.exists()

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data[HISTORY_KEY] == expected

    def test_add_history_moves_existing_to_front(self, tmp_path: Path) -> None:
        """既存のパスを追加した場合、先頭に移動し重複しないこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))

        cm.add_history("C:/path1")
        cm.add_history("C:/path2")
        cm.add_history("C:/path1")

        expected = [os.path.normpath("C:/path1"), os.path.normpath("C:/path2")]
        assert cm.history == expected

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data[HISTORY_KEY] == expected

    def test_add_history_max_limit(self, tmp_path: Path) -> None:
        """上限を超えた場合、古い要素が削除されて最大 3 件になること。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file), max_history=3)

        cm.add_history("C:/path1")
        cm.add_history("C:/path2")
        cm.add_history("C:/path3")
        cm.add_history("C:/path4")

        expected = [
            os.path.normpath("C:/path4"),
            os.path.normpath("C:/path3"),
            os.path.normpath("C:/path2"),
        ]
        assert cm.history == expected

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data[HISTORY_KEY] == expected

    def test_custom_max_history_and_invalid(self, tmp_path: Path) -> None:
        """max_history のカスタマイズおよび 1 未満での ValueError 送出を検証。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file), max_history=5)
        assert cm.max_history == 5

        for i in range(7):
            cm.add_history(f"C:/dir{i}")
        assert len(cm.history) == 5

        with pytest.raises(ValueError):
            ConfigManager(max_history=0)
        with pytest.raises(ValueError):
            ConfigManager(max_history=-1)

    def test_add_history_empty_ignored(self, tmp_path: Path) -> None:
        """空文字列や空白のみのパスは無視されファイルも作成されないこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))

        cm.add_history("")
        cm.add_history("   ")

        assert cm.history == []
        assert not config_file.exists()

    def test_add_history_japanese_characters(self, tmp_path: Path) -> None:
        """日本語を含むパスがエスケープされずに保存され、読み直しても一致すること。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))
        jp_path = "C:/テスト/画像出力先"

        cm.add_history(jp_path)

        raw_text = config_file.read_text(encoding="utf-8")
        assert "\\u" not in raw_text
        assert "画像出力先" in raw_text

        cm2 = ConfigManager(config_path=str(config_file))
        assert cm2.load_history() == [os.path.normpath(jp_path)]

    def test_save_preserves_other_keys(self, tmp_path: Path) -> None:
        """既存の設定ファイルにある別キーを上書きせず保持すること。"""
        config_file = tmp_path / CONFIG_FILENAME
        initial_data = {
            "other_setting": 12345,
            "theme": "dark",
            HISTORY_KEY: ["C:/old"],
        }
        config_file.write_text(
            json.dumps(initial_data, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )

        cm = ConfigManager(config_path=str(config_file))
        cm.load_history()
        cm.add_history("C:/new")

        with open(config_file, "r", encoding="utf-8") as f:
            saved = json.load(f)

        assert saved["other_setting"] == 12345
        assert saved["theme"] == "dark"
        assert saved[HISTORY_KEY] == [
            os.path.normpath("C:/new"),
            os.path.normpath("C:/old"),
        ]

    def test_add_history_save_failure_logged(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """保存先ディレクトリが存在しない場合でも例外を出さず、履歴は更新され WARNING が記録されること。"""
        nonexistent_dir = tmp_path / "not_existing_folder"
        config_file = nonexistent_dir / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))

        with caplog.at_level(logging.WARNING):
            cm.add_history("C:/path1")

        assert cm.history == [os.path.normpath("C:/path1")]
        assert "設定ファイルの保存に失敗しました" in caplog.text

    def test_history_immutability(self, tmp_path: Path) -> None:
        """history プロパティの戻り値を変更しても内部の履歴が変更されないこと。"""
        config_file = tmp_path / CONFIG_FILENAME
        cm = ConfigManager(config_path=str(config_file))
        cm.add_history("C:/path1")

        copy_history = cm.history
        copy_history.append("C:/injected")

        assert cm.history == [os.path.normpath("C:/path1")]
