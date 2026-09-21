"""La chaîne complète, telle que `make all` la déroule."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sjs_phenotype import omop
from sjs_phenotype.cli import main


def test_generer_puis_phenotyper_puis_evaluer(tmp_path: Path) -> None:
    travail = tmp_path / "travail"

    assert main(["generer", "--sortie", str(travail), "--patients", "150", "--graine", "5"]) == 0
    assert main(["phenotyper", "--travail", str(travail)]) == 0
    assert main(["evaluer", "--travail", str(travail)]) == 0

    assert (travail / "omop" / "person.parquet").exists()
    assert (travail / "etat_reel.parquet").exists()
    assert (travail / "resultats" / "phenotype.parquet").exists()

    effectifs = json.loads((travail / "resultats" / "effectifs.json").read_text())
    assert effectifs["total"] == 150
    assert effectifs["par_niveau"]["défini"] == 0
    assert sum(effectifs["par_profil"].values()) == 150


def test_generer_depuis_un_fichier_de_scenario(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    fichier = tmp_path / "essai.toml"
    fichier.write_text(
        'nom = "essai"\nn_patients = 30\n[parts]\npopulation_generale = 1.0\n', encoding="utf-8"
    )

    assert main(["generer", "--sortie", str(travail), "--scenario", str(fichier)]) == 0

    assert "essai" in (travail / "scenario.toml").read_text(encoding="utf-8")


def test_evaluer_avant_de_phenotyper_rend_une_erreur_lisible(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "10"])

    code = main(["evaluer", "--travail", str(travail)])

    assert code != 0
    assert "phenotyper" in capsys.readouterr().err


def test_letat_reel_est_ecrit_hors_du_schema_omop(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "20"])

    tables_omop = {chemin.name for chemin in (travail / "omop").glob("*.parquet")}

    assert "etat_reel.parquet" not in tables_omop


def test_evaluer_sans_dossier_omop_refuse_de_calculer_la_concordance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un comparateur vide faute de données ressemblerait à un comparateur qui ne trouve rien."""
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "20"])
    main(["phenotyper", "--travail", str(travail)])
    for chemin in sorted((travail / "omop").iterdir()):
        chemin.unlink()
    (travail / "omop").rmdir()

    code = main(["evaluer", "--travail", str(travail)])

    assert code != 0
    assert "Concordance" in capsys.readouterr().err


def test_un_seuil_invalide_est_refuse_avant_tout_resultat(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "20"])
    main(["phenotyper", "--travail", str(travail)])

    with pytest.raises(SystemExit):
        main(["evaluer", "--travail", str(travail), "--occurrences-cim10", "0"])


def test_les_resultats_de_concordance_ne_secrasent_pas(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "60"])
    main(["phenotyper", "--travail", str(travail)])

    main(["evaluer", "--travail", str(travail)])
    main(["evaluer", "--travail", str(travail), "--occurrences-cim10", "2"])
    main(["evaluer", "--travail", str(travail), "--niveaux", "défini"])

    produits = sorted(p.name for p in (travail / "resultats").glob("concordance-*.json"))
    assert len(produits) == 3


def test_les_performances_sortent_sur_un_jeu_synthetique(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "120"])
    main(["phenotyper", "--travail", str(travail)])

    assert main(["evaluer", "--travail", str(travail)]) == 0

    (fichier,) = (travail / "resultats").glob("performances-*.json")
    resultat = json.loads(fichier.read_text())
    assert "sensibilite" in resultat
    assert "avertissement" in resultat


def test_sans_etat_reel_aucune_performance_nest_publiee(tmp_path: Path) -> None:
    """Sur l'EDS il n'y a pas de référence : le bloc doit simplement ne pas exister."""
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "40"])
    main(["phenotyper", "--travail", str(travail)])
    (travail / "etat_reel.parquet").unlink()

    assert main(["evaluer", "--travail", str(travail)]) == 0

    assert not list((travail / "resultats").glob("performances-*.json"))


def test_les_resultats_avec_et_sans_exclus_ne_secrasent_pas(tmp_path: Path) -> None:
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "60"])
    main(["phenotyper", "--travail", str(travail)])

    main(["evaluer", "--travail", str(travail)])
    main(["evaluer", "--travail", str(travail), "--avec-exclus"])

    produits = sorted(p.name for p in (travail / "resultats").glob("performances-*.json"))
    assert len(produits) == 2


def test_un_etat_reel_incomplet_est_refuse(tmp_path: Path) -> None:
    """Un statut SjD absent n'est pas un témoin : mieux vaut refuser que deviner."""
    travail = tmp_path / "travail"
    main(["generer", "--sortie", str(travail), "--patients", "20"])
    main(["phenotyper", "--travail", str(travail)])

    lignes = omop.lire(travail / "etat_reel.parquet")
    lignes[0]["sjd"] = None
    omop.ecrire_table(travail, "etat_reel", lignes)

    with pytest.raises(ValueError, match="État réel incomplet"):
        main(["evaluer", "--travail", str(travail)])
