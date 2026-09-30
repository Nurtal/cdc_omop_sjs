"""Seam 3 : `extraire(texte) -> faits`.

Le contrat seul est livré ici, avec une implémentation qui ne rend rien. Le jalon suivant
remplacera le bouchon par un extracteur edsnlp réel sans toucher au reste du pipeline :
c'est ce que ce ticket doit prouver.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.extraction import (
    Fait,
    Origine,
    aucune_extraction,
    extraire_notes,
)
from sjs_phenotype.modele import Item, Niveau, Statut
from sjs_phenotype.phenotype import run_phenotype

VOCABULAIRE = Vocabulaire.par_defaut()


def _personne(person_id: int) -> dict[str, Any]:
    return {"person_id": person_id, "gender_concept_id": 8532, "year_of_birth": 1970}


def _anti_ssa_positif(person_id: int) -> dict[str, Any]:
    return {
        "measurement_id": person_id * 10,
        "person_id": person_id,
        "measurement_concept_id": VOCABULAIRE.anti_ssa.anti_ro60[0],
        "measurement_date": date(2018, 4, 1),
        "value_as_number": None,
        "value_as_concept_id": VOCABULAIRE.valeur_positive,
        "range_high": None,
        "measurement_source_value": "anti-SSA",
        "measurement_type_concept_id": VOCABULAIRE.items.concept("type_ehr"),
        "measurement_event_id": None,
        "meas_event_field_concept_id": None,
        "visit_occurrence_id": None,
    }


def _note(person_id: int, texte: str) -> dict[str, Any]:
    return {
        "note_id": person_id * 100,
        "person_id": person_id,
        "note_date": date(2019, 9, 2),
        "note_class_concept_id": VOCABULAIRE.notes.concept("anatomopathologie"),
        "note_title": "Compte rendu d'anatomopathologie",
        "note_text": texte,
        "visit_occurrence_id": None,
    }


def _jeu(dossier: Path, notes: list[dict[str, Any]], mesures: list[dict[str, Any]]) -> Path:
    omop.ecrire_table(dossier, "person", [_personne(1)])
    omop.ecrire_table(dossier, "measurement", mesures)
    omop.ecrire_table(dossier, "note", notes)
    return dossier


def _focus_score_positif(note_id: int, person_id: int, jour: date) -> list[Fait]:
    return [
        Fait(
            note_id=note_id,
            person_id=person_id,
            jour=jour,
            item=Item.FOCUS_SCORE,
            valeur=2.0,
            extrait="focus score à 2",
            debut=10,
            fin=25,
        )
    ]


def test_lextracteur_par_defaut_ne_rend_aucun_fait() -> None:
    assert aucune_extraction(_note(1, "focus score à 2 pour 4 mm²")) == []


def test_sans_extraction_le_pipeline_se_comporte_comme_avant(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "Sialadénite lymphocytaire focale, focus score à 2.")],
        mesures=[_anti_ssa_positif(1)],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.FOCUS_SCORE] is Statut.NON_DOCUMENTE
    assert ligne.niveau is Niveau.PROBABLE


def test_un_extracteur_bouchon_fait_passer_a_defini(tmp_path: Path) -> None:
    """La preuve que le chemin fonctionne de bout en bout, avant tout vrai extracteur."""
    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "Sialadénite lymphocytaire focale, focus score à 2.")],
        mesures=[_anti_ssa_positif(1)],
    )

    extraire_notes(dossier, extracteur=_bouchon)
    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.FOCUS_SCORE] is Statut.POSITIF
    assert ligne.score_observe == 6
    assert ligne.niveau is Niveau.DEFINI


def test_les_faits_laissent_une_trace_dans_note_nlp(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "Sialadénite lymphocytaire focale, focus score à 2.")],
        mesures=[],
    )

    extraire_notes(dossier, extracteur=_bouchon)

    (trace,) = omop.lire(dossier / "note_nlp.parquet")
    assert trace["note_id"] == 100
    assert trace["lexical_variant"] == "focus score à 2"
    assert trace["offset"] == "10"


def test_les_faits_deviennent_des_lignes_marquees_nlp(tmp_path: Path) -> None:
    """La Définition computable lit MEASUREMENT sans se soucier de l'origine (ADR-0002)."""
    dossier = _jeu(tmp_path / "omop", notes=[_note(1, "focus score à 2")], mesures=[])

    extraire_notes(dossier, extracteur=_bouchon)

    (mesure,) = omop.lire(dossier / "measurement.parquet")
    assert mesure["measurement_concept_id"] == VOCABULAIRE.items.concept("focus_score")
    assert mesure["measurement_type_concept_id"] == VOCABULAIRE.items.concept("type_nlp")
    assert mesure["value_as_number"] == 2.0
    assert mesure["measurement_event_id"] == 100
    assert mesure["meas_event_field_concept_id"] == VOCABULAIRE.items.concept("champ_note_id")


