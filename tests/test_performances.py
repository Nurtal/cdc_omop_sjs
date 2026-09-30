"""Sensibilité et VPP face à l'État réel : les seules performances chiffrées du projet.

Elles n'existent que sur le jeu synthétique, et ne valent que sous les hypothèses du
Processus d'observation (ADR-0001). Sur l'EDS, il n'y a pas de référence (ADR-0004).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from sjs_phenotype import omop
from sjs_phenotype.evaluation import performances
from sjs_phenotype.generator import Observation, Profil, Scenario, generer
from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut
from sjs_phenotype.phenotype import run_phenotype


def _ligne(person_id: int, niveau: Niveau, *, exclu: bool = False) -> LignePhenotype:
    statuts = {item: Statut.NON_DOCUMENTE for item in Item}
    if niveau is not Niveau.AUCUN:
        statuts[Item.ANTI_SSA] = Statut.POSITIF
    return LignePhenotype(
        person_id=person_id,
        statuts=statuts,
        score_observe=3 if niveau is not Niveau.AUCUN else 0,
        score_atteignable=9,
        niveau=niveau,
        dates_atteinte={niveau: date(2020, 1, 1)} if niveau is not Niveau.AUCUN else {},
        criteres_exclusion=("D86",) if exclu else (),
    )


def test_un_cas_calcule_a_la_main() -> None:
    """10 patients : 6 SjD, dont 3 identifiés ; 2 identifiés à tort parmi les 4 témoins.

    Sensibilité = 3/6 = 0,5. VPP = 3/(3+2) = 0,6.
    """
    table = [_ligne(person_id, Niveau.PROBABLE) for person_id in (1, 2, 3, 7, 8)]
    table += [_ligne(person_id, Niveau.AUCUN) for person_id in (4, 5, 6, 9, 10)]
    etat_reel = {person_id: person_id <= 6 for person_id in range(1, 11)}

    resultat = performances(table, etat_reel)

    assert resultat.sensibilite == pytest.approx(0.5)
    assert resultat.vpp == pytest.approx(0.6)
    assert resultat.vrais_positifs == 3
    assert resultat.faux_negatifs == 3
    assert resultat.faux_positifs == 2
    assert resultat.vrais_negatifs == 2


def test_la_specificite_est_rendue_aussi() -> None:
    table = [_ligne(1, Niveau.PROBABLE), _ligne(2, Niveau.AUCUN), _ligne(3, Niveau.AUCUN)]

    resultat = performances(table, {1: True, 2: False, 3: False})

    assert resultat.specificite == pytest.approx(1.0)


def test_les_performances_sont_rendues_par_niveau() -> None:
    """Défini seul repère moins de patients que Défini et Probable réunis."""
    table = [_ligne(1, Niveau.DEFINI), _ligne(2, Niveau.PROBABLE), _ligne(3, Niveau.AUCUN)]
    etat_reel = {1: True, 2: True, 3: False}

    large = performances(table, etat_reel)
    stricte = performances(table, etat_reel, niveaux=(Niveau.DEFINI,))

    assert large.sensibilite == pytest.approx(1.0)
    assert stricte.sensibilite == pytest.approx(0.5)


def test_un_exclu_nest_pas_identifie() -> None:
    table = [_ligne(1, Niveau.PROBABLE), _ligne(2, Niveau.PROBABLE, exclu=True)]

    resultat = performances(table, {1: True, 2: True})

    assert resultat.vrais_positifs == 1
    assert resultat.faux_negatifs == 1


def test_sans_aucun_malade_la_sensibilite_est_sans_objet() -> None:
    resultat = performances([_ligne(1, Niveau.AUCUN)], {1: False})

    assert resultat.sensibilite is None
    assert resultat.vpp is None


def test_un_patient_absent_de_letat_reel_est_ignore() -> None:
    """Un État réel dépareillé ne doit pas faire tomber le calcul."""
    table = [_ligne(1, Niveau.PROBABLE), _ligne(2, Niveau.PROBABLE)]

    resultat = performances(table, {1: True})

    assert resultat.total == 1
    assert resultat.vrais_positifs == 1


def test_les_parametres_sont_traces() -> None:
    resultat = performances([_ligne(1, Niveau.DEFINI)], {1: True}, niveaux=(Niveau.DEFINI,))

    trace = resultat.en_json()
    assert trace["niveaux_retenus"] == ["défini"]
    assert trace["exclus_retires"] is True


def test_doser_moins_souvent_abaisse_la_sensibilite(tmp_path: Path) -> None:
    """Le Processus d'observation pèse sur la sensibilité : c'est ce qu'on veut montrer."""

    def mesurer(proba: float, sortie: Path) -> float:
        scenario = Scenario(
            n_patients=600,
            graine=11,
            parts={Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: 0.5, Profil.POPULATION_GENERALE: 0.5},
            observation=Observation(proba_dosage_si_sjd=proba, proba_dosage_si_temoin=0.0),
        )
        chemins = generer(scenario, sortie)
        table = run_phenotype(chemins.omop)
        resultat = performances(table, _etat_reel(chemins.etat_reel))
        assert resultat.sensibilite is not None
        return resultat.sensibilite

    assert mesurer(0.3, tmp_path / "rare") < mesurer(0.95, tmp_path / "frequent")


def test_un_malade_jamais_dose_nest_pas_identifie(tmp_path: Path) -> None:
    """La garantie d'étanchéité : tous SjD dans l'État réel, aucun dosage, donc aucun cas.

    Si la Définition computable consultait l'État réel d'une manière ou d'une autre, elle
    les identifierait tous. Elle n'a ici aucune preuve observable, et doit le dire.
    """
    scenario = Scenario(
        n_patients=150,
        graine=12,
        parts={Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: 1.0},
        observation=Observation(proba_dosage_si_sjd=0.0),
    )
    chemins = generer(scenario, tmp_path)

    table = run_phenotype(chemins.omop)
    resultat = performances(table, _etat_reel(chemins.etat_reel))

    assert resultat.faux_negatifs == 150
    assert resultat.vrais_positifs == 0
    assert all(ligne.niveau is Niveau.AUCUN for ligne in table)


def test_un_etat_reel_glisse_dans_le_dossier_omop_est_ignore(tmp_path: Path) -> None:
    """Même posé au milieu des tables OMOP, l'État réel ne doit rien changer."""
    chemins = generer(Scenario(n_patients=200, graine=12), tmp_path)
    avant = run_phenotype(chemins.omop)

    (chemins.omop / "etat_reel.parquet").write_bytes(chemins.etat_reel.read_bytes())

    assert run_phenotype(chemins.omop) == avant


def _etat_reel(chemin: Path) -> dict[int, bool]:
    return {int(ligne["person_id"]): bool(ligne["sjd"]) for ligne in omop.lire(chemin)}
