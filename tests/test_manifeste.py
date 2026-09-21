"""Manifeste : rattacher un résultat à ce qui l'a produit (Reproductibilité).

Un chiffre sans manifeste n'est pas reproductible : on ne sait ni quel code, ni quels
concepts, ni quels paramètres l'ont produit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sjs_phenotype.cli import main
from sjs_phenotype.manifeste import Manifeste, empreinte_fichier


def _manifeste(travail: Path) -> dict[str, Any]:
    contenu: dict[str, Any] = json.loads(
        (travail / "resultats" / "manifeste.json").read_text(encoding="utf-8")
    )
    return contenu


def _executer(travail: Path, patients: int = 40, graine: int = 0) -> None:
    main(
        ["generer", "--sortie", str(travail), "--patients", str(patients), "--graine", str(graine)]
    )
    main(["phenotyper", "--travail", str(travail)])


def test_une_execution_ecrit_un_manifeste(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    _executer(travail)

    contenu = _manifeste(travail)

    assert contenu["version_code"]
    assert contenu["horodatage"]
    assert contenu["scenario"]
    assert contenu["entrees"]
    assert contenu["vocabulaire"]


def test_deux_executions_identiques_donnent_le_meme_manifeste(tmp_path: Path) -> None:
    """Hors horodatage : c'est la définition même de la Reproductibilité."""
    premier, second = tmp_path / "a", tmp_path / "b"
    _executer(premier, graine=7)
    _executer(second, graine=7)

    avant, apres = _manifeste(premier), _manifeste(second)
    del avant["horodatage"], apres["horodatage"]
    del avant["travail"], apres["travail"]

    assert avant == apres


def test_changer_la_graine_change_les_empreintes(tmp_path: Path) -> None:
    premier, second = tmp_path / "a", tmp_path / "b"
    _executer(premier, graine=1)
    _executer(second, graine=2)

    assert _manifeste(premier)["entrees"] != _manifeste(second)["entrees"]


def test_le_manifeste_porte_lempreinte_du_vocabulaire(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    _executer(travail)

    vocabulaire = _manifeste(travail)["vocabulaire"]

    assert isinstance(vocabulaire, dict)
    assert vocabulaire["empreinte"]
    assert set(vocabulaire["jeux"]) >= {"anti_ssa", "diagnostics", "notes"}


def test_le_manifeste_signale_les_concepts_locaux(tmp_path: Path) -> None:
    """L'entorse aux concepts standard doit rester visible (ADR-0002)."""
    travail = tmp_path / "travail"
    _executer(travail)

    vocabulaire = _manifeste(travail)["vocabulaire"]

    assert isinstance(vocabulaire, dict)
    locaux = vocabulaire["concepts_locaux"]
    assert locaux, "l'entorse aux concepts standard doit rester visible"
    assert all(
        concept_id >= vocabulaire["seuil_concept_local"]
        for identifiants in locaux.values()
        for concept_id in identifiants
    )
    assert vocabulaire["jeux_a_verifier"]


def test_une_empreinte_change_avec_le_contenu(tmp_path: Path) -> None:
    fichier = tmp_path / "essai.txt"
    fichier.write_text("un", encoding="utf-8")
    avant = empreinte_fichier(fichier)
    fichier.write_text("deux", encoding="utf-8")

    assert empreinte_fichier(fichier) != avant


def test_le_manifeste_se_relit(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    _executer(travail)

    relu = Manifeste.lire(travail / "resultats" / "manifeste.json")

    assert relu.version_code
    assert relu.scenario["nom"] == "défaut"


def test_un_manifeste_absent_est_signale(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        Manifeste.lire(tmp_path / "manquant.json")


def test_les_concepts_serologiques_sont_standard() -> None:
    """Vérifiés dans LOINC le 2026-09-21 : ils ne doivent plus être des identifiants locaux."""
    from sjs_phenotype.concepts import PREMIER_CONCEPT_LOCAL, Vocabulaire

    anti_ssa = Vocabulaire.par_defaut().anti_ssa
    serologie = (
        *anti_ssa.anti_ro60,
        *anti_ssa.anti_ro52,
        *anti_ssa.anti_ssa_non_differencie,
        *anti_ssa.anti_ssb,
    )

    assert serologie
    assert all(concept_id < PREMIER_CONCEPT_LOCAL for concept_id in serologie)


def test_les_items_sans_concept_standard_sont_nommes() -> None:
    """Focus score et OSS n'ont aucun équivalent LOINC ni SNOMED : l'entorse reste visible."""
    from sjs_phenotype.concepts import PREMIER_CONCEPT_LOCAL, Vocabulaire

    items = Vocabulaire.par_defaut().items
    sans_standard = items.groupe("sans_concept_standard")

    assert set(sans_standard) == {"focus_score", "oss"}
    assert all(items.concept(code) >= PREMIER_CONCEPT_LOCAL for code in sans_standard)
    assert items.concept("schirmer_droit") < PREMIER_CONCEPT_LOCAL
    assert items.concept("debit_salivaire") < PREMIER_CONCEPT_LOCAL


def test_le_manifeste_enregistre_lencodage_reellement_utilise(tmp_path: Path) -> None:
    """Lire en « defauts » un jeu écrit en NULL donne d'autres Statuts : ça doit se voir."""
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "20"])
    main(["phenotyper", "--travail", str(travail), "--absences", "defauts"])

    assert _manifeste(travail)["absences"] == "defauts"


def test_le_manifeste_porte_tous_les_parametres_du_scenario(tmp_path: Path) -> None:
    """Un bloc partiel laisserait croire que deux scénarios distincts sont identiques."""
    travail = tmp_path / "travail"
    fichier = tmp_path / "essai.toml"
    fichier.write_text(
        'nom = "essai"\nn_patients = 20\npart_vhc_actif_si_exclusion = 0.25\n',
        encoding="utf-8",
    )
    main(["generer", "--sortie", str(travail), "--scenario", str(fichier)])
    main(["phenotyper", "--travail", str(travail)])

    scenario = _manifeste(travail)["scenario"]
    assert scenario["part_vhc_actif_si_exclusion"] == 0.25
    assert {"part_ro52_isole_si_lupus", "part_compte_rendu_manquant", "debut", "fin"} <= set(
        scenario
    )


def test_tous_les_jeux_de_concepts_entrent_dans_lempreinte() -> None:
    """Un jeu ajouté plus tard doit changer l'empreinte, sinon elle ne sert à rien."""
    from sjs_phenotype.manifeste import etat_vocabulaire, jeux_de_concepts

    livres = set(jeux_de_concepts())
    empreintes = set(etat_vocabulaire()["jeux"])

    assert livres == empreintes
    assert "items" in livres
