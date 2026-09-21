"""Comptes rendus en texte libre : de quoi nourrir l'extracteur, plus tard.

À ce jalon la Définition computable les ignore. Les Items qui en dépendent restent
« non documenté », et personne n'atteint Défini : c'est le comportement attendu, et il
se teste, pour qu'un manque d'extraction ne se confonde pas avec un défaut de calcul.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.generator import Observation, Profil, Scenario, generer
from sjs_phenotype.modele import Item, Niveau, Statut
from sjs_phenotype.phenotype import run_phenotype

VOCABULAIRE = Vocabulaire.par_defaut()


def _scenario(**surcharges: Any) -> Scenario:
    return Scenario(**{"n_patients": 300, "graine": 21, **surcharges})


def _notes(chemins_omop: Path) -> list[dict[str, Any]]:
    return omop.lire(chemins_omop / "note.parquet")


def _textes(chemins_omop: Path, classe: str) -> list[str]:
    concept = VOCABULAIRE.notes.concept(classe)
    return [
        str(ligne["note_text"])
        for ligne in _notes(chemins_omop)
        if ligne["note_class_concept_id"] == concept
    ]


def test_la_table_note_porte_les_deux_familles_de_comptes_rendus(tmp_path: Path) -> None:
    chemins = generer(_scenario(), tmp_path)

    assert _textes(chemins.omop, "anatomopathologie")
    assert _textes(chemins.omop, "courrier")


def test_les_comptes_rendus_danatomopathologie_varient(tmp_path: Path) -> None:
    """Un extracteur entraîné sur une seule tournure ne prouverait rien."""
    chemins = generer(_scenario(n_patients=600), tmp_path)

    textes = _textes(chemins.omop, "anatomopathologie")

    assert len({texte.split(".")[0] for texte in textes}) >= 4


def test_les_negations_sont_presentes(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=600), tmp_path)

    textes = " ".join(_textes(chemins.omop, "anatomopathologie")).lower()

    assert "absence de sialadénite" in textes
    assert "non calculable" in textes


def test_les_valeurs_en_intervalle_sont_presentes(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=600), tmp_path)

    textes = " ".join(_textes(chemins.omop, "anatomopathologie"))

    assert re.search(r"focus score (?:entre|de) \d[,.]?\d? (?:et|à) \d", textes)


def test_un_grade_de_chisholm_peut_etre_donne_seul(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=600), tmp_path)

    seuls = [
        texte
        for texte in _textes(chemins.omop, "anatomopathologie")
        if "Chisholm" in texte and "focus score" not in texte.lower()
    ]

    assert seuls


def test_les_sialadenites_non_focales_sont_presentes(tmp_path: Path) -> None:
    """Sclérosante ou granulomateuse : l'Item sera négatif, pas positif."""
    chemins = generer(_scenario(n_patients=600), tmp_path)

    textes = " ".join(_textes(chemins.omop, "anatomopathologie")).lower()

    assert "sclérosante" in textes
    assert "granulomateuse" in textes


def test_le_grade_de_chisholm_saccorde_au_focus_score(tmp_path: Path) -> None:
    """Grade ≥3 vaut focus score ≥1 : l'État réel doit être cohérent avec lui-même."""
    chemins = generer(_scenario(n_patients=600), tmp_path)

    for ligne in omop.lire(chemins.etat_reel):
        focus, grade = ligne["focus_score"], ligne["grade_chisholm"]
        if focus is None or grade is None:
            continue
        assert (float(focus) >= 1.0) == (int(grade) >= 3)


def test_une_sialadenite_non_focale_ne_porte_aucun_focus_score(tmp_path: Path) -> None:
    """« Focus score non calculable » doit correspondre à une absence dans l'État réel."""
    chemins = generer(_scenario(n_patients=600), tmp_path)

    lignes = [l for l in omop.lire(chemins.etat_reel) if l["sialadenite"] is not None]
    non_focales = [l for l in lignes if l["sialadenite"] in ("sclérosante", "granulomateuse")]

    assert non_focales
    assert all(l["focus_score"] is None and l["grade_chisholm"] is None for l in non_focales)
    assert all(
        l["focus_score"] is not None for l in lignes if l["sialadenite"] in ("focale", "absente")
    )


def test_un_compte_rendu_ne_dit_jamais_autre_chose_que_letat_reel(tmp_path: Path) -> None:
    """Un extracteur sera noté contre l'État réel : le texte doit dire le vrai score."""
    chemins = generer(_scenario(n_patients=600), tmp_path)

    etat_reel = {int(l["person_id"]): l for l in omop.lire(chemins.etat_reel)}
    for note in _notes(chemins.omop):
        if note["note_class_concept_id"] != VOCABULAIRE.notes.concept("anatomopathologie"):
            continue
        reel = etat_reel[int(note["person_id"])]
        texte = str(note["note_text"])
        if "non calculable" in texte and "sclérosante" not in texte.lower():
            pass
        if re.search(r"[Ff]ocus score à 0\.", texte) or "Focus score à 0." in texte:
            assert reel["focus_score"] == 0.0, texte
        chiffre = re.search(r"focus score (?:à|:|évalué à) (\d+(?:,\d+)?)", texte, re.I)
        if chiffre:
            attendu = float(chiffre.group(1).replace(",", "."))
            assert reel["focus_score"] == attendu, texte


