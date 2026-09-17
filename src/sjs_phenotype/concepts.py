"""Jeux de concepts versionnés, chargés depuis le dépôt (ADR-0002).

La Définition computable ne connaît aucun identifiant en dur : tout vient d'ici.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JeuDeConcepts:
    """Les concepts de l'Item Anti-SSA, et les valeurs qui disent positif ou négatif."""

    anti_ro60: tuple[int, ...]
    anti_ro52: tuple[int, ...]
    anti_ssa_non_differencie: tuple[int, ...]
    valeur_positive: int
    valeur_negative: int

    @property
    def anti_ssa(self) -> tuple[int, ...]:
        """Ce qui compte comme Anti-SSA : le Ro60 et le rendu non différencié, pas le Ro52."""
        return self.anti_ro60 + self.anti_ssa_non_differencie

    @classmethod
    def charger(cls, chemin: Path) -> JeuDeConcepts:
        return cls._depuis(json.loads(chemin.read_text(encoding="utf-8")))

    @classmethod
    def par_defaut(cls) -> JeuDeConcepts:
        fichier = resources.files("sjs_phenotype.jeux_de_concepts") / "anti_ssa.json"
        return cls._depuis(json.loads(fichier.read_text(encoding="utf-8")))

    @classmethod
    def _depuis(cls, contenu: dict[str, Any]) -> JeuDeConcepts:
        return cls(
            anti_ro60=tuple(contenu["anti_ro60"]),
            anti_ro52=tuple(contenu["anti_ro52"]),
            anti_ssa_non_differencie=tuple(contenu["anti_ssa_non_differencie"]),
            valeur_positive=int(contenu["valeur_positive"]),
            valeur_negative=int(contenu["valeur_negative"]),
        )
