"""Écriture et lecture des tables OMOP : ce qui manque doit se voir, pas se taire."""

from __future__ import annotations

from pathlib import Path

import pytest

from sjs_phenotype import omop


def _personne(**surcharges: object) -> dict[str, object]:
    ligne: dict[str, object] = {
        "person_id": 1,
        "gender_concept_id": 8532,
        "year_of_birth": 1970,
    }
    ligne.update(surcharges)
    return ligne


def test_une_colonne_manquante_est_refusee(tmp_path: Path) -> None:
    ligne = _personne()
    del ligne["year_of_birth"]

    with pytest.raises(ValueError, match="year_of_birth"):
        omop.ecrire_table(tmp_path, "person", [ligne])


def test_une_colonne_inconnue_est_refusee(tmp_path: Path) -> None:
    """Une clé mal orthographiée écrirait des NULL, donc des « non documenté » (ADR-0005)."""
    ligne = _personne()
    del ligne["gender_concept_id"]
    ligne["gender_concept_ID"] = 8532

    with pytest.raises(ValueError, match="gender_concept_ID"):
        omop.ecrire_table(tmp_path, "person", [ligne])


def test_un_chemin_avec_apostrophe_fonctionne(tmp_path: Path) -> None:
    dossier = tmp_path / "hôpital d'Ys"
    chemin = omop.ecrire_table(dossier, "person", [_personne()])

    assert omop.lire(chemin) == [_personne()]
