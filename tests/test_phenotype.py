"""Tests du seam 1 : un dossier OMOP en Parquet entre, une table phénotype sort."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from aide_omop import ecrire_jeu
from sjs_phenotype import omop
from sjs_phenotype.concepts import JeuDeConcepts
from sjs_phenotype.generator import Observation, Profil, Scenario, generer
from sjs_phenotype.modele import Item, Niveau, Statut
from sjs_phenotype.phenotype import run_phenotype

CONCEPTS = JeuDeConcepts.par_defaut()


def _personne(person_id: int) -> dict[str, Any]:
    return {"person_id": person_id, "gender_concept_id": 8532, "year_of_birth": 1970}


def _resultat(
    person_id: int,
    concept_id: int,
    *,
    valeur_concept_id: int | None = None,
    valeur: float | None = None,
    seuil_haut: float | None = None,
    jour: date = date(2020, 5, 4),
) -> dict[str, Any]:
    return {
        "measurement_id": person_id * 100 + concept_id % 100,
        "person_id": person_id,
        "measurement_concept_id": concept_id,
        "measurement_date": jour,
        "value_as_number": valeur,
        "value_as_concept_id": valeur_concept_id,
        "range_high": seuil_haut,
        "measurement_source_value": "SSA",
        "visit_occurrence_id": None,
    }


def test_un_anti_ssa_positif_donne_probable(dossier_omop: Path) -> None:
    ecrire_jeu(
        dossier_omop,
        person=[_personne(1)],
        measurement=[
            _resultat(1, CONCEPTS.anti_ro60[0], valeur_concept_id=CONCEPTS.valeur_positive)
        ],
    )

    (ligne,) = run_phenotype(dossier_omop)

    assert ligne.statuts[Item.ANTI_SSA] is Statut.POSITIF
    assert ligne.score_observe == 3
    assert ligne.score_atteignable == 9
    assert ligne.niveau is Niveau.PROBABLE


def test_sans_resultat_les_items_sont_non_documentes(dossier_omop: Path) -> None:
    ecrire_jeu(dossier_omop, person=[_personne(1)], measurement=[])

    (ligne,) = run_phenotype(dossier_omop)

    assert all(statut is Statut.NON_DOCUMENTE for statut in ligne.statuts.values())
    assert ligne.score_observe == 0
    assert ligne.score_atteignable == 9
    assert ligne.niveau is Niveau.AUCUN


def test_un_resultat_negatif_nest_pas_non_documente(dossier_omop: Path) -> None:
    ecrire_jeu(
        dossier_omop,
        person=[_personne(1)],
        measurement=[
            _resultat(1, CONCEPTS.anti_ro60[0], valeur_concept_id=CONCEPTS.valeur_negative)
        ],
    )

    (ligne,) = run_phenotype(dossier_omop)

    assert ligne.statuts[Item.ANTI_SSA] is Statut.NEGATIF
    assert ligne.score_observe == 0
    assert ligne.score_atteignable == 6
    assert ligne.niveau is Niveau.AUCUN


def test_une_valeur_au_dessus_du_seuil_est_positive(dossier_omop: Path) -> None:
    ecrire_jeu(
        dossier_omop,
        person=[_personne(1), _personne(2)],
        measurement=[
            _resultat(1, CONCEPTS.anti_ro60[0], valeur=240.0, seuil_haut=10.0),
            _resultat(2, CONCEPTS.anti_ro60[0], valeur=3.0, seuil_haut=10.0),
        ],
    )

    positif, negatif = run_phenotype(dossier_omop)

    assert positif.statuts[Item.ANTI_SSA] is Statut.POSITIF
    assert negatif.statuts[Item.ANTI_SSA] is Statut.NEGATIF


def test_un_anti_ro52_isole_nest_pas_un_anti_ssa(dossier_omop: Path) -> None:
    ecrire_jeu(
        dossier_omop,
        person=[_personne(1)],
        measurement=[
            _resultat(1, CONCEPTS.anti_ro52[0], valeur_concept_id=CONCEPTS.valeur_positive)
        ],
    )

    (ligne,) = run_phenotype(dossier_omop)

    assert ligne.statuts[Item.ANTI_SSA] is Statut.NON_DOCUMENTE
    assert ligne.niveau is Niveau.AUCUN


def test_la_date_datteinte_est_celle_de_la_premiere_preuve(dossier_omop: Path) -> None:
    ecrire_jeu(
        dossier_omop,
        person=[_personne(1)],
        measurement=[
            _resultat(
                1,
                CONCEPTS.anti_ro60[0],
                valeur_concept_id=CONCEPTS.valeur_positive,
                jour=date(2015, 3, 2),
            ),
            _resultat(
                1,
                CONCEPTS.anti_ssa_non_differencie[0],
                valeur_concept_id=CONCEPTS.valeur_positive,
                jour=date(2019, 8, 9),
            ),
        ],
    )

    (ligne,) = run_phenotype(dossier_omop)

    assert ligne.dates_atteinte[Niveau.PROBABLE] == date(2015, 3, 2)
    assert Niveau.DEFINI not in ligne.dates_atteinte


def test_personne_natteint_defini_sans_extraction(tmp_path: Path) -> None:
    chemins = generer(Scenario(n_patients=300, graine=7), tmp_path)

    table = run_phenotype(chemins.omop)

    assert table, "le jeu généré doit contenir des patients"
    assert all(ligne.niveau is not Niveau.DEFINI for ligne in table)


def test_les_patients_seropositifs_doses_atteignent_probable(tmp_path: Path) -> None:
    """Scénario sans hasard de recueil : tout séropositif est dosé, aucun témoin ne l'est."""
    scenario = Scenario(
        nom="sans hasard de recueil",
        n_patients=200,
        graine=1,
        parts={Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: 0.4, Profil.POPULATION_GENERALE: 0.6},
        observation=Observation(proba_dosage_si_sjd=1.0, proba_dosage_si_temoin=0.0),
    )
    chemins = generer(scenario, tmp_path)

    table = run_phenotype(chemins.omop)
    probables = {ligne.person_id for ligne in table if ligne.niveau is Niveau.PROBABLE}

    etat_reel = omop.lire(chemins.etat_reel)
    seropositifs = {int(ligne["person_id"]) for ligne in etat_reel if bool(ligne["anti_ssa_reel"])}
    assert probables == seropositifs


