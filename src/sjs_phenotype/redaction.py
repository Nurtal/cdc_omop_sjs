"""Rédaction des comptes rendus synthétiques.

Les gabarits reproduisent les tournures des comptes rendus français : un focus score
chiffré, un intervalle, un grade de Chisholm-Mason sans focus score, une négation, une
sialadénite qui n'est pas focale. C'est cette variété qui rendra l'évaluation de
l'extracteur crédible — un extracteur mis au point sur une seule tournure ne prouve rien.

Ce module ne fabrique que du texte : les faits viennent de l'État réel du patient.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

SIALADENITE_FOCALE = "focale"
SIALADENITE_ABSENTE = "absente"
SIALADENITES_NON_FOCALES = ("sclérosante", "granulomateuse")


@dataclass(frozen=True)
class Biopsie:
    """Ce qu'une biopsie a réellement montré.

    Les trois champs décrivent la même lame et ne peuvent pas se contredire : une
    sialadénite non focale ne permet aucun focus score (`None`, « non calculable »), une
    glande normale en donne un à zéro, et le grade de Chisholm-Mason découle du score.
    """

    focus_score: float | None
    grade_chisholm: int | None
    sialadenite: str

    def __post_init__(self) -> None:
        calculable = self.sialadenite in (SIALADENITE_FOCALE, SIALADENITE_ABSENTE)
        if calculable != (self.focus_score is not None):
            raise ValueError(f"focus score et sialadénite {self.sialadenite} incohérents")
        if self.focus_score is not None and grade_pour(self.focus_score) != self.grade_chisholm:
            raise ValueError("grade de Chisholm-Mason incohérent avec le focus score")

    @property
    def positive(self) -> bool:
        return self.focus_score is not None and self.focus_score >= 1.0


def grade_pour(focus_score: float | None) -> int | None:
    """Grade de Chisholm-Mason correspondant à un focus score.

    Grade 3 vaut un foyer pour 4 mm², grade 4 davantage : le seuil de grade 3 coïncide
    donc avec le seuil de focus score ≥ 1 des critères ACR/EULAR.
    """
    if focus_score is None:
        return None
    if focus_score >= 2.0:
        return 4
    if focus_score >= 1.0:
        return 3
    if focus_score > 0.0:
        return 2
    return 1


_CHIFFRE = (
    (
        "Biopsie de glande salivaire accessoire. Sialadénite lymphocytaire focale, "
        "focus score à {score} pour 4 mm²."
    ),
    (
        "Prélèvement de glandes salivaires accessoires. Présence d'une sialadénite "
        "lymphocytaire focale. Focus score : {score}."
    ),
    "BGSA. Infiltrat lymphocytaire focal, score de focus évalué à {score} / 4 mm².",
)
_INTERVALLE = (
    (
        "Biopsie de glande salivaire accessoire. Sialadénite lymphocytaire focale, focus "
        "score entre {bas} et {haut} selon les champs examinés."
    ),
    "BGSA : infiltrat focal hétérogène, focus score de {bas} à {haut} pour 4 mm².",
)
_GRADE_SEUL = (
    (
        "Biopsie de glande salivaire accessoire. Sialadénite lymphocytaire, "
        "stade {grade} de Chisholm et Mason."
    ),
    "BGSA. Aspect compatible avec un grade {grade} de la classification de Chisholm-Mason.",
)
_SOUS_SEUIL = (
    (
        "Biopsie de glande salivaire accessoire. Infiltrat lymphocytaire focal de faible "
        "abondance, focus score à {score} pour 4 mm²."
    ),
    (
        "BGSA. Quelques foyers lymphocytaires, focus score évalué à {score}, sous le seuil "
        "de 1 foyer pour 4 mm²."
    ),
)
_NEGATIF = (
    (
        "Biopsie de glande salivaire accessoire. Absence de sialadénite lymphocytaire "
        "focale. Focus score non calculable."
    ),
    (
        "BGSA. Parenchyme salivaire sans infiltrat lymphocytaire focal significatif. "
        "Absence de sialadénite focale."
    ),
    (
        "Prélèvement de glandes salivaires accessoires. Quelques lymphocytes épars, sans "
        "foyer constitué. Focus score à 0."
    ),
)
_AUTRE_SIALADENITE = (
    (
        "Biopsie de glande salivaire accessoire. Sialadénite chronique sclérosante, sans "
        "infiltrat focal. Focus score non calculable."
    ),
    "BGSA. Sialadénite granulomateuse. Absence de sialadénite lymphocytaire focale.",
)

_COURRIER = (
    (
        "Consultation de rhumatologie. Test de Schirmer à {schirmer} mm en 5 minutes à "
        "droite. Débit salivaire non stimulé mesuré à {debit} mL/min."
    ),
    (
        "Bilan de sécheresse. Schirmer : {schirmer} mm/5 min. Score de coloration oculaire "
        "(OSS) à {oss}. Flux salivaire non stimulé {debit} mL/min."
    ),
    (
        "Courrier d'ophtalmologie. OSS évalué à {oss}. Schirmer {schirmer} mm. Le débit "
        "salivaire non stimulé est de {debit} mL/min."
    ),
)


def compte_rendu_biopsie(biopsie: Biopsie, hasard: random.Random) -> str:
    """Rédige un compte rendu qui dit la vérité, mais pas toujours de la même manière.

    Un extracteur sera un jour noté contre l'État réel : le texte ne doit donc jamais
    dire autre chose que ce que la lame a montré. Un focus score de 0,8 s'écrit « 0,8 »,
    jamais « 0 ».
    """
    if biopsie.focus_score is None:
        return hasard.choice(_AUTRE_SIALADENITE)
    if biopsie.focus_score == 0.0:
        return hasard.choice(_NEGATIF)
    if not biopsie.positive:
        return hasard.choice(_SOUS_SEUIL).format(score=_nombre(biopsie.focus_score))

    gabarit = hasard.choice(_CHIFFRE + _INTERVALLE + _GRADE_SEUL)
    if gabarit in _GRADE_SEUL:
        return gabarit.format(grade=biopsie.grade_chisholm)
    if gabarit in _INTERVALLE:
        bas = _nombre(biopsie.focus_score)
        haut = _nombre(biopsie.focus_score + 1)
        return gabarit.format(bas=bas, haut=haut)
    return gabarit.format(score=_nombre(biopsie.focus_score))


def courrier_secheresse(schirmer: int, oss: int, debit: float, hasard: random.Random) -> str:
    return hasard.choice(_COURRIER).format(
        schirmer=schirmer, oss=oss, debit=f"{debit:.2f}".replace(".", ",")
    )


def _nombre(valeur: float) -> str:
    """Les comptes rendus français écrivent « 1,5 », pas « 1.5 »."""
    texte = f"{valeur:g}"
    return texte.replace(".", ",")
