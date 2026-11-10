"""GitHub Releases API を利用した自動アップデートシステムモジュール。

ゼロ外部依存（urllib, json, hashlib などの標準ライブラリのみ）で動作し、
最新リリースのチェック、アセットのダウンロード、SHA-256完全性検証、および新プロセスの起動を行います。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


class UpdateVerificationError(Exception):
    """ダウンロードしたアセットのSHA-256検証に失敗した場合の例外。"""

    pass


class UpdateCancelledError(Exception):
    """ダウンロード処理がキャンセルされた場合の例外。"""

    pass


@dataclass
class UpdateInfo:
    """GitHub Release の更新情報データクラス。"""

    current_version: str
    latest_version: str
    release_name: str
    release_notes: str
    html_url: str
    exe_download_url: str | None
    exe_name: str | None
    exe_size: int | None
    expected_sha256: str | None


def parse_version_tuple(v_str: str | None) -> tuple[int, ...]:
    """バージョン文字列を整数のタプルに変換します。

    例:
        "1.0.0" -> (1, 0, 0)
        "v1.2.3" -> (1, 2, 3)
        "v2.0" -> (2, 0)
        "v1.0.0-beta" -> (1, 0, 0)
        None, "" -> ()

    Args:
        v_str: バージョン文字列。

    Returns:
        整数のタプル。
    """
    if not v_str:
        return ()

    cleaned = v_str.strip().lstrip("vV")
    # ハイフンやプラスなどのビルドメタデータ・プレリリース識別子を除去
    base = re.split(r"[-+]", cleaned)[0]

    parts: list[int] = []
    for part in base.split("."):
        part = part.strip()
        if part.isdigit():
            parts.append(int(part))
        else:
            match = re.match(r"^(\d+)", part)
            if match:
                parts.append(int(match.group(1)))
            break
    return tuple(parts)


def compare_versions(v1: str, v2: str) -> int:
    """2つのバージョン文字列をセマンティック比較します。

    Args:
        v1: 比較対象バージョン1（例: 現在のバージョン）。
        v2: 比較対象バージョン2（例: 最新バージョン）。

    Returns:
        v1 < v2 なら -1
        v1 == v2 なら 0
        v1 > v2 なら 1
    """
    t1 = parse_version_tuple(v1)
    t2 = parse_version_tuple(v2)

    max_len = max(len(t1), len(t2))
    p1 = t1 + (0,) * (max_len - len(t1))
    p2 = t2 + (0,) * (max_len - len(t2))

    if p1 < p2:
        return -1
    if p1 > p2:
        return 1
    return 0


def is_newer_version(current: str, latest: str) -> bool:
    """最新バージョンが現在のバージョンより新しいかどうかを判定します。

    Args:
        current: 現在のバージョン文字列。
        latest: 最新バージョン文字列。

    Returns:
        latest が current より新しい場合 True。
    """
    return compare_versions(current, latest) < 0


def parse_sha256_text(text: str, target_filename: str | None = None) -> str | None:
    """sha256 ファイルの内容から 64文字のハッシュ値を抽出します。

    `<hash> *<filename>` または `<hash>  <filename>` または `<hash>` 単体の形式に対応します。

    Args:
        text: sha256ファイルの内容テキスト。
        target_filename: 対象とするファイル名（指定時はそのファイル名を含む行を優先）。

    Returns:
        小文字の64文字16進ハッシュ文字列。見つからない場合は None。
    """
    lines = text.strip().splitlines()
    hex64_pattern = re.compile(r"\b([a-fA-F0-9]{64})\b")

    # target_filename が指定されている場合、一致する行を優先探索
    if target_filename:
        target_base = os.path.basename(target_filename).lower()
        for line in lines:
            if target_base in line.lower():
                match = hex64_pattern.search(line)
                if match:
                    return match.group(1).lower()

    # 一致する行がない場合、最初に見つかった64文字hexを返す
    for line in lines:
        match = hex64_pattern.search(line)
        if match:
            return match.group(1).lower()

    return None


def fetch_latest_release_info(
    owner: str,
    repo: str,
    current_version: str,
    timeout_sec: float = 5.0,
) -> UpdateInfo | None:
    """GitHub Releases API から最新リリースの情報を取得します。

    Args:
        owner: リポジトリ所有者（例: "Mitsuie"）。
        repo: リポジトリ名（例: "pdf-image-extractor"）。
        current_version: 現在のアプリケーションバージョン。
        timeout_sec: 通信タイムアウト秒数。

    Returns:
        UpdateInfo インスタンス。取得失敗時は None。
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {
        "User-Agent": f"{repo}-AppUpdater/{current_version}",
        "Accept": "application/vnd.github.v3+json",
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logger.warning("最新リリースの取得に失敗しました: %s", e)
        return None

    raw_tag = data.get("tag_name", "")
    latest_version = raw_tag.lstrip("vV") if raw_tag else ""
    release_name = data.get("name") or raw_tag
    release_notes = data.get("body") or ""
    html_url = data.get("html_url") or f"https://github.com/{owner}/{repo}/releases/latest"

    assets = data.get("assets", [])
    exe_asset: dict | None = None
    sha256_asset: dict | None = None

    for asset in assets:
        name = asset.get("name", "")
        lower_name = name.lower()
        if lower_name.endswith(".exe") and exe_asset is None:
            exe_asset = asset
        elif lower_name.endswith((".sha256", ".sha256.txt")) and sha256_asset is None:
            sha256_asset = asset

    exe_download_url = exe_asset.get("browser_download_url") if exe_asset else None
    exe_name = exe_asset.get("name") if exe_asset else None
    exe_size = exe_asset.get("size") if exe_asset else None

    expected_sha256: str | None = None
    if sha256_asset and sha256_asset.get("browser_download_url"):
        sha_url = sha256_asset["browser_download_url"]
        sha_req = urllib.request.Request(sha_url, headers=headers)
        try:
            with urllib.request.urlopen(sha_req, timeout=timeout_sec) as sha_resp:
                sha_text = sha_resp.read().decode("utf-8", errors="ignore")
                expected_sha256 = parse_sha256_text(sha_text, exe_name)
        except Exception as e:
            logger.warning("SHA-256アセットの取得に失敗しました: %s", e)

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_name=release_name,
        release_notes=release_notes,
        html_url=html_url,
        exe_download_url=exe_download_url,
        exe_name=exe_name,
        exe_size=exe_size,
        expected_sha256=expected_sha256,
    )


