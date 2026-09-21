"""Comparateur CIM-10 : un ensemble de patients calculé à part, jamais une référence.

Les codes CIM-10 de SjD n'entrent pas dans la Définition computable. C'est ce qui donne
son sens à la comparaison : deux repérages indépendants, qu'on confronte sans dire lequel
a raison (ADR-0004).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.comparateur import Comparateur, comparateur_cim10
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.generator import Observation, Profil, Scenario, generer
from sjs_phenotype.modele import Niveau
from sjs_phenotype.phenotype import run_phenotype

VOCABULAIRE = Vocabulaire.par_defaut()
CODE_SJD = VOCABULAIRE.diagnostics.concept("M35.0")


def _personne(person_id: int) -> dict[str, Any]:
    return {"person_id": person_id, "gender_concept_id": 8532, "year_of_birth": 1970}


def _code_sjd(person_id: int, rang: int = 0, jour: date = date(2019, 6, 1)) -> dict[str, Any]:
    return {
        "condition_occurrence_id": person_id * 10 + rang,
        "person_id": person_id,
        "condition_concept_id": CODE_SJD,
        "condition_start_date": jour,
        "condition_source_value": "M35.0",
        "visit_occurrence_id": None,
    }


def _jeu(dossier: Path, person: list[dict[str, Any]], conditions: list[dict[str, Any]]) -> Path:
    omop.ecrire_table(dossier, "person", person)
    omop.ecrire_table(dossier, "measurement", [])
    omop.ecrire_table(dossier, "condition_occurrence", conditions)
    return dossier


def test_un_code_suffit_par_defaut(tmp_path: Path) -> None:
    dossier = _jeu(tmp_path / "omop", [_personne(1)], [_code_sjd(1)])

    assert comparateur_cim10(dossier) == {1}


def test_le_seuil_a_deux_occurrences_donne_un_ensemble_different(tmp_path: Path) -> None:
    """La variante de Robustesse : deux occurrences distinctes, pas deux lignes du même jour."""
    dossier = _jeu(
        tmp_path / "omop",
        [_personne(1), _personne(2), _personne(3)],
        [
            _code_sjd(1),
            _code_sjd(2),
            _code_sjd(2, rang=1, jour=date(2021, 3, 4)),
            _code_sjd(3),
            _code_sjd(3, rang=1),
        ],
    )

    assert comparateur_cim10(dossier) == {1, 2, 3}
    assert comparateur_cim10(dossier, Comparateur(occurrences_minimum=2)) == {2}


def test_un_autre_code_nentre_pas_dans_le_comparateur(tmp_path: Path) -> None:
    lupus = {
        **_code_sjd(1),
        "condition_concept_id": VOCABULAIRE.diagnostics.concept("M32"),
        "condition_source_value": "M32",
    }
    dossier = _jeu(tmp_path / "omop", [_personne(1)], [lupus])

    assert comparateur_cim10(dossier) == set()


def test_sans_table_de_diagnostics_le_comparateur_est_vide(tmp_path: Path) -> None:
    dossier = tmp_path / "omop"
    omop.ecrire_table(dossier, "person", [_personne(1)])
    omop.ecrire_table(dossier, "measurement", [])

    assert comparateur_cim10(dossier) == set()


def test_un_patient_code_sans_item_positif_nest_jamais_identifie(tmp_path: Path) -> None:
    """Le point qui donne son sens à la comparaison : les codes n'entrent pas dans la règle."""
    dossier = _jeu(tmp_path / "omop", [_personne(1)], [_code_sjd(1), _code_sjd(1, rang=1)])

    (ligne,) = run_phenotype(dossier)

    assert ligne.niveau is Niveau.AUCUN
    assert comparateur_cim10(dossier) == {1}


def test_le_profil_code_a_tort_entre_dans_le_comparateur_sans_etre_identifie(
    tmp_path: Path,
) -> None:
    scenario = Scenario(
        n_patients=80,
        graine=5,
        parts={Profil.M35_CODE_A_TORT: 1.0},
        observation=Observation(proba_dosage_si_temoin=1.0),
    )
    chemins = generer(scenario, tmp_path)

    codes = comparateur_cim10(chemins.omop)
    identifies = {
        ligne.person_id for ligne in run_phenotype(chemins.omop) if ligne.niveau is not Niveau.AUCUN
    }

    assert codes, "le profil doit porter des codes M35.0"
    assert not identifies


def test_la_variante_a_deux_occurrences_retient_des_patients_generes(tmp_path: Path) -> None:
    """Sans recodage aux venues suivantes, la variante de Robustesse serait inerte."""
    scenario = Scenario(
        n_patients=300,
        graine=8,
        observation=Observation(proba_codage_si_sjd=1.0, proba_recodage_a_chaque_venue=1.0),
    )
    chemins = generer(scenario, tmp_path)

    une = comparateur_cim10(chemins.omop)
    deux = comparateur_cim10(chemins.omop, Comparateur(occurrences_minimum=2))

    assert deux
    assert deux < une


def test_sans_recodage_le_seuil_a_deux_ne_retient_personne(tmp_path: Path) -> None:
    scenario = Scenario(
        n_patients=200,
        graine=8,
        observation=Observation(proba_codage_si_sjd=1.0, proba_recodage_a_chaque_venue=0.0),
    )
    chemins = generer(scenario, tmp_path)

    assert comparateur_cim10(chemins.omop)
    assert comparateur_cim10(chemins.omop, Comparateur(occurrences_minimum=2)) == set()
