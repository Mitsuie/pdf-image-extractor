import shutil
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def sample_pdf(repo_root: Path) -> Path:
    return repo_root / "example_files" / "pdf_image_test.pdf"


@pytest.fixture
def copy_sample_pdf(sample_pdf: Path):
    def _copy(dst_dir: Path | str, filename: str | None = None) -> Path:
        dst = Path(dst_dir)
        dst.mkdir(parents=True, exist_ok=True)
        name = filename if filename is not None else sample_pdf.name
        target = dst / name
        shutil.copyfile(sample_pdf, target)
        return target

    return _copy