def test_lorigine_de_chaque_item_est_lisible(tmp_path: Path) -> None:
    """Préparation du retrait de source : il faudra savoir ce que le texte a apporté."""
    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "focus score à 2")],
        mesures=[_anti_ssa_positif(1)],
    )
    extraire_notes(dossier, extracteur=_bouchon)

    (ligne,) = run_phenotype(dossier)

    assert ligne.origines[Item.ANTI_SSA] is Origine.STRUCTUREE
    assert ligne.origines[Item.FOCUS_SCORE] is Origine.TEXTE
    assert ligne.origines[Item.SCHIRMER] is Origine.AUCUNE


def test_lextraction_est_idempotente(tmp_path: Path) -> None:
    """Relancer l'extraction ne doit pas empiler deux fois les mêmes faits."""
    dossier = _jeu(tmp_path / "omop", notes=[_note(1, "focus score à 2")], mesures=[])

    extraire_notes(dossier, extracteur=_bouchon)
    extraire_notes(dossier, extracteur=_bouchon)

    assert len(omop.lire(dossier / "measurement.parquet")) == 1
    assert len(omop.lire(dossier / "note_nlp.parquet")) == 1


def test_lextraction_preserve_les_resultats_structures(tmp_path: Path) -> None:
    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "focus score à 2")],
        mesures=[_anti_ssa_positif(1)],
    )

    extraire_notes(dossier, extracteur=_bouchon)

    mesures = omop.lire(dossier / "measurement.parquet")
    assert len(mesures) == 2
    assert any(m["measurement_source_value"] == "anti-SSA" for m in mesures)


def test_sans_note_lextraction_ne_fait_rien(tmp_path: Path) -> None:
    dossier = tmp_path / "omop"
    omop.ecrire_table(dossier, "person", [_personne(1)])
    omop.ecrire_table(dossier, "measurement", [_anti_ssa_positif(1)])

    extraire_notes(dossier, extracteur=_bouchon)

    assert len(omop.lire(dossier / "measurement.parquet")) == 1


def test_un_fait_sous_le_seuil_rend_litem_negatif(tmp_path: Path) -> None:
    """Un focus score mesuré à 0,5 est un résultat : négatif, pas « non documenté »."""
    dossier = _jeu(tmp_path / "omop", notes=[_note(1, "focus score à 0,5")], mesures=[])

    extraire_notes(dossier, extracteur=_bouchon_sous_seuil)
    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.FOCUS_SCORE] is Statut.NEGATIF
    assert ligne.score_observe == 0


def _bouchon(note: dict[str, Any]) -> list[Fait]:
    return _focus_score_positif(int(note["note_id"]), int(note["person_id"]), note["note_date"])


def _bouchon_sous_seuil(note: dict[str, Any]) -> list[Fait]:
    faits = _bouchon(note)
    return [Fait(**{**vars(faits[0]), "valeur": 0.5, "extrait": "focus score à 0,5"})]


