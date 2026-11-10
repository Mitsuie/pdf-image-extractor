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
    clean_build_artifacts,
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

    def test_parse_args_custom(self):
        """引数パースのカスタム値検証"""
        args = parse_args(["--skip-tests", "--output-dir", "custom_dist", "--spec", "custom.spec"])
        self.assertTrue(args.skip_tests)
        self.assertEqual(args.output_dir, "custom_dist")
        self.assertEqual(args.spec, "custom.spec")

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


if __name__ == "__main__":
    unittest.main()

