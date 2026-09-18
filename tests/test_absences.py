"""Une absence n'est jamais un résultat (ADR-0005).

Sur l'EDS, un entrepôt ClickHouse remplace les valeurs absentes par des valeurs par
défaut : 0 pour un nombre, chaîne vide pour un texte, 1970-01-01 pour une date. Un
Schirmer absent y devient un Schirmer à 0 mm, donc positif. Le pipeline doit rendre les
mêmes Statuts, que la source encode l'absence en NULL ou par des valeurs par défaut.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from aide_omop import ecrire_jeu
from sjs_phenotype import omop
from sjs_phenotype.concepts import JeuDeConcepts
from sjs_phenotype.generator import Scenario, generer
from sjs_phenotype.modele import Item, Niveau, Statut
from sjs_phenotype.omop import Absences
from sjs_phenotype.phenotype import Parametres, run_phenotype

CONCEPTS = JeuDeConcepts.par_defaut()


def _personne(person_id: int) -> dict[str, Any]:
    return {"person_id": person_id, "gender_concept_id": 8532, "year_of_birth": 1970}


def _resultat_vide(person_id: int) -> dict[str, Any]:
    """Un dosage enregistré dont aucune valeur n'a été saisie."""
    return {
        "measurement_id": person_id,
        "person_id": person_id,
        "measurement_concept_id": CONCEPTS.anti_ro60[0],
        "measurement_date": date(2020, 5, 4),
        "value_as_number": None,
        "value_as_concept_id": None,
        "range_high": None,
        "measurement_source_value": "anti-SSA",
        "visit_occurrence_id": None,
    }


def test_les_valeurs_absentes_sont_ecrites_en_defauts(tmp_path: Path) -> None:
    chemin = omop.ecrire_table(
        tmp_path, "measurement", [_resultat_vide(1)], absences=Absences.DEFAUTS
    )

    (ligne,) = omop.lire(chemin)

    assert ligne["value_as_number"] == 0.0
    assert ligne["value_as_concept_id"] == 0
    assert ligne["visit_occurrence_id"] == 0


def test_un_dosage_sans_valeur_reste_non_documente_en_defauts(tmp_path: Path) -> None:
    """Le test qui garde l'invariant : si une absence redevient un résultat, il tombe."""
    dossier = tmp_path / "omop"
    omop.ecrire_table(dossier, "person", [_personne(1)], absences=Absences.DEFAUTS)
    omop.ecrire_table(dossier, "measurement", [_resultat_vide(1)], absences=Absences.DEFAUTS)

    (ligne,) = run_phenotype(dossier, Parametres(absences=Absences.DEFAUTS))

    assert ligne.statuts[Item.ANTI_SSA] is Statut.NON_DOCUMENTE
    assert ligne.niveau is Niveau.AUCUN


def test_un_item_jamais_mesure_reste_non_documente_en_defauts(tmp_path: Path) -> None:
    """Le Schirmer n'est pas encore extrait : un 0 ne doit pas le rendre positif."""
    dossier = tmp_path / "omop"
    omop.ecrire_table(dossier, "person", [_personne(1)], absences=Absences.DEFAUTS)
    omop.ecrire_table(dossier, "measurement", [], absences=Absences.DEFAUTS)

    (ligne,) = run_phenotype(dossier, Parametres(absences=Absences.DEFAUTS))

    assert ligne.statuts[Item.SCHIRMER] is Statut.NON_DOCUMENTE
    assert ligne.score_atteignable == 9


@pytest.mark.parametrize("absences", list(Absences))
def test_la_table_phenotype_est_la_meme_dans_les_deux_modes(
    tmp_path: Path, absences: Absences
) -> None:
    reference = generer(Scenario(n_patients=200, graine=4), tmp_path / "null")
    autre = generer(
        Scenario(n_patients=200, graine=4, absences=absences), tmp_path / str(absences.name)
    )

    attendu = run_phenotype(reference.omop)
    obtenu = run_phenotype(autre.omop, Parametres(absences=absences))

    assert obtenu == attendu


