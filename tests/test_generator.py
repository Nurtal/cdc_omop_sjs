"""L'État réel et le Processus d'observation sont deux tirages indépendants (ADR-0001)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.generator import Scenario, generer


def _etat_reel(scenario: Scenario, sortie: Path) -> list[dict[str, Any]]:
    return omop.lire(generer(scenario, sortie).etat_reel)


def test_changer_une_proba_dobservation_ne_change_pas_letat_reel(tmp_path: Path) -> None:
    base = Scenario(n_patients=100, graine=0, proba_dosage_si_temoin=0.1)
    variante = Scenario(n_patients=100, graine=0, proba_dosage_si_temoin=0.8)

    assert _etat_reel(base, tmp_path / "a") == _etat_reel(variante, tmp_path / "b")


def test_changer_une_proba_dobservation_change_les_resultats(tmp_path: Path) -> None:
    peu = Scenario(n_patients=100, graine=0, proba_dosage_si_temoin=0.0)
    beaucoup = Scenario(n_patients=100, graine=0, proba_dosage_si_temoin=0.9)

    dosages_peu = omop.lire(generer(peu, tmp_path / "a").omop / "measurement.parquet")
    dosages_beaucoup = omop.lire(generer(beaucoup, tmp_path / "b").omop / "measurement.parquet")

    assert len(dosages_beaucoup) > len(dosages_peu)


def test_changer_la_part_de_sjd_change_letat_reel(tmp_path: Path) -> None:
    rare = Scenario(n_patients=100, graine=0, part_sjd=0.1)
    frequent = Scenario(n_patients=100, graine=0, part_sjd=0.9)

    assert _etat_reel(rare, tmp_path / "a") != _etat_reel(frequent, tmp_path / "b")