def download_file(
    url: str,
    dest_path: str,
    expected_sha256: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    chunk_size: int = 65536,
) -> None:
    """指定されたURLからファイルをストリーミングダウンロードし、SHA-256完全性を検証します。

    Args:
        url: ダウンロード元URL。
        dest_path: 保存先ファイルパス。
        expected_sha256: 期待されるSHA-256ハッシュ（小文字・64文字）。検証しない場合は None。
        progress_callback: (downloaded_bytes, total_bytes) を受け取る進捗コールバック。
        cancel_event: 中断フラグ用 threading.Event。
        chunk_size: 1回の読み込みチャンクサイズ。

    Raises:
        UpdateCancelledError: ユーザーにより中断された場合。
        UpdateVerificationError: SHA-256ハッシュが不一致だった場合（ファイルは破棄されます）。
        Exception: ネットワークエラー等のその他例外。
    """
    if cancel_event is not None and cancel_event.is_set():
        raise UpdateCancelledError("ダウンロードが開始前に中断されました。")

    dest_dir = os.path.dirname(os.path.abspath(dest_path))
    if dest_dir:
        os.makedirs(dest_dir, exist_ok=True)

    temp_path = dest_path + ".tmp"
    headers = {"User-Agent": "pdf-image-extractor-AppUpdater"}
    req = urllib.request.Request(url, headers=headers)

    hasher = hashlib.sha256()
    downloaded_bytes = 0

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            content_length = resp.headers.get("Content-Length")
            total_size = (
                int(content_length)
                if content_length and content_length.isdigit()
                else 0
            )

            with open(temp_path, "wb") as f:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise UpdateCancelledError("ダウンロードが中断されました。")

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    hasher.update(chunk)
                    f.write(chunk)
                    downloaded_bytes += len(chunk)

                    if progress_callback is not None:
                        progress_callback(downloaded_bytes, total_size)

        # SHA-256 完全性検証
        computed_hash = hasher.hexdigest().lower()
        if expected_sha256:
            clean_expected = expected_sha256.strip().lower()
            if computed_hash != clean_expected:
                raise UpdateVerificationError(
                    f"SHA-256ハッシュが一致しません。(期待値: {clean_expected}, 計算値: {computed_hash})"
                )

        # 検証成功時に最終保存先へアトミック配置
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        os.replace(temp_path, dest_path)

    except Exception:
        # エラー発生時（中断・検証失敗・通信エラー等）は一時ファイルおよび不正ファイルを破棄
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        raise


def launch_executable(exe_path: str) -> None:
    """指定された実行ファイルを親プロセスから独立した新しいプロセスグループで起動します。

    Args:
        exe_path: 起動する実行ファイルの絶対または相対パス。
    """
    creationflags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [os.path.abspath(exe_path)],
        creationflags=creationflags,
        close_fds=True,
    )
