"""Jeux de concepts versionnés, chargés depuis le dépôt (ADR-0002).

La Définition computable ne connaît aucun identifiant en dur : tout vient d'ici.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
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


@dataclass(frozen=True)
class Table:
    """Une table de correspondance code → concept, plus les regroupements qu'elle déclare."""

    concepts: Mapping[str, int]
    libelles: Mapping[str, str]
    groupes: Mapping[str, tuple[str, ...]]

    def concept(self, code: str) -> int:
        return self.concepts[code]

    def groupe(self, nom: str) -> tuple[str, ...]:
        return self.groupes[nom]

    @classmethod
    def charger(cls, fichier: str) -> Table:
        chemin = resources.files("sjs_phenotype.jeux_de_concepts") / fichier
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        codes: dict[str, dict[str, Any]] = contenu["codes"]
        groupes = {nom: tuple(membres) for nom, membres in contenu.get("groupes", {}).items()}
        return cls(
            concepts={code: int(detail["concept_id"]) for code, detail in codes.items()},
            libelles={code: str(detail["libelle"]) for code, detail in codes.items()},
            groupes=groupes,
        )


@dataclass(frozen=True)
class Vocabulaire:
    """Tous les jeux de concepts du projet, chargés d'un coup."""

    anti_ssa: JeuDeConcepts
    diagnostics: Table
    medicaments: Table
    visites: Table

    @classmethod
    def par_defaut(cls) -> Vocabulaire:
        return cls(
            anti_ssa=JeuDeConcepts.par_defaut(),
            diagnostics=Table.charger("diagnostics.json"),
            medicaments=Table.charger("medicaments.json"),
            visites=Table.charger("visites.json"),
        )