def _schirmer(person_id: int, concept_id: int, valeur: float, *, nlp: bool) -> dict[str, Any]:
    return {
        **_anti_ssa_positif(person_id),
        "measurement_id": concept_id % 1000 + person_id,
        "measurement_concept_id": concept_id,
        "value_as_number": valeur,
        "value_as_concept_id": None,
        "measurement_source_value": "Schirmer",
        "measurement_type_concept_id": VOCABULAIRE.items.concept("type_nlp" if nlp else "type_ehr"),
    }


def test_un_schirmer_code_par_oeil_est_reconnu(tmp_path: Path) -> None:
    """Un site qui latéralise ses Schirmer ne doit pas perdre l'Item en silence."""
    dossier = _jeu(
        tmp_path / "omop",
        notes=[],
        mesures=[_schirmer(1, VOCABULAIRE.items.concept("schirmer_droit"), 3.0, nlp=False)],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.SCHIRMER] is Statut.POSITIF
    assert ligne.origines[Item.SCHIRMER] is Origine.STRUCTUREE


def test_lorigine_suit_la_preuve_qui_decide(tmp_path: Path) -> None:
    """Un Schirmer positif saisi au dossier et un négatif extrait : l'origine est structurée."""
    dossier = _jeu(
        tmp_path / "omop",
        notes=[],
        mesures=[
            _schirmer(1, VOCABULAIRE.items.concept("schirmer"), 3.0, nlp=False),
            _schirmer(1, VOCABULAIRE.items.concept("schirmer_gauche"), 12.0, nlp=True),
        ],
    )

    (ligne,) = run_phenotype(dossier)

    assert ligne.statuts[Item.SCHIRMER] is Statut.POSITIF
    assert ligne.origines[Item.SCHIRMER] is Origine.STRUCTUREE


def test_lextracteur_par_defaut_ne_detruit_rien(tmp_path: Path) -> None:
    """Le no-op doit être un vrai no-op, y compris après une extraction précédente."""
    dossier = _jeu(tmp_path / "omop", notes=[_note(1, "focus score à 2")], mesures=[])
    extraire_notes(dossier, extracteur=_bouchon)

    extraire_notes(dossier)

    assert len(omop.lire(dossier / "measurement.parquet")) == 1
    assert len(omop.lire(dossier / "note_nlp.parquet")) == 1


def test_les_traces_dun_autre_systeme_sont_conservees(tmp_path: Path) -> None:
    """NOTE_NLP peut accueillir plusieurs extracteurs ; effacer le voisin serait une perte."""
    dossier = _jeu(tmp_path / "omop", notes=[_note(1, "focus score à 2")], mesures=[])
    extraire_notes(dossier, extracteur=_bouchon, systeme="voisin")

    extraire_notes(dossier, extracteur=_bouchon, systeme="bouchon")

    systemes = {ligne["nlp_system"] for ligne in omop.lire(dossier / "note_nlp.parquet")}
    assert systemes == {"voisin", "bouchon"}


def test_un_item_non_extractible_est_refuse() -> None:
    """L'Anti-SSA vient d'un résultat structuré : un extracteur ne doit pas le rapporter."""
    import pytest

    with pytest.raises(ValueError, match="anti_ssa"):
        Fait(1, 1, date(2020, 1, 1), Item.ANTI_SSA, 1.0, "anti-SSA positif", 0, 5)


def test_lorigine_survit_a_lecriture_et_la_relecture(tmp_path: Path) -> None:
    from sjs_phenotype import phenotype

    dossier = _jeu(
        tmp_path / "omop",
        notes=[_note(1, "focus score à 2")],
        mesures=[_anti_ssa_positif(1)],
    )
    extraire_notes(dossier, extracteur=_bouchon)
    table = run_phenotype(dossier)

    chemin = phenotype.ecrire(table, tmp_path / "resultats")

    assert phenotype.lire(chemin) == table
