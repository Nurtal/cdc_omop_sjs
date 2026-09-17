"""Fixtures partagées."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def dossier_omop(tmp_path: Path) -> Path:
    dossier = tmp_path / "omop"
    dossier.mkdir()
    return dossier
