"""Unit tests that do not require a live database."""

import pytest

from app.db.base import Base
from app.db.defaults import DEFAULT_WORKSPACE_CATEGORIES, DEFAULT_WORKSPACE_STAGES
import app.models  # noqa: F401


EXPECTED_TABLES = {
    "users",
    "workspaces",
    "workspace_members",
    "workspace_stages",
    "workspace_categories",
    "tags",
    "ideas",
    "idea_tags",
    "idea_shares",
    "idea_participants",
}


def test_settings_exposes_database_url_field(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url == ""
    get_settings.cache_clear()


def test_metadata_contains_core_tables() -> None:
    assert EXPECTED_TABLES.issubset(set(Base.metadata.tables.keys()))


def test_default_workspace_stages() -> None:
    stages = DEFAULT_WORKSPACE_STAGES
    assert len(stages) == 10
    slugs = [s["slug"] for s in stages]
    orders = [s["sort_order"] for s in stages]
    assert len(set(slugs)) == 10
    assert len(set(orders)) == 10
    defaults = [s for s in stages if s["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["slug"] == "memo"
    terminals = {s["slug"] for s in stages if s["is_terminal"]}
    assert terminals == {"completed", "discarded"}


def test_default_workspace_categories() -> None:
    cats = DEFAULT_WORKSPACE_CATEGORIES
    assert len(cats) == 8
    slugs = [c["slug"] for c in cats]
    orders = [c["sort_order"] for c in cats]
    assert len(set(slugs)) == 8
    assert len(set(orders)) == 8


def test_personal_workspace_default_name() -> None:
    from app.services.workspace import PERSONAL_WORKSPACE_NAME

    assert PERSONAL_WORKSPACE_NAME == "내 작업공간"
