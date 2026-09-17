"""Seam 2 : une table phénotype entre, des tables de résultats sortent.

Fonction pure : aucune lecture de fichier, aucun accès au jeu de données. C'est ce qui
permet de vérifier les chiffres sur de petites tables écrites à la main.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut

PROFIL_INCONNU = "profil inconnu"


@dataclass(frozen=True)
class Effectifs:
    """Combien de patients par Niveau de certitude, par Statut d'Item, et par Profil."""

    total: int
    par_niveau: Mapping[Niveau, int]
    par_statut: Mapping[Item, Mapping[Statut, int]]
    par_profil: Mapping[str, int]

    def en_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "par_niveau": {str(niveau): nombre for niveau, nombre in self.par_niveau.items()},
            "par_statut": {
                str(item): {str(statut): nombre for statut, nombre in statuts.items()}
                for item, statuts in self.par_statut.items()
            },
            "par_profil": dict(self.par_profil),
        }


def evaluer(table: Sequence[LignePhenotype], profils: Mapping[int, str] | None = None) -> Effectifs:
    """Compte les patients. `profils` vient de l'État réel, connu du seul jeu synthétique."""
    par_niveau = {niveau: 0 for niveau in Niveau}
    par_statut = {item: {statut: 0 for statut in Statut} for item in Item}
    par_profil: dict[str, int] = {}
    for ligne in table:
        par_niveau[ligne.niveau] += 1
        for item, statut in ligne.statuts.items():
            par_statut[item][statut] += 1
        if profils is not None:
            # Un État réel dépareillé (jeu régénéré, dossier réutilisé) doit se voir dans
            # les chiffres, pas faire tomber l'évaluation.
            profil = profils.get(ligne.person_id, PROFIL_INCONNU)
            par_profil[profil] = par_profil.get(profil, 0) + 1
    return Effectifs(
        total=len(table),
        par_niveau=par_niveau,
        par_statut=par_statut,
        par_profil=par_profil,
    )


def formater(effectifs: Effectifs) -> str:
    """Rendu lisible en terminal, dans le vocabulaire du glossaire."""
    lignes = [f"Patients : {effectifs.total}", "", "Niveau de certitude"]
    lignes += [f"  {niveau:<14} {nombre:>6}" for niveau, nombre in effectifs.par_niveau.items()]
    lignes += ["", "Statut par Item ACR/EULAR"]
    for item, statuts in effectifs.par_statut.items():
        detail = "  ".join(f"{statut} {nombre}" for statut, nombre in statuts.items())
        lignes.append(f"  {item:<16} {detail}")
    if effectifs.par_profil:
        lignes += ["", "Profil (État réel, jeu synthétique)"]
        lignes += [
            f"  {profil:<32} {nombre:>6}" for profil, nombre in sorted(effectifs.par_profil.items())
        ]
    return "\n".join(lignes)
