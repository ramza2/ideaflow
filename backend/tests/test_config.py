"""Configuration path tests."""

import os
from pathlib import Path

from app.core.config import env_file_path, repo_root


def test_repo_root_points_at_ideaflow_repository() -> None:
    root = repo_root()
    assert root.is_absolute()
    assert (root / "backend").is_dir()
    assert (root / "frontend").is_dir()
    assert (root / ".env.example").is_file()


def test_env_file_path_is_repository_root_dotenv() -> None:
    path = env_file_path()
    assert path.is_absolute()
    assert path.name == ".env"
    assert path.parent == repo_root()


def test_env_file_path_independent_of_working_directory(tmp_path: Path) -> None:
    expected = env_file_path().resolve()
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert env_file_path().resolve() == expected

        os.chdir(repo_root() / "backend")
        assert env_file_path().resolve() == expected
    finally:
        os.chdir(original_cwd)
