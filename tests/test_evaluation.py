"""Tests du seam 2 : des tables entrent, des tables de résultats sortent."""

from __future__ import annotations

from datetime import date

from sjs_phenotype.evaluation import PROFIL_INCONNU, evaluer
from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut


def _ligne(person_id: int, anti_ssa: Statut, niveau: Niveau) -> LignePhenotype:
    statuts = {item: Statut.NON_DOCUMENTE for item in Item}
    statuts[Item.ANTI_SSA] = anti_ssa
    points_observes = 3 if anti_ssa is Statut.POSITIF else 0
    points_non_documentes = sum(
        item.points for item, statut in statuts.items() if statut is Statut.NON_DOCUMENTE
    )
    dates: dict[Niveau, date] = {}
    if niveau is not Niveau.AUCUN:
        dates[niveau] = date(2020, 1, 1)
    return LignePhenotype(
        person_id=person_id,
        statuts=statuts,
        score_observe=points_observes,
        score_atteignable=points_observes + points_non_documentes,
        niveau=niveau,
        dates_atteinte=dates,
    )


def test_effectifs_par_niveau() -> None:
    table = [
        _ligne(1, Statut.POSITIF, Niveau.PROBABLE),
        _ligne(2, Statut.POSITIF, Niveau.PROBABLE),
        _ligne(3, Statut.NEGATIF, Niveau.AUCUN),
        _ligne(4, Statut.NON_DOCUMENTE, Niveau.AUCUN),
    ]

    effectifs = evaluer(table)

    assert effectifs.total == 4
    assert effectifs.par_niveau[Niveau.PROBABLE] == 2
    assert effectifs.par_niveau[Niveau.AUCUN] == 2
    assert effectifs.par_niveau[Niveau.DEFINI] == 0


def test_effectifs_par_statut_ditem() -> None:
    table = [
        _ligne(1, Statut.POSITIF, Niveau.PROBABLE),
        _ligne(2, Statut.NEGATIF, Niveau.AUCUN),
        _ligne(3, Statut.NON_DOCUMENTE, Niveau.AUCUN),
    ]

    effectifs = evaluer(table)

    anti_ssa = effectifs.par_statut[Item.ANTI_SSA]
    assert anti_ssa[Statut.POSITIF] == 1
    assert anti_ssa[Statut.NEGATIF] == 1
    assert anti_ssa[Statut.NON_DOCUMENTE] == 1
    assert effectifs.par_statut[Item.SCHIRMER][Statut.NON_DOCUMENTE] == 3


def test_les_effectifs_par_profil_viennent_de_letat_reel() -> None:
    table = [
        _ligne(1, Statut.POSITIF, Niveau.PROBABLE),
        _ligne(2, Statut.NEGATIF, Niveau.AUCUN),
        _ligne(3, Statut.NON_DOCUMENTE, Niveau.AUCUN),
    ]
    profils = {1: "sjd_seropositive_biopsie", 2: "sjd_seronegative", 3: "population_generale"}

    effectifs = evaluer(table, profils=profils)

    assert effectifs.par_profil["sjd_seropositive_biopsie"] == 1
    assert effectifs.par_profil["population_generale"] == 1


def test_sans_etat_reel_il_ny_a_pas_deffectifs_par_profil() -> None:
    effectifs = evaluer([_ligne(1, Statut.POSITIF, Niveau.PROBABLE)])

    assert effectifs.par_profil == {}


def test_une_table_vide_ne_fait_pas_tomber_levaluation() -> None:
    effectifs = evaluer([])

    assert effectifs.total == 0
    assert effectifs.par_niveau[Niveau.PROBABLE] == 0


def test_un_patient_absent_de_letat_reel_est_compte_a_part() -> None:
    table = [_ligne(1, Statut.POSITIF, Niveau.PROBABLE), _ligne(2, Statut.NEGATIF, Niveau.AUCUN)]

    effectifs = evaluer(table, profils={1: "sjd_seronegative"})

    assert effectifs.par_profil["sjd_seronegative"] == 1
    assert effectifs.par_profil[PROFIL_INCONNU] == 1
