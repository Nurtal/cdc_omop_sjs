"""Seam 3 : `extraire(texte) -> faits`, et ce que le pipeline fait des faits.

Un extracteur reçoit une note et rend des Faits : un Item ACR/EULAR, une valeur, et de
quoi retrouver le passage. Il ne connaît ni les seuils, ni les scores, ni OMOP — c'est la
Définition computable qui décide ce qu'un focus score de 2 vaut.

Ce module ne livre aucun extracteur réel : seulement le contrat, l'implémentation qui ne
rend rien, et le raccordement à OMOP. Le jalon suivant y branchera edsnlp sans toucher au
reste.

Les faits extraits laissent une trace dans NOTE_NLP — pour retrouver le passage d'origine —
et deviennent des lignes MEASUREMENT marquées du type « NLP » (ADR-0002). La Définition
computable lit MEASUREMENT sans se soucier de l'origine ; le marquage sert au retrait de
source, qui mesurera un jour ce que le texte apporte.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from sjs_phenotype import omop
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.modele import Item

# Les Items qu'un extracteur peut rapporter : ceux qui portent une valeur numérique.
# L'Anti-SSA vient d'un résultat structuré, jamais du texte.
ITEMS_EXTRACTIBLES: frozenset[Item] = frozenset(
    {Item.FOCUS_SCORE, Item.OSS, Item.SCHIRMER, Item.DEBIT_SALIVAIRE}
)


class Origine(StrEnum):
    """D'où vient le Statut d'un Item : d'une donnée structurée, du texte, ou de nulle part."""

    STRUCTUREE = "structurée"
    TEXTE = "texte"
    AUCUNE = "aucune"


@dataclass(frozen=True)
class Fait:
    """Un Item ACR/EULAR lu dans une note, et le passage qui le porte.

    L'extracteur rapporte ce qu'il lit, jamais ce qu'il en conclut : `valeur` est la
    mesure telle qu'écrite, et c'est la Définition computable qui applique le seuil.
    """

    note_id: int
    person_id: int
    jour: date
    item: Item
    valeur: float
    extrait: str
    debut: int
    fin: int

    def __post_init__(self) -> None:
        if self.item not in ITEMS_EXTRACTIBLES:
            raise ValueError(
                f"{self.item} ne se lit pas dans un compte rendu ; "
                f"Items extractibles : {sorted(item.value for item in ITEMS_EXTRACTIBLES)}"
            )


class Extracteur(Protocol):
    """Le contrat du seam 3. Une note entre, des Faits sortent."""

    def __call__(self, note: dict[str, Any]) -> Sequence[Fait]: ...


def aucune_extraction(note: dict[str, Any]) -> list[Fait]:
    """L'extracteur par défaut : il ne lit rien, et le pipeline se comporte comme avant."""
    return []


def extraire_notes(
    dossier_omop: Path,
    extracteur: Extracteur = aucune_extraction,
    vocabulaire: Vocabulaire | None = None,
    absences: omop.Absences = omop.Absences.NULL,
    systeme: str = "bouchon",
) -> list[Fait]:
    """Passe l'extracteur sur toutes les notes et verse les Faits dans OMOP.

    Idempotent : relancer l'extraction remplace les lignes que ce système avait produites,
    et laisse intactes les lignes structurées comme celles d'un autre extracteur. Sans
    Fait à verser, rien n'est réécrit : l'extracteur par défaut ne doit rien détruire.

    `absences` doit être celui du dossier : mélanger deux encodages dans une même table
    contredirait le manifeste qui la décrit.
    """
    chemin_notes = dossier_omop / "note.parquet"
    if not chemin_notes.exists():
        return []

    vocabulaire = vocabulaire or Vocabulaire.par_defaut()
    faits = [fait for note in omop.lire(chemin_notes) for fait in extracteur(note)]
    if not faits:
        return []

    _ecrire_note_nlp(dossier_omop, faits, vocabulaire, absences, systeme)
    _verser_dans_measurement(dossier_omop, faits, vocabulaire, absences)
    return faits


def _ecrire_note_nlp(
    dossier_omop: Path,
    faits: Sequence[Fait],
    vocabulaire: Vocabulaire,
    absences: omop.Absences,
    systeme: str,
) -> None:
    """La trace de ce qui a été lu, et où : c'est ce qui rend une extraction vérifiable.

    Les traces d'un autre système sont conservées : NOTE_NLP peut accueillir plusieurs
    extracteurs, et effacer le travail d'un voisin serait une perte silencieuse.
    """
    chemin = dossier_omop / "note_nlp.parquet"
    autres = [
        ligne
        for ligne in (omop.lire(chemin) if chemin.exists() else [])
        if ligne["nlp_system"] != systeme
    ]
    depart = max((int(ligne["note_nlp_id"]) for ligne in autres), default=0)
    omop.ecrire_table(
        dossier_omop,
        "note_nlp",
        autres
        + [
            {
                "note_nlp_id": depart + rang,
                "note_id": fait.note_id,
                "section_concept_id": None,
                "snippet": fait.extrait,
                "offset": str(fait.debut),
                "lexical_variant": fait.extrait,
                "note_nlp_concept_id": vocabulaire.items.concept(fait.item.value),
                "nlp_system": systeme,
                "term_exists": "Y",
            }
            for rang, fait in enumerate(faits, start=1)
        ],
        absences=absences,
    )


def _verser_dans_measurement(
    dossier_omop: Path,
    faits: Sequence[Fait],
    vocabulaire: Vocabulaire,
    absences: omop.Absences,
) -> None:
    """Ajoute les Faits à MEASUREMENT, en remplaçant ceux d'une extraction précédente."""
    chemin = dossier_omop / "measurement.parquet"
    type_nlp = vocabulaire.items.concept("type_nlp")
    structurees = [
        ligne
        for ligne in (omop.lire(chemin) if chemin.exists() else [])
        if ligne["measurement_type_concept_id"] != type_nlp
    ]
    depart = max((int(ligne["measurement_id"]) for ligne in structurees), default=0)

    derivees = [
        {
            "measurement_id": depart + rang,
            "person_id": fait.person_id,
            "measurement_concept_id": vocabulaire.items.concept(fait.item.value),
            "measurement_date": fait.jour,
            "value_as_number": fait.valeur,
            "value_as_concept_id": None,
            "range_high": None,
            "measurement_source_value": fait.extrait,
            "measurement_type_concept_id": type_nlp,
            "measurement_event_id": fait.note_id,
            "meas_event_field_concept_id": vocabulaire.items.concept("champ_note_id"),
            "visit_occurrence_id": None,
        }
        for rang, fait in enumerate(faits, start=1)
    ]
    omop.ecrire_table(dossier_omop, "measurement", structurees + derivees, absences=absences)
