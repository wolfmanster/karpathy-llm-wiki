"""Keep pytest's generated data inside this project."""

from pathlib import Path


def pytest_configure(config):
    project_root = Path(__file__).resolve().parents[1]
    base = project_root / "tests" / ".testdata" / "pytest"
    base.parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(base)
