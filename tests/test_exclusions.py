"""Critères d'exclusion ACR/EULAR : calculés quand ils peuvent l'être, signalés sinon.

Un patient exclu garde son Niveau de certitude et reçoit le statut Exclu : il reste dans la
table, pour qu'on puisse chiffrer ce que les exclusions changent.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.evaluation import evaluer
from sjs_phenotype.generator import Observation, Profil, Scenario, generer
from sjs_phenotype.modele import Niveau
from sjs_phenotype.phenotype import run_phenotype

VOCABULAIRE = Vocabulaire.par_defaut()


def _personne(person_id: int) -> dict[str, Any]:
    return {"person_id": person_id, "gender_concept_id": 8532, "year_of_birth": 1970}


def _anti_ssa_positif(person_id: int) -> dict[str, Any]:
    return {
        "measurement_id": person_id * 10,
        "person_id": person_id,
        "measurement_concept_id": VOCABULAIRE.anti_ssa.anti_ro60[0],
        "measurement_date": date(2018, 4, 1),
        "value_as_number": None,
        "value_as_concept_id": VOCABULAIRE.valeur_positive,
        "range_high": None,
        "measurement_source_value": "anti-SSA",
        "visit_occurrence_id": None,
    }


def _pcr_vhc(person_id: int, *, positive: bool) -> dict[str, Any]:
    return {
        **_anti_ssa_positif(person_id),
        "measurement_id": person_id * 10 + 1,
        "measurement_concept_id": VOCABULAIRE.biologie.concept("pcr_vhc"),
        "value_as_concept_id": (
            VOCABULAIRE.valeur_positive if positive else VOCABULAIRE.valeur_negative
        ),
        "measurement_source_value": "PCR VHC",
    }


def _diagnostic(person_id: int, code: str, jour: date = date(2019, 6, 1)) -> dict[str, Any]:
    return {
        "condition_occurrence_id": person_id * 10,
        "person_id": person_id,
        "condition_concept_id": VOCABULAIRE.diagnostics.concept(code),
        "condition_start_date": jour,
        "condition_source_value": code,
        "visit_occurrence_id": None,
    }


def _jeu(
    dossier: Path,
    person: list[dict[str, Any]],
    measurement: list[dict[str, Any]],
    condition_occurrence: list[dict[str, Any]],
) -> Path:
    omop.ecrire_table(dossier, "person", person)
    omop.ecrire_table(dossier, "measurement", measurement)
    omop.ecrire_table(dossier, "condition_occurrence", condition_occurrence)
    return dossier


def test_un_patient_exclu_garde_son_niveau(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1)],
        measurement=[_anti_ssa_positif(1)],
        condition_occurrence=[_diagnostic(1, "D86")],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.niveau is Niveau.PROBABLE
    assert ligne.exclu
    assert ligne.criteres_exclusion == ("D86",)


def test_un_patient_sans_critere_nest_pas_exclu(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1)],
        measurement=[_anti_ssa_positif(1)],
        condition_occurrence=[_diagnostic(1, "M32")],
    )

    (ligne,) = run_phenotype(dossier)

    assert not ligne.exclu
    assert ligne.criteres_exclusion == ()


def test_le_code_vhc_seul_nexclut_pas(tmp_path: Path) -> None:
    """Le critère ACR/EULAR vise une hépatite C active : le code ne suffit pas."""
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1), _personne(2)],
        measurement=[
            _anti_ssa_positif(1),
            _pcr_vhc(1, positive=False),
            _anti_ssa_positif(2),
            _pcr_vhc(2, positive=True),
        ],
        condition_occurrence=[_diagnostic(1, "B18.2"), _diagnostic(2, "B18.2")],
    )

    sans_pcr, avec_pcr = run_phenotype(dossier)

    assert not sans_pcr.exclu
    assert avec_pcr.exclu
    assert avec_pcr.criteres_exclusion == ("B18.2",)


def test_plusieurs_criteres_sont_tous_nommes(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1)],
        measurement=[_anti_ssa_positif(1)],
        condition_occurrence=[
            _diagnostic(1, "D86"),
            {**_diagnostic(1, "E85"), "condition_occurrence_id": 11},
        ],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.criteres_exclusion == ("D86", "E85")


def test_une_exclusion_posterieure_compte_aussi(tmp_path: Path) -> None:
    """Les exclusions valent sur tout l'historique, pas seulement avant la Date d'atteinte."""
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1)],
        measurement=[_anti_ssa_positif(1)],
        condition_occurrence=[_diagnostic(1, "D86", jour=date(2023, 1, 1))],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.exclu


def test_levaluation_compte_avec_et_sans_les_exclus(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1), _personne(2)],
        measurement=[_anti_ssa_positif(1), _anti_ssa_positif(2)],
        condition_occurrence=[_diagnostic(2, "D86")],
    )

    effectifs = evaluer(run_phenotype(dossier))

    assert effectifs.par_niveau[Niveau.PROBABLE] == 2
    assert effectifs.par_niveau_hors_exclus[Niveau.PROBABLE] == 1
    assert effectifs.exclus == 1


def test_les_criteres_non_calculables_sont_signales(tmp_path: Path) -> None:
    effectifs = evaluer([], criteres_non_appliques=("radiothérapie cervico-faciale",))

    assert effectifs.en_json()["criteres_non_appliques"] == ["radiothérapie cervico-faciale"]


def test_le_profil_porteur_dexclusion_produit_des_exclus(tmp_path: Path) -> None:
    scenario = Scenario(
        n_patients=60,
        graine=3,
        parts={Profil.PORTEUR_CRITERE_EXCLUSION: 1.0},
        observation=Observation(proba_dosage_si_temoin=1.0),
    )
    chemins = generer(scenario, tmp_path)

    table = run_phenotype(chemins.omop)

    assert any(ligne.exclu for ligne in table)
    assert all(
        set(ligne.criteres_exclusion) <= set(VOCABULAIRE.diagnostics.groupe("criteres_exclusion"))
        for ligne in table
    )


def test_le_generateur_accorde_son_etat_reel_et_le_pipeline(tmp_path: Path) -> None:
    """Ce que le jeu déclare exclu doit être exactement ce que le pipeline trouve."""
    scenario = Scenario(
        n_patients=200,
        graine=7,
        parts={Profil.PORTEUR_CRITERE_EXCLUSION: 1.0},
        observation=Observation(proba_dosage_si_temoin=1.0),
    )
    chemins = generer(scenario, tmp_path)

    exclus_reels = {
        int(ligne["person_id"])
        for ligne in omop.lire(chemins.etat_reel)
        if bool(ligne["exclusion"])
    }
    exclus_trouves = {ligne.person_id for ligne in run_phenotype(chemins.omop) if ligne.exclu}

    assert exclus_trouves == exclus_reels


def test_une_hepatite_c_inactive_nexclut_pas_dans_le_jeu_genere(tmp_path: Path) -> None:
    scenario = Scenario(
        n_patients=200,
        graine=7,
        parts={Profil.PORTEUR_CRITERE_EXCLUSION: 1.0},
        part_vhc_actif_si_exclusion=0.0,
        observation=Observation(proba_dosage_si_temoin=1.0),
    )
    chemins = generer(scenario, tmp_path)

    etat_reel = {int(ligne["person_id"]): ligne for ligne in omop.lire(chemins.etat_reel)}
    table = {ligne.person_id: ligne for ligne in run_phenotype(chemins.omop)}
    porteurs_vhc = [
        person_id for person_id, ligne in etat_reel.items() if ligne["critere_exclusion"] == "B18.2"
    ]

    assert porteurs_vhc, "le jeu doit contenir des hépatites C"
    assert all(not table[person_id].exclu for person_id in porteurs_vhc)


def test_un_critere_est_nomme_meme_sans_texte_source(tmp_path: Path) -> None:
    """Dans un export OMOP, `condition_source_value` est souvent vide : le concept suffit."""
    dossier = _jeu(
        tmp_path / "omop",
        person=[_personne(1)],
        measurement=[_anti_ssa_positif(1)],
        condition_occurrence=[{**_diagnostic(1, "D86"), "condition_source_value": None}],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.criteres_exclusion == ("D86",)
