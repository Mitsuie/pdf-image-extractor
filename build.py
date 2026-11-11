"""
PDF-Image-Extractor ビルド & パッケージングスクリプト (build.py)

PyInstaller による単一実行可能ファイル (.exe) の生成、
Inno Setup によるインストーラー (Setup.exe) の生成、
完全性照合用の SHA-256 チェックサム (.sha256) 自動生成、
および成果物の dists/ フォルダへの配置を一括して実行します。
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import time

from version import __version__


def remove_readonly(func, path, excinfo):
    """Windowsの読み取り専用属性を強制解除して削除を再試行するハンドラ"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def safe_rmtree(path: Path | str, retries: int = 5, delay: float = 0.5) -> None:
    """Windows環境のファイルロックや読み取り専用属性に対応した堅牢なディレクトリ削除"""
    p = Path(path)
    if not p.exists():
        return

    for _ in range(retries):
        try:
            if sys.version_info >= (3, 12):
                def _onexc(func, filepath, err):
                    try:
                        os.chmod(filepath, stat.S_IWRITE)
                        func(filepath)
                    except Exception:
                        pass
                shutil.rmtree(p, onexc=_onexc)
            else:
                shutil.rmtree(p, onerror=remove_readonly)

            if not p.exists():
                return
        except Exception:
            pass
        time.sleep(delay)

    if p.exists():
        try:
            shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass


def clean_build_artifacts(root_dir: Path | None = None) -> None:
    """一時ビルド生成物（build/ ディレクトリおよび dist/ ディレクトリ）をクリーンアップする"""
    root = root_dir if root_dir is not None else Path(__file__).resolve().parent
    safe_rmtree(root / "build")
    safe_rmtree(root / "dist")


def generate_sha256_file(file_path: Path) -> Path:
    """
    対象ファイルの SHA-256 ハッシュを計算し、
    sha256sum 互換フォーマット (<64桁hex> *<ファイル名>\n) のチェックサムファイルを生成する。
    """
    if not file_path.exists() or not file_path.is_file():
        raise FileNotFoundError(f"File not found for checksum calculation: {file_path}")

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            hasher.update(chunk)

    sha256_hex = hasher.hexdigest().lower()
    sha256_path = file_path.with_name(f"{file_path.name}.sha256")
    sha256_path.write_text(f"{sha256_hex} *{file_path.name}\n", encoding="utf-8")
    return sha256_path


def find_iscc_exe() -> Path | None:
    """Inno Setup コンパイラ (ISCC.exe) の実行可能ファイルパスを探索する"""
    for cmd in ("ISCC.exe", "iscc"):
        found = shutil.which(cmd)
        if found:
            return Path(found)

    candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def build_installer(iscc_path: Path, iss_path: Path, version: str, output_dir: Path) -> Path:
    """
    Inno Setup を呼び出してインストーラー実行ファイル (.exe) をビルドし、
    その SHA-256 チェックサムファイルを生成してインストーラーのパスを返す。
    """
    if not iscc_path.exists():
        raise FileNotFoundError(f"ISCC executable not found: {iscc_path}")
    if not iss_path.exists():
        raise FileNotFoundError(f"Inno Setup script not found: {iss_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(iscc_path),
        f"/DMyAppVersion={version}",
        f"/O{output_dir}",
        str(iss_path),
    ]
    print(f"[INFO] Inno Setup によるインストーラー作成を実行中 ({iss_path.name}, v{version})...")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise RuntimeError(f"Inno Setup build failed with return code {res.returncode}")

    installer_name = f"PDFImageExtractor_Setup_v{version}.exe"
    installer_path = output_dir / installer_name
    if not installer_path.exists():
        raise FileNotFoundError(f"Generated installer not found: {installer_path}")

    print("[INFO] インストーラーの SHA-256 チェックサムファイルを生成中...")
    generate_sha256_file(installer_path)

    return installer_path


def run_tests(python_exe: str | None = None) -> bool:
    """ビルド前に pytest による自動テストを実行する"""
    exe = python_exe or sys.executable
    print("[INFO] ビルド前自動テストを実行中 (pytest -q)...")
    try:
        res = subprocess.run([exe, "-m", "pytest", "-q"])
        if res.returncode != 0:
            print(f"[ERROR] テストが失敗しました（終了コード: {res.returncode}）。ビルドを中断します。")
            return False
        print("[INFO] 自動テストがすべてパスしました。")
        return True
    except Exception as e:
        print(f"[ERROR] テストの実行中に例外が発生しました: {e}")
        return False