def test_meme_graine_meme_resultat(tmp_path: Path) -> None:
    premier = generer(Scenario(n_patients=120, graine=3), tmp_path / "a")
    second = generer(Scenario(n_patients=120, graine=3), tmp_path / "b")

    assert run_phenotype(premier.omop) == run_phenotype(second.omop)


def test_graines_differentes_jeux_differents(tmp_path: Path) -> None:
    premier = generer(Scenario(n_patients=120, graine=3), tmp_path / "a")
    second = generer(Scenario(n_patients=120, graine=4), tmp_path / "b")

    assert run_phenotype(premier.omop) != run_phenotype(second.omop)


def _lupus_ro52_isole(proba_rendu_non_differencie: float) -> Scenario:
    return Scenario(
        nom="lupus à Ro52 isolé",
        n_patients=100,
        graine=2,
        parts={Profil.LUPUS_ANTI_SSA: 1.0},
        part_ro52_isole_si_lupus=1.0,
        observation=Observation(
            proba_dosage_si_temoin=1.0,
            proba_rendu_non_differencie=proba_rendu_non_differencie,
        ),
    )


def test_un_ro52_isole_rendu_comme_tel_natteint_jamais_probable(tmp_path: Path) -> None:
    """Quand le laboratoire distingue Ro52 et Ro60, un Ro52 isolé n'est pas un Anti-SSA."""
    chemins = generer(_lupus_ro52_isole(0.0), tmp_path)

    table = run_phenotype(chemins.omop)

    assert len(table) == 100
    assert all(ligne.niveau is Niveau.AUCUN for ligne in table)


def test_un_ro52_isole_rendu_sans_distinction_devient_probable(tmp_path: Path) -> None:
    """Un dosage global ne sépare pas Ro52 de Ro60 : le faux positif est inévitable, et voulu."""
    chemins = generer(_lupus_ro52_isole(1.0), tmp_path)

    table = run_phenotype(chemins.omop)

    assert all(ligne.niveau is Niveau.PROBABLE for ligne in table)
