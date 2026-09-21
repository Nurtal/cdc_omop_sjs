"""Concordance : accord entre deux repérages, en l'absence de référence (ADR-0004).

Les valeurs de kappa et de Jaccard sont vérifiées sur de petites tables écrites à la main,
à des cas dont on connaît le résultat de tête.
"""

from __future__ import annotations

from datetime import date

import pytest

from sjs_phenotype.evaluation import concordance
from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut


def _ligne(person_id: int, niveau: Niveau, *, exclu: bool = False) -> LignePhenotype:
    statuts = {item: Statut.NON_DOCUMENTE for item in Item}
    if niveau is not Niveau.AUCUN:
        statuts[Item.ANTI_SSA] = Statut.POSITIF
    observe = 3 if niveau is not Niveau.AUCUN else 0
    return LignePhenotype(
        person_id=person_id,
        statuts=statuts,
        score_observe=observe,
        score_atteignable=9,
        niveau=niveau,
        dates_atteinte={niveau: date(2020, 1, 1)} if niveau is not Niveau.AUCUN else {},
        criteres_exclusion=("D86",) if exclu else (),
    )


def _table(*niveaux: Niveau) -> list[LignePhenotype]:
    return [_ligne(person_id, niveau) for person_id, niveau in enumerate(niveaux, start=1)]


def test_un_accord_parfait_donne_un_kappa_de_un() -> None:
    table = _table(Niveau.PROBABLE, Niveau.PROBABLE, Niveau.AUCUN, Niveau.AUCUN)

    resultat = concordance(table, comparateur={1, 2})

    assert resultat.kappa == pytest.approx(1.0)
    assert resultat.jaccard == pytest.approx(1.0)


def test_un_desaccord_total_donne_un_jaccard_nul() -> None:
    table = _table(Niveau.PROBABLE, Niveau.PROBABLE, Niveau.AUCUN, Niveau.AUCUN)

    resultat = concordance(table, comparateur={3, 4})

    assert resultat.jaccard == pytest.approx(0.0)
    assert resultat.kappa == pytest.approx(-1.0)


def test_le_tableau_croise_compte_les_quatre_cases() -> None:
    table = _table(Niveau.PROBABLE, Niveau.PROBABLE, Niveau.AUCUN, Niveau.AUCUN)

    resultat = concordance(table, comparateur={1, 3})

    assert resultat.les_deux == 1
    assert resultat.phenotype_seul == 1
    assert resultat.comparateur_seul == 1
    assert resultat.aucun_des_deux == 1


def test_jaccard_vaut_lintersection_sur_lunion() -> None:
    table = _table(Niveau.PROBABLE, Niveau.PROBABLE, Niveau.PROBABLE, Niveau.AUCUN)

    resultat = concordance(table, comparateur={1, 2, 4})

    assert resultat.jaccard == pytest.approx(2 / 4)


def test_kappa_sur_un_cas_calcule_a_la_main() -> None:
    """20 patients : 8 des deux côtés, 2 phénotype seul, 3 comparateur seul, 7 ni l'un ni l'autre.

    Accord observé 15/20 = 0,75. Marges : phénotype 10/20, comparateur 11/20.
    Accord attendu = 0,5 × 0,55 + 0,5 × 0,45 = 0,5. Kappa = (0,75 − 0,5) / 0,5 = 0,5.
    """
    niveaux = (
        [Niveau.PROBABLE] * 8 + [Niveau.PROBABLE] * 2 + [Niveau.AUCUN] * 3 + [Niveau.AUCUN] * 7
    )
    table = _table(*niveaux)
    comparateur = set(range(1, 9)) | {11, 12, 13}

    resultat = concordance(table, comparateur)

    assert resultat.kappa == pytest.approx(0.5)


def test_le_niveau_retenu_est_un_parametre() -> None:
    """Analyse principale sur Défini seul ; Robustesse sur Défini et Probable."""
    table = _table(Niveau.DEFINI, Niveau.PROBABLE, Niveau.AUCUN)

    large = concordance(table, comparateur={1, 2}, niveaux=(Niveau.DEFINI, Niveau.PROBABLE))
    stricte = concordance(table, comparateur={1, 2}, niveaux=(Niveau.DEFINI,))

    assert large.les_deux == 2
    assert stricte.les_deux == 1
    assert stricte.comparateur_seul == 1


def test_deux_ensembles_vides_ne_font_pas_tomber_le_calcul() -> None:
    resultat = concordance(_table(Niveau.AUCUN, Niveau.AUCUN), comparateur=set())

    assert resultat.jaccard is None
    assert resultat.kappa is None
    assert resultat.aucun_des_deux == 2


def test_les_discordants_sont_nommes() -> None:
    table = _table(Niveau.PROBABLE, Niveau.AUCUN)

    resultat = concordance(table, comparateur={2})

    assert resultat.ids_phenotype_seul == (1,)
    assert resultat.ids_comparateur_seul == (2,)


def test_un_exclu_ne_compte_pas_parmi_les_identifies() -> None:
    """Un Critère d'exclusion ACR/EULAR écarte le patient : il n'est pas un cas."""
    table = [_ligne(1, Niveau.PROBABLE), _ligne(2, Niveau.PROBABLE, exclu=True)]

    resultat = concordance(table, comparateur={1, 2})

    assert resultat.les_deux == 1
    assert resultat.comparateur_seul == 1


def test_les_exclus_peuvent_etre_comptes_a_la_demande() -> None:
    table = [_ligne(1, Niveau.PROBABLE), _ligne(2, Niveau.PROBABLE, exclu=True)]

    resultat = concordance(table, comparateur={1, 2}, exclus_retires=False)

    assert resultat.les_deux == 2


def test_les_parametres_sont_traces_dans_le_json() -> None:
    """Deux exécutions ne diffèrent parfois que par leurs paramètres : ils doivent rester."""
    resultat = concordance(
        _table(Niveau.DEFINI),
        comparateur={1},
        niveaux=(Niveau.DEFINI,),
        occurrences_minimum=2,
    )

    trace = resultat.en_json()
    assert trace["niveaux_retenus"] == ["défini"]
    assert trace["occurrences_minimum_cim10"] == 2
    assert trace["exclus_retires"] is True
