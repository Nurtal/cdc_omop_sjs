"""Le vocabulaire de `CONTEXT.md`, en types.

Item ACR/EULAR, Statut d'item, Score observé, Score atteignable, Niveau de certitude.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Statut(StrEnum):
    """Statut d'un Item ACR/EULAR pour un patient.

    « Non documenté » n'est jamais assimilé à « négatif » (ADR-0005).
    """

    POSITIF = "positif"
    NEGATIF = "négatif"
    NON_DOCUMENTE = "non documenté"


class Item(StrEnum):
    """Les cinq Items pondérés des critères ACR/EULAR 2016."""

    FOCUS_SCORE = "focus_score"
    ANTI_SSA = "anti_ssa"
    OSS = "oss"
    SCHIRMER = "schirmer"
    DEBIT_SALIVAIRE = "debit_salivaire"

    @property
    def points(self) -> int:
        return _POINTS[self]


_POINTS: Mapping[Item, int] = {
    Item.FOCUS_SCORE: 3,
    Item.ANTI_SSA: 3,
    Item.OSS: 1,
    Item.SCHIRMER: 1,
    Item.DEBIT_SALIVAIRE: 1,
}

SCORE_MAXIMAL = sum(_POINTS.values())


class Niveau(StrEnum):
    """Niveau de certitude attribué par la Définition computable."""

    DEFINI = "défini"
    PROBABLE = "probable"
    AUCUN = "aucun"


@dataclass(frozen=True)
class LignePhenotype:
    """Une ligne de la table phénotype : le Profil de preuves d'un patient, et ce qu'il vaut."""

    person_id: int
    statuts: Mapping[Item, Statut]
    score_observe: int
    score_atteignable: int
    niveau: Niveau
    dates_atteinte: Mapping[Niveau, date]
    criteres_exclusion: tuple[str, ...] = ()

    @property
    def exclu(self) -> bool:
        """Un patient exclu garde son Niveau : il est signalé, pas retiré."""
        return bool(self.criteres_exclusion)

    def __eq__(self, autre: object) -> bool:
        if not isinstance(autre, LignePhenotype):
            return NotImplemented
        return (
            self.person_id == autre.person_id
            and dict(self.statuts) == dict(autre.statuts)
            and self.score_observe == autre.score_observe
            and self.score_atteignable == autre.score_atteignable
            and self.niveau == autre.niveau
            and dict(self.dates_atteinte) == dict(autre.dates_atteinte)
            and self.criteres_exclusion == autre.criteres_exclusion
        )

    def __hash__(self) -> int:
        return hash((self.person_id, self.score_observe, self.niveau))


def niveau_pour(score_observe: int, score_atteignable: int) -> Niveau:
    """Défini si le Score observé atteint 4 ; Probable si le bilan peut encore y arriver."""
    if score_observe >= 4:
        return Niveau.DEFINI
    if score_observe >= 3 and score_atteignable >= 4:
        return Niveau.PROBABLE
    return Niveau.AUCUN