def test_une_biopsie_peut_etre_codee_sans_compte_rendu(tmp_path: Path) -> None:
    """C'est ce qui distinguera « biopsie non faite » de « compte rendu introuvable »."""
    chemins = generer(_scenario(n_patients=400, part_compte_rendu_manquant=0.5), tmp_path)

    actes = omop.lire(chemins.omop / "procedure_occurrence.parquet")
    biopsies = {int(ligne["person_id"]) for ligne in actes}
    redigees = {
        int(ligne["person_id"])
        for ligne in _notes(chemins.omop)
        if ligne["note_class_concept_id"] == VOCABULAIRE.notes.concept("anatomopathologie")
    }

    assert biopsies
    assert biopsies - redigees, "une biopsie codée sans compte rendu doit exister"


def test_sans_compte_rendu_manquant_toute_biopsie_est_redigee(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=400, part_compte_rendu_manquant=0.0), tmp_path)

    actes = omop.lire(chemins.omop / "procedure_occurrence.parquet")
    biopsies = {int(ligne["person_id"]) for ligne in actes}
    anatomopathologie = {
        int(ligne["person_id"])
        for ligne in _notes(chemins.omop)
        if ligne["note_class_concept_id"] == VOCABULAIRE.notes.concept("anatomopathologie")
    }

    assert biopsies == anatomopathologie


def test_seuls_les_patients_biopsies_ont_un_compte_rendu(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=400), tmp_path)

    etat_reel = {int(l["person_id"]): bool(l["biopsie"]) for l in omop.lire(chemins.etat_reel)}
    redigees = {
        int(ligne["person_id"])
        for ligne in _notes(chemins.omop)
        if ligne["note_class_concept_id"] == VOCABULAIRE.notes.concept("anatomopathologie")
    }

    assert all(etat_reel[person_id] for person_id in redigees)


def test_les_notes_ne_changent_aucun_niveau(tmp_path: Path) -> None:
    """Le comportement attendu à ce jalon : le texte n'est pas encore lu."""
    chemins = generer(_scenario(n_patients=400), tmp_path)

    table = run_phenotype(chemins.omop)

    assert _notes(chemins.omop), "le jeu doit contenir des comptes rendus"
    assert all(ligne.niveau is not Niveau.DEFINI for ligne in table)
    for item in (Item.FOCUS_SCORE, Item.OSS, Item.SCHIRMER, Item.DEBIT_SALIVAIRE):
        assert all(ligne.statuts[item] is Statut.NON_DOCUMENTE for ligne in table)


def test_les_courriers_portent_les_trois_tests_de_secheresse(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=600), tmp_path)

    textes = " ".join(_textes(chemins.omop, "courrier")).lower()

    assert "schirmer" in textes
    assert "oss" in textes or "coloration oculaire" in textes
    assert "débit salivaire" in textes


def test_un_meme_scenario_donne_les_memes_textes(tmp_path: Path) -> None:
    premier = generer(_scenario(n_patients=200), tmp_path / "a")
    second = generer(_scenario(n_patients=200), tmp_path / "b")

    assert _notes(premier.omop) == _notes(second.omop)


def test_les_profils_sans_biopsie_nont_pas_danatomopathologie(tmp_path: Path) -> None:
    scenario = _scenario(
        n_patients=200,
        parts={Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: 1.0},
        observation=Observation(proba_dosage_si_sjd=1.0),
    )
    chemins = generer(scenario, tmp_path)

    assert not _textes(chemins.omop, "anatomopathologie")


def test_les_comptes_rendus_se_repartissent_entre_positifs_et_negatifs(tmp_path: Path) -> None:
    chemins = generer(_scenario(n_patients=600), tmp_path)

    etat_reel = {
        int(ligne["person_id"]): ligne["focus_score"] for ligne in omop.lire(chemins.etat_reel)
    }
    scores = Counter(
        "positif" if score is not None and float(score) >= 1.0 else "négatif"
        for person_id, score in etat_reel.items()
        if score is not None
    )

    assert scores["positif"]
    assert scores["négatif"]


def test_changer_la_part_de_comptes_rendus_manquants_ne_change_pas_letat_reel(
    tmp_path: Path,
) -> None:
    """Deux scénarios qui ne diffèrent que par le recueil doivent porter les mêmes patients."""
    avec = generer(_scenario(part_compte_rendu_manquant=0.15), tmp_path / "a")
    sans = generer(_scenario(part_compte_rendu_manquant=0.0), tmp_path / "b")

    assert omop.lire(avec.etat_reel) == omop.lire(sans.etat_reel)


def test_un_courrier_peut_manquer_chez_un_patient_sec(tmp_path: Path) -> None:
    """La seule présence d'un courrier ne doit pas trahir l'État réel."""
    scenario = _scenario(
        n_patients=400,
        observation=Observation(proba_courrier_si_secheresse=0.5),
    )
    chemins = generer(scenario, tmp_path)

    secs = {int(l["person_id"]) for l in omop.lire(chemins.etat_reel) if l["secheresse"]}
    courriers = {
        int(ligne["person_id"])
        for ligne in _notes(chemins.omop)
        if ligne["note_class_concept_id"] == VOCABULAIRE.notes.concept("courrier")
    }

    assert secs - courriers, "un patient sec peut ne pas avoir de courrier"


def test_un_temoin_peut_avoir_un_bilan_de_secheresse(tmp_path: Path) -> None:
    scenario = _scenario(
        n_patients=400,
        observation=Observation(proba_bilan_secheresse_si_temoin=0.5),
    )
    chemins = generer(scenario, tmp_path)

    secs = {int(l["person_id"]) for l in omop.lire(chemins.etat_reel) if l["secheresse"]}
    courriers = {
        int(ligne["person_id"])
        for ligne in _notes(chemins.omop)
        if ligne["note_class_concept_id"] == VOCABULAIRE.notes.concept("courrier")
    }

    assert courriers - secs, "un témoin peut avoir été exploré"