def test_un_ro52_isole_rend_litem_anti_ssa_negatif(tmp_path: Path) -> None:
    """Un panel qui différencie rend les deux résultats : Ro52 positif, Ro60 négatif."""
    dossier = tmp_path / "omop"
    ecrire_jeu(
        dossier,
        person=[_personne(1)],
        measurement=[
            {
                **_resultat_vide(1),
                "measurement_concept_id": CONCEPTS.anti_ro52[0],
                "value_as_concept_id": CONCEPTS.valeur_positive,
            },
            {
                **_resultat_vide(1),
                "measurement_id": 2,
                "value_as_concept_id": CONCEPTS.valeur_negative,
            },
        ],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.ANTI_SSA] is Statut.NEGATIF
    assert ligne.niveau is Niveau.AUCUN


def test_le_panel_differencie_du_generateur_rend_les_deux_resultats(tmp_path: Path) -> None:
    """Le Ro52 reste consultable comme attribut, à côté du Ro60 négatif."""
    from sjs_phenotype.generator import Observation, Profil

    scenario = Scenario(
        n_patients=50,
        graine=2,
        parts={Profil.LUPUS_ANTI_SSA: 1.0},
        part_ro52_isole_si_lupus=1.0,
        observation=Observation(proba_dosage_si_temoin=1.0, proba_rendu_non_differencie=0.0),
    )
    chemins = generer(scenario, tmp_path)

    resultats = omop.lire(chemins.omop / "measurement.parquet")
    concepts = [ligne["measurement_concept_id"] for ligne in resultats]

    assert concepts.count(CONCEPTS.anti_ro52[0]) == 50
    assert concepts.count(CONCEPTS.anti_ro60[0]) == 50


def test_la_cli_accepte_le_mode_dabsences(tmp_path: Path) -> None:
    from sjs_phenotype.cli import main

    travail = tmp_path / "travail"
    fichier = tmp_path / "defauts.toml"
    fichier.write_text('nom = "défauts"\nn_patients = 40\nabsences = "defauts"\n', encoding="utf-8")

    assert main(["generer", "--sortie", str(travail), "--scenario", str(fichier)]) == 0
    assert main(["phenotyper", "--travail", str(travail), "--absences", "defauts"]) == 0

    table = omop.lire(travail / "resultats" / "phenotype.parquet")
    assert len(table) == 40
    assert all(ligne["statut_schirmer"] == "non documenté" for ligne in table)


def test_un_vrai_zero_devient_non_documente_en_defauts(tmp_path: Path) -> None:
    """La perte assumée : sans NULL, un vrai 0 ne se distingue plus d'une absence.

    On perd alors un résultat plutôt que d'en inventer un. C'est le sens sûr, et c'est
    pourquoi le pipeline lit le Parquet plutôt que ClickHouse (ADR-0002, ADR-0005).
    """
    dossier = tmp_path / "omop"
    zero_veritable = {
        **_resultat_vide(1),
        "value_as_number": 0.0,
        "range_high": 20.0,
    }
    omop.ecrire_table(dossier, "person", [_personne(1)])
    omop.ecrire_table(dossier, "measurement", [zero_veritable])

    en_null = run_phenotype(dossier)[0]
    en_defauts = run_phenotype(dossier, Parametres(absences=Absences.DEFAUTS))[0]

    assert en_null.statuts[Item.ANTI_SSA] is Statut.NEGATIF
    assert en_defauts.statuts[Item.ANTI_SSA] is Statut.NON_DOCUMENTE


def test_la_cli_lit_le_mode_dabsences_du_scenario(tmp_path: Path) -> None:
    """Lire en NULL un jeu écrit en défauts donnerait de faux Statuts : la CLI l'évite."""
    from sjs_phenotype.cli import main

    travail = tmp_path / "travail"
    fichier = tmp_path / "defauts.toml"
    fichier.write_text('nom = "défauts"\nn_patients = 40\nabsences = "defauts"\n', encoding="utf-8")
    main(["generer", "--sortie", str(travail), "--scenario", str(fichier)])

    assert main(["phenotyper", "--travail", str(travail)]) == 0

    reference = tmp_path / "reference"
    main(["generer", "--sortie", str(reference), "--patients", "40"])
    main(["phenotyper", "--travail", str(reference)])
    attendu = omop.lire(reference / "resultats" / "phenotype.parquet")
    assert omop.lire(travail / "resultats" / "phenotype.parquet") == attendu
