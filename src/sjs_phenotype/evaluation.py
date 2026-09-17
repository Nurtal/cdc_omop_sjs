"""Seam 2 : une table phénotype entre, des tables de résultats sortent.

Fonction pure : aucune lecture de fichier, aucun accès au jeu de données. C'est ce qui
permet de vérifier les chiffres sur de petites tables écrites à la main.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut


@dataclass(frozen=True)
class Effectifs:
    """Combien de patients par Niveau de certitude, et par Statut de chaque Item."""

    total: int
    par_niveau: Mapping[Niveau, int]
    par_statut: Mapping[Item, Mapping[Statut, int]]

    def en_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "par_niveau": {str(niveau): nombre for niveau, nombre in self.par_niveau.items()},
            "par_statut": {
                str(item): {str(statut): nombre for statut, nombre in statuts.items()}
                for item, statuts in self.par_statut.items()
            },
        }


def evaluer(table: Sequence[LignePhenotype]) -> Effectifs:
    par_niveau = {niveau: 0 for niveau in Niveau}
    par_statut = {item: {statut: 0 for statut in Statut} for item in Item}
    for ligne in table:
        par_niveau[ligne.niveau] += 1
        for item, statut in ligne.statuts.items():
            par_statut[item][statut] += 1
    return Effectifs(total=len(table), par_niveau=par_niveau, par_statut=par_statut)


def formater(effectifs: Effectifs) -> str:
    """Rendu lisible en terminal, dans le vocabulaire du glossaire."""
    lignes = [f"Patients : {effectifs.total}", "", "Niveau de certitude"]
    lignes += [f"  {niveau:<14} {nombre:>6}" for niveau, nombre in effectifs.par_niveau.items()]
    lignes += ["", "Statut par Item ACR/EULAR"]
    for item, statuts in effectifs.par_statut.items():
        detail = "  ".join(f"{statut} {nombre}" for statut, nombre in statuts.items())
        lignes.append(f"  {item:<16} {detail}")
    return "\n".join(lignes)
