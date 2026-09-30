"""Le générateur : dix profils, un Processus d'observation réglable, et rien qui fuite.

L'État réel et le Processus d'observation sont deux tirages indépendants (ADR-0001).
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from sjs_phenotype import omop
from sjs_phenotype.generator import Observation, Profil, Scenario, generer


def _scenario(**surcharges: Any) -> Scenario:
    return Scenario(**{"n_patients": 200, "graine": 0, **surcharges})


def _etat_reel(scenario: Scenario, sortie: Path) -> list[dict[str, Any]]:
    return omop.lire(generer(scenario, sortie).etat_reel)


def _table(chemins_omop: Path, nom: str) -> list[dict[str, Any]]:
    return omop.lire(chemins_omop / f"{nom}.parquet")


def test_changer_une_proba_dobservation_ne_change_pas_letat_reel(tmp_path: Path) -> None:
    base = _scenario(observation=Observation(proba_dosage_si_temoin=0.1))
    variante = _scenario(observation=Observation(proba_dosage_si_temoin=0.8))

    assert _etat_reel(base, tmp_path / "a") == _etat_reel(variante, tmp_path / "b")


def test_les_dix_profils_sont_generes(tmp_path: Path) -> None:
    etat_reel = _etat_reel(_scenario(), tmp_path)

    profils = {ligne["profil"] for ligne in etat_reel}

    assert profils == {profil.value for profil in Profil}


def test_les_proportions_demandees_sont_respectees(tmp_path: Path) -> None:
    scenario = _scenario(
        n_patients=100,
        parts={Profil.SJD_SEROPOSITIVE_BIOPSIE: 0.25, Profil.POPULATION_GENERALE: 0.75},
    )

    profils = Counter(ligne["profil"] for ligne in _etat_reel(scenario, tmp_path))

    assert profils[Profil.SJD_SEROPOSITIVE_BIOPSIE.value] == 25
    assert profils[Profil.POPULATION_GENERALE.value] == 75


def test_une_part_inconnue_est_refusee() -> None:
    with pytest.raises(ValueError, match="profil"):
        Scenario(parts={"sjd_imaginaire": 1.0})


def test_les_trois_formes_de_rendu_danti_ssa_sont_produites(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=400), tmp_path)

    concepts = {ligne["measurement_concept_id"] for ligne in _table(chemins.omop, "measurement")}

    from sjs_phenotype.concepts import JeuDeConcepts

    anti_ssa = JeuDeConcepts.par_defaut()
    assert anti_ssa.anti_ro60[0] in concepts
    assert anti_ssa.anti_ro52[0] in concepts
    assert anti_ssa.anti_ssa_non_differencie[0] in concepts


def test_coder_plus_souvent_produit_plus_de_codes_sjd(tmp_path: Path) -> None:
    from sjs_phenotype.concepts import Vocabulaire

    code_sjd = Vocabulaire.par_defaut().diagnostics.concept("M35.0")
    rare = _scenario(observation=Observation(proba_codage_si_sjd=0.1))
    frequent = _scenario(observation=Observation(proba_codage_si_sjd=0.9))

    def codes(scenario: Scenario, sortie: Path) -> int:
        chemins = generer(scenario, sortie)
        diagnostics = _table(chemins.omop, "condition_occurrence")
        return sum(1 for ligne in diagnostics if ligne["condition_concept_id"] == code_sjd)

    assert codes(frequent, tmp_path / "a") > codes(rare, tmp_path / "b")


def test_doser_plus_souvent_produit_plus_de_resultats(tmp_path: Path) -> None:
    rare = _scenario(observation=Observation(proba_dosage_si_temoin=0.0))
    frequent = _scenario(observation=Observation(proba_dosage_si_temoin=0.9))

    peu = len(_table(generer(rare, tmp_path / "a").omop, "measurement"))
    beaucoup = len(_table(generer(frequent, tmp_path / "b").omop, "measurement"))

    assert beaucoup > peu


def test_toutes_les_lignes_se_rattachent_a_un_patient_et_a_une_venue(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=300), tmp_path)

    patients = {ligne["person_id"] for ligne in _table(chemins.omop, "person")}
    venues = {ligne["visit_occurrence_id"] for ligne in _table(chemins.omop, "visit_occurrence")}

    for nom in ("measurement", "condition_occurrence", "drug_exposure", "visit_occurrence"):
        lignes = _table(chemins.omop, nom)
        assert lignes, f"la table {nom} doit être alimentée"
        assert all(ligne["person_id"] in patients for ligne in lignes)
        if nom != "visit_occurrence":
            assert all(ligne["visit_occurrence_id"] in venues for ligne in lignes)


def test_seuls_les_profils_attendus_portent_un_code_sjd(tmp_path: Path) -> None:
    from sjs_phenotype.concepts import Vocabulaire

    code_sjd = Vocabulaire.par_defaut().diagnostics.concept("M35.0")
    chemins = generer(_scenario(n_patients=400), tmp_path)

    profils = {ligne["person_id"]: ligne["profil"] for ligne in omop.lire(chemins.etat_reel)}
    codes = {
        ligne["person_id"]
        for ligne in _table(chemins.omop, "condition_occurrence")
        if ligne["condition_concept_id"] == code_sjd
    }

    attendus = {profil.value for profil in Profil if profil.value.startswith("sjd_")}
    attendus.add(Profil.M35_CODE_A_TORT.value)
    assert {profils[person_id] for person_id in codes} <= attendus


def test_un_scenario_se_charge_depuis_un_fichier(tmp_path: Path) -> None:
    fichier = tmp_path / "essai.toml"
    fichier.write_text(
        """
        nom = "essai"
        n_patients = 42
        graine = 9
        [parts]
        sjd_seronegative = 0.5
        population_generale = 0.5
        [observation]
        proba_dosage_si_sjd = 0.25
        """,
        encoding="utf-8",
    )

    scenario = Scenario.charger(fichier)

    assert scenario.nom == "essai"
    assert scenario.n_patients == 42
    assert scenario.observation.proba_dosage_si_sjd == 0.25
    assert scenario.parts[Profil.SJD_SERONEGATIVE] == 0.5


def test_le_scenario_utilise_est_ecrit_a_cote_du_jeu(tmp_path: Path) -> None:
    chemins = generer(_scenario(nom="essai"), tmp_path)

    assert chemins.scenario.exists()
    assert "essai" in chemins.scenario.read_text(encoding="utf-8")


def test_un_scenario_fait_laller_retour_par_le_fichier(tmp_path: Path) -> None:
    scenario = _scenario(nom="aller-retour", part_ro52_isole_si_lupus=0.75)
    fichier = tmp_path / "scenario.toml"
    fichier.write_text(scenario.en_toml(), encoding="utf-8")

    assert Scenario.charger(fichier) == scenario


def test_changer_une_proba_ne_decale_pas_le_flux_dobservation(tmp_path: Path) -> None:
    """Deux scénarios qui ne diffèrent que par un réglage doivent rester comparables."""
    rare = _scenario(observation=Observation(proba_codage_si_sjd=0.1))
    frequent = _scenario(observation=Observation(proba_codage_si_sjd=0.9))

    venues_rare = _table(generer(rare, tmp_path / "a").omop, "visit_occurrence")
    venues_frequent = _table(generer(frequent, tmp_path / "b").omop, "visit_occurrence")

    assert venues_rare == venues_frequent


def test_un_scenario_sans_parts_est_refuse() -> None:
    with pytest.raises(ValueError, match="parts"):
        Scenario(parts={})


def test_un_scenario_sans_venue_est_refuse() -> None:
    with pytest.raises(ValueError, match="venues_par_patient"):
        Scenario(observation=Observation(venues_par_patient=0))


def test_un_nom_avec_guillemets_fait_laller_retour(tmp_path: Path) -> None:
    scenario = _scenario(nom='recueil "dégradé"')
    fichier = tmp_path / "scenario.toml"
    fichier.write_text(scenario.en_toml(), encoding="utf-8")

    assert Scenario.charger(fichier).nom == 'recueil "dégradé"'


def test_un_profil_rare_ecrit_en_dernier_nest_pas_rogne(tmp_path: Path) -> None:
    scenario = _scenario(
        n_patients=3, parts={Profil.POPULATION_GENERALE: 0.5, Profil.SJD_LYMPHOME: 0.5}
    )

    profils = Counter(ligne["profil"] for ligne in _etat_reel(scenario, tmp_path))

    assert profils[Profil.SJD_LYMPHOME.value] >= 1
