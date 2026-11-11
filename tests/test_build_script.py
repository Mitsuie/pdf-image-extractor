"""
ビルド & パッケージングスクリプト (build.py) の単体テスト
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from build import (
    build_installer,
    clean_build_artifacts,
    find_iscc_exe,
    generate_sha256_file,
    main,
    parse_args,
    run_tests,
    safe_rmtree,
)


class TestBuildScript(unittest.TestCase):
    """build.py の各機能に対する単体テスト"""

    def test_generate_sha256_file_format_and_content(self):
        """生成される .sha256 ファイルの命名と sha256sum 互換フォーマットを検証"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_exe = tmp_path / "PDFImageExtractor.exe"
            content = b"PDF-Image-Extractor binary mock content 1234567890"
            dummy_exe.write_bytes(content)

            sha_path = generate_sha256_file(dummy_exe)

            # ファイル名検証: <元ファイル名>.sha256
            self.assertEqual(sha_path.name, "PDFImageExtractor.exe.sha256")
            self.assertTrue(sha_path.exists())

            # 内容検証: "<小文字64桁hex> *<ファイル名>\n"
            sha_text = sha_path.read_text(encoding="utf-8")
            expected_hex = hashlib.sha256(content).hexdigest().lower()
            expected_line = f"{expected_hex} *{dummy_exe.name}\n"
            self.assertEqual(sha_text, expected_line)

    def test_generate_sha256_file_chunked_reading(self):
        """複数チャンク（1MB超）にまたがるデータでもハッシュが正確に計算されることを検証"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_exe = tmp_path / "large_file.exe"
            # 2.5MB のデータを作成
            content = b"A" * (1024 * 1024 * 2 + 512 * 1024)
            dummy_exe.write_bytes(content)

            sha_path = generate_sha256_file(dummy_exe)
            sha_text = sha_path.read_text(encoding="utf-8")

            expected_hex = hashlib.sha256(content).hexdigest().lower()
            self.assertEqual(sha_text, f"{expected_hex} *{dummy_exe.name}\n")

    def test_generate_sha256_file_non_existent(self):
        """存在しないファイルまたはディレクトリを渡した場合に FileNotFoundError を送出すること"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            non_existent = tmp_path / "not_found.exe"
            with self.assertRaises(FileNotFoundError):
                generate_sha256_file(non_existent)

            dir_target = tmp_path / "a_directory"
            dir_target.mkdir()
            with self.assertRaises(FileNotFoundError):
                generate_sha256_file(dir_target)

    def test_safe_rmtree_and_clean_build_artifacts(self):
        """一時ディレクトリの安全削除および clean_build_artifacts の動作検証"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            build_dir = root / "build"
            dist_dir = root / "dist"
            build_dir.mkdir()
            dist_dir.mkdir()
            (build_dir / "temp.txt").write_text("temp", encoding="utf-8")
            (dist_dir / "dummy.exe").write_bytes(b"dummy")

            self.assertTrue(build_dir.exists())
            self.assertTrue(dist_dir.exists())

            clean_build_artifacts(root)

            self.assertFalse(build_dir.exists())
            self.assertFalse(dist_dir.exists())

    def test_safe_rmtree_non_existent(self):
        """存在しないパスに対する safe_rmtree が例外なく正常終了すること"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            non_existent = Path(tmp_dir) / "ghost"
            safe_rmtree(non_existent)

    @patch("subprocess.run")
    def test_run_tests_success(self, mock_run):
        """自動テストが成功した場合（returncode 0）に True を返すこと"""
        mock_run.return_value = MagicMock(returncode=0)
        self.assertTrue(run_tests("dummy_python"))
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_tests_failure(self, mock_run):
        """自動テストが失敗した場合（returncode != 0）に False を返すこと"""
        mock_run.return_value = MagicMock(returncode=1)
        self.assertFalse(run_tests("dummy_python"))

    @patch("subprocess.run")
    def test_run_tests_exception(self, mock_run):
        """自動テスト実行中に例外が発生した場合に False を返すこと"""
        mock_run.side_effect = OSError("pytest not found")
        self.assertFalse(run_tests("dummy_python"))

    def test_parse_args_defaults(self):
        """引数パースのデフォルト値検証"""
        args = parse_args([])
        self.assertFalse(args.skip_tests)
        self.assertEqual(args.output_dir, "dists")
        self.assertEqual(args.spec, "PDFImageExtractor.spec")
        self.assertFalse(args.installer)
        self.assertFalse(args.skip_pyinstaller)
        self.assertEqual(args.iss, "installer.iss")

    def test_parse_args_custom(self):
        """引数パースのカスタム値検証"""
        args = parse_args([
            "--skip-tests",
            "--output-dir", "custom_dist",
            "--spec", "custom.spec",
            "--installer",
            "--skip-pyinstaller",
            "--iss", "custom.iss",
        ])
        self.assertTrue(args.skip_tests)
        self.assertEqual(args.output_dir, "custom_dist")
        self.assertEqual(args.spec, "custom.spec")
        self.assertTrue(args.installer)
        self.assertTrue(args.skip_pyinstaller)
        self.assertEqual(args.iss, "custom.iss")

    @patch("build.run_tests", return_value=False)
    def test_main_aborts_on_test_failure(self, mock_run_tests):
        """自動テスト失敗時に main が終了コード 1 で中断すること"""
        code = main([])
        self.assertEqual(code, 1)

    @patch("build.run_tests", return_value=True)
    def test_main_aborts_on_missing_spec(self, mock_run_tests):
        """spec ファイルが存在しない場合に main が終了コード 1 で中断すること"""
        code = main(["--spec", "non_existent_file.spec"])
        self.assertEqual(code, 1)

    @patch("shutil.which")
    def test_find_iscc_exe_found_in_path(self, mock_which):
        """PATH 上に ISCC.exe が存在する場合にそのパスを返すこと"""
        mock_which.side_effect = lambda cmd: r"C:\Tools\ISCC.exe" if "iscc" in cmd.lower() else None
        res = find_iscc_exe()
        self.assertEqual(res, Path(r"C:\Tools\ISCC.exe"))

    @patch("pathlib.Path.is_file")
    @patch("pathlib.Path.exists")
    @patch("shutil.which", return_value=None)
    def test_find_iscc_exe_found_in_default_locations(self, mock_which, mock_exists, mock_is_file):
        """PATH になくてもデフォルトのインストール先に存在する場合にそのパスを返すこと"""
        mock_exists.return_value = True
        mock_is_file.return_value = True
        res = find_iscc_exe()
        self.assertIsNotNone(res)
        self.assertIn("Inno Setup 6", str(res))

    @patch("pathlib.Path.is_file", return_value=False)
    @patch("pathlib.Path.exists", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_find_iscc_exe_not_found(self, mock_which, mock_exists, mock_is_file):
        """いずれの候補にも見つからない場合は None を返すこと"""
        res = find_iscc_exe()
        self.assertIsNone(res)

    def test_find_iscc_exe_live_environment(self):
        """実機環境で Inno Setup 6 が検出できることの検証（ローカル実行環境用）"""
        res = find_iscc_exe()
        self.assertIsNotNone(res)
        self.assertTrue(res.exists())

    def test_build_installer_missing_files(self):
        """iscc または iss ファイルが存在しない場合に FileNotFoundError を送出すること"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_iscc = tmp_path / "ISCC.exe"
            dummy_iss = tmp_path / "installer.iss"

            # iscc が存在しない
            with self.assertRaises(FileNotFoundError):
                build_installer(dummy_iscc, dummy_iss, "1.1.0", tmp_path)

            dummy_iscc.write_text("dummy", encoding="utf-8")
            # iss が存在しない
            with self.assertRaises(FileNotFoundError):
                build_installer(dummy_iscc, dummy_iss, "1.1.0", tmp_path)

    @patch("build.generate_sha256_file")
    @patch("subprocess.run")
    def test_build_installer_success(self, mock_run, mock_sha256):
        """Inno Setup コンパイルが正常終了し、インストーラーとチェックサムが生成されること"""
        mock_run.return_value = MagicMock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_iscc = tmp_path / "ISCC.exe"
            dummy_iss = tmp_path / "installer.iss"
            dummy_iscc.write_text("dummy", encoding="utf-8")
            dummy_iss.write_text("dummy", encoding="utf-8")

            # 生成される予定の exe をモック作成
            version = "1.1.0"
            expected_exe = tmp_path / f"PDFImageExtractor_Setup_v{version}.exe"
            expected_exe.write_bytes(b"dummy installer binary")

            res_path = build_installer(dummy_iscc, dummy_iss, version, tmp_path)
            self.assertEqual(res_path, expected_exe)
            mock_sha256.assert_called_once_with(expected_exe)

    @patch("subprocess.run")
    def test_build_installer_failure(self, mock_run):
        """Inno Setup コンパイルがエラーとなった場合に RuntimeError を送出すること"""
        mock_run.return_value = MagicMock(returncode=1)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_iscc = tmp_path / "ISCC.exe"
            dummy_iss = tmp_path / "installer.iss"
            dummy_iscc.write_text("dummy", encoding="utf-8")
            dummy_iss.write_text("dummy", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                build_installer(dummy_iscc, dummy_iss, "1.1.0", tmp_path)

    @patch("build.run_tests", return_value=True)
    def test_main_skip_pyinstaller_missing_exe(self, mock_run_tests):
        """--skip-pyinstaller 指定時に既存の exe が存在しない場合エラーコード 1 で中断すること"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            code = main(["--skip-tests", "--skip-pyinstaller", "--output-dir", tmp_dir])
            self.assertEqual(code, 1)

    @patch("build.find_iscc_exe", return_value=None)
    @patch("build.run_tests", return_value=True)
    def test_main_installer_missing_iscc(self, mock_run_tests, mock_find_iscc):
        """--installer 指定時に ISCC が見つからない場合エラーコード 1 で中断すること"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            dummy_exe = tmp_path / "PDFImageExtractor.exe"
            dummy_exe.write_bytes(b"dummy")

            code = main(["--skip-tests", "--skip-pyinstaller", "--output-dir", tmp_dir])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
