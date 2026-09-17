"""Interface en ligne de commande : générer, phénotyper, évaluer.

Le `Makefile` enchaîne ces trois commandes sur un même dossier de travail.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from sjs_phenotype import phenotype
from sjs_phenotype.evaluation import evaluer, formater
from sjs_phenotype.generator import Scenario, generer


def main(arguments: Sequence[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(prog="sjs-phenotype", description=__doc__)
    commandes = analyseur.add_subparsers(dest="commande", required=True)

    generation = commandes.add_parser("generer", help="écrire un jeu OMOP synthétique")
    generation.add_argument("--sortie", type=Path, required=True)
    generation.add_argument("--patients", type=int, default=Scenario.n_patients)
    generation.add_argument("--graine", type=int, default=Scenario.graine)

    calcul = commandes.add_parser("phenotyper", help="calculer la table phénotype")
    calcul.add_argument("--travail", type=Path, required=True)

    bilan = commandes.add_parser("evaluer", help="compter les patients par Niveau et par Statut")
    bilan.add_argument("--travail", type=Path, required=True)

    options = analyseur.parse_args(arguments)

    if options.commande == "generer":
        chemins = generer(
            Scenario(n_patients=options.patients, graine=options.graine), options.sortie
        )
        print(f"Jeu OMOP : {chemins.omop}\nÉtat réel : {chemins.etat_reel}")
        return 0

    resultats = options.travail / "resultats"
    if options.commande == "phenotyper":
        table = phenotype.run_phenotype(options.travail / "omop")
        chemin = phenotype.ecrire(table, resultats)
        print(f"Table phénotype : {chemin} ({len(table)} patients)")
        return 0

    if options.commande == "evaluer":
        chemin = resultats / "phenotype.parquet"
        if not chemin.exists():
            print(
                f"Table phénotype introuvable : {chemin}. Lancez d'abord « phenotyper ».",
                file=sys.stderr,
            )
            return 1
        effectifs = evaluer(phenotype.lire(chemin))
        (resultats / "effectifs.json").write_text(
            json.dumps(effectifs.en_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(formater(effectifs))
        return 0

    raise AssertionError(f"commande non gérée : {options.commande}")


if __name__ == "__main__":
    raise SystemExit(main())