def kill_existing_process(exe_name: str = "PDFImageExtractor.exe") -> None:
    """実行中の同名プロセスがあれば終了を試行する（Windowsのファイルロック回避）"""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", exe_name, "/T"],
                capture_output=True,
                check=False,
            )
        except Exception:
            pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """コマンドライン引数を解析する"""
    parser = argparse.ArgumentParser(
        description="PDF-Image-Extractor ビルド & パッケージングスクリプト"
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="ビルド前の自動テスト (pytest) の実行をスキップします。",
    )
    parser.add_argument(
        "--output-dir",
        default="dists",
        help="ビルド成果物 (.exe および .sha256) の出力先ディレクトリ（デフォルト: dists）",
    )
    parser.add_argument(
        "--spec",
        default="PDFImageExtractor.spec",
        help="使用する PyInstaller spec ファイル（デフォルト: PDFImageExtractor.spec）",
    )
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Inno Setup によるインストーラー (Setup.exe) も合わせてビルドします。",
    )
    parser.add_argument(
        "--skip-pyinstaller",
        action="store_true",
        help="PyInstaller ビルドをスキップし、既存の実行ファイルを使用してインストーラーのみビルドします。",
    )
    parser.add_argument(
        "--iss",
        default="installer.iss",
        help="使用する Inno Setup 定義ファイル（デフォルト: installer.iss）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_dir = Path(__file__).resolve().parent
    os.chdir(root_dir)

    print("=" * 60)
    print("  PDF-Image-Extractor 自動ビルド & パッケージング")
    print("=" * 60)

    # 1. 自動テスト実行
    if not args.skip_tests:
        if not run_tests():
            return 1
    else:
        print("[INFO] --skip-tests が指定されたため、自動テストをスキップします。")

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = root_dir / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    target_exe = out_dir / "PDFImageExtractor.exe"

    if not args.skip_pyinstaller:
        # 2. specファイルの存在確認
        spec_path = root_dir / args.spec
        if not spec_path.exists():
            print(f"[ERROR] Spec ファイルが見つかりません: {spec_path}")
            return 1

        # 3. 実行中プロセスの停止と一時成果物の事前クリーンアップ
        print("[INFO] 以前のビルド成果物・一時ディレクトリをクリーンアップ中...")
        kill_existing_process()
        clean_build_artifacts(root_dir)

        # 4. PyInstaller ビルド実行
        print(f"[INFO] PyInstaller によるビルドを実行中 ({spec_path.name})...")
        build_cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--clean"]
        try:
            build_res = subprocess.run(build_cmd)
            if build_res.returncode != 0:
                print(f"[ERROR] PyInstaller ビルドが失敗しました（終了コード: {build_res.returncode}）。")
                return build_res.returncode
        except Exception as e:
            print(f"[ERROR] PyInstaller の起動に失敗しました: {e}")
            return 1

        # 5. 生成された exe の存在確認
        dist_exe = root_dir / "dist" / "PDFImageExtractor.exe"
        if not dist_exe.exists():
            print(f"[ERROR] ビルド成果物の exe が見つかりません: {dist_exe}")
            return 1

        # 6. 出力先ディレクトリへの配置
        print(f"[INFO] 成果物を配置中: {target_exe}")
        try:
            shutil.copy2(dist_exe, target_exe)
        except Exception as e:
            print(f"[ERROR] 成果物のコピーに失敗しました ({dist_exe} -> {target_exe}): {e}")
            return 1

        # 7. SHA-256 チェックサムファイルの生成
        print("[INFO] SHA-256 チェックサムファイルを生成中...")
        try:
            target_sha256 = generate_sha256_file(target_exe)
        except Exception as e:
            print(f"[ERROR] チェックサム生成に失敗しました: {e}")
            return 1

        # 8. 中間成果物 (build/) のクリーンアップ
        print("[INFO] 中間ビルドディレクトリ (build/) をクリーンアップ中...")
        safe_rmtree(root_dir / "build")
    else:
        print("[INFO] --skip-pyinstaller が指定されたため、PyInstaller ビルドをスキップします。")
        if not target_exe.exists():
            print(f"[ERROR] 既存の実行ファイルが見つかりません: {target_exe}")
            return 1
        target_sha256 = target_exe.with_name(f"{target_exe.name}.sha256")
        if not target_sha256.exists():
            print("[INFO] SHA-256 チェックサムファイルを生成中...")
            try:
                target_sha256 = generate_sha256_file(target_exe)
            except Exception as e:
                print(f"[ERROR] チェックサム生成に失敗しました: {e}")
                return 1

    # 9. Inno Setup によるインストーラー作成
    installer_exe: Path | None = None
    installer_sha256: Path | None = None
    if args.installer or args.skip_pyinstaller:
        print("\n" + "-" * 60)
        print("  Inno Setup インストーラービルド")
        print("-" * 60)

        iscc_path = find_iscc_exe()
        if iscc_path is None:
            print("[ERROR] Inno Setup コンパイラ (ISCC.exe) が見つかりません。")
            print("        Inno Setup 6 がインストールされているか確認してください。")
            return 1

        iss_path = root_dir / args.iss
        if not iss_path.exists():
            print(f"[ERROR] Inno Setup スクリプトが見つかりません: {iss_path}")
            return 1

        try:
            from version import __version__
            installer_exe = build_installer(
                iscc_path=iscc_path,
                iss_path=iss_path,
                version=__version__,
                output_dir=out_dir,
            )
            installer_sha256 = installer_exe.with_name(f"{installer_exe.name}.sha256")
        except Exception as e:
            print(f"[ERROR] インストーラーのビルドに失敗しました: {e}")
            return 1

    # 10. 完了報告とハッシュ値表示
    print("=" * 60)
    print("  ビルドが正常に完了しました！")
    sha_text = target_sha256.read_text(encoding="utf-8").strip()
    file_size_mb = target_exe.stat().st_size / (1024 * 1024)
    print(f"  [ポータブル版]")
    print(f"  - 実行ファイル: {target_exe} ({file_size_mb:.2f} MB)")
    print(f"  - チェックサム: {target_sha256}")
    print(f"  - SHA-256 内容: {sha_text}")

    if installer_exe and installer_sha256:
        inst_sha_text = installer_sha256.read_text(encoding="utf-8").strip()
        inst_size_mb = installer_exe.stat().st_size / (1024 * 1024)
        print(f"  [インストーラー版]")
        print(f"  - インストーラー: {installer_exe} ({inst_size_mb:.2f} MB)")
        print(f"  - チェックサム: {installer_sha256}")
        print(f"  - SHA-256 内容: {inst_sha_text}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
