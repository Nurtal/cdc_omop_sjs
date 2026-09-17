"""Construction de petits jeux OMOP à la main, pour les tests du seam 1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sjs_phenotype import omop


def ecrire_jeu(
    dossier: Path,
    person: list[dict[str, Any]],
    measurement: list[dict[str, Any]] | None = None,
) -> Path:
    """Écrit un jeu OMOP minimal, une table Parquet par nom de table."""
    omop.ecrire_table(dossier, "person", person)
    omop.ecrire_table(dossier, "measurement", measurement or [])
    return dossier
