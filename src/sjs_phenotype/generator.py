"""Générateur de jeux OMOP synthétiques (ADR-0001).

Chaque patient reçoit un État réel — ce qu'il a vraiment, et qui le range dans un Profil —
puis un Processus d'observation décide de ce que l'hôpital en enregistre : examen prescrit
ou non, résultat rendu sous telle ou telle forme, diagnostic codé ou non.

Les deux tirages sont indépendants : changer une probabilité de recueil ne doit pas modifier
la maladie des patients, sans quoi deux scénarios ne seraient plus comparables.

L'État réel est écrit hors du schéma OMOP. La Définition computable ne doit jamais le lire.
"""

from __future__ import annotations

import json
import random
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import CODE_SJD, Table, Vocabulaire
from sjs_phenotype.redaction import (
    SIALADENITE_ABSENTE,
    SIALADENITE_FOCALE,
    SIALADENITES_NON_FOCALES,
    Biopsie,
    compte_rendu_biopsie,
    courrier_secheresse,
    grade_pour,
)

CODE_VHC = "B18.2"


class Profil(StrEnum):
    """Ce qu'un patient synthétique est vraiment. Invisible pour la Définition computable."""

    SJD_SEROPOSITIVE_BIOPSIE = "sjd_seropositive_biopsie"
    SJD_SEROPOSITIVE_SANS_BIOPSIE = "sjd_seropositive_sans_biopsie"
    SJD_SERONEGATIVE = "sjd_seronegative"
    SJD_CONNECTIVITE_ASSOCIEE = "sjd_connectivite_associee"
    SJD_LYMPHOME = "sjd_lymphome"
    LUPUS_ANTI_SSA = "lupus_anti_ssa"
    SECHERESSE_AUTRE_CAUSE = "secheresse_autre_cause"
    PORTEUR_CRITERE_EXCLUSION = "porteur_critere_exclusion"
    M35_CODE_A_TORT = "m35_code_a_tort"
    POPULATION_GENERALE = "population_generale"


@dataclass(frozen=True)
class Recette:
    """L'État réel que porte un Profil."""

    sjd: bool = False
    anti_ssa_reel: bool = False
    anti_ro52_reel: bool = False
    biopsie: bool = False
    secheresse: bool = False
    connectivite: bool = False
    lymphome: bool = False
    exclusion: bool = False
    critere_exclusion: str = ""
    code_sjd_a_tort: bool = False


RECETTES: Mapping[Profil, Recette] = {
    Profil.SJD_SEROPOSITIVE_BIOPSIE: Recette(
        sjd=True, anti_ssa_reel=True, biopsie=True, secheresse=True
    ),
    Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: Recette(sjd=True, anti_ssa_reel=True, secheresse=True),
    Profil.SJD_SERONEGATIVE: Recette(sjd=True, biopsie=True, secheresse=True),
    Profil.SJD_CONNECTIVITE_ASSOCIEE: Recette(
        sjd=True, anti_ssa_reel=True, biopsie=True, secheresse=True, connectivite=True
    ),
    Profil.SJD_LYMPHOME: Recette(
        sjd=True, anti_ssa_reel=True, biopsie=True, secheresse=True, lymphome=True
    ),
    Profil.LUPUS_ANTI_SSA: Recette(anti_ssa_reel=True, connectivite=True),
    Profil.SECHERESSE_AUTRE_CAUSE: Recette(secheresse=True),
    Profil.PORTEUR_CRITERE_EXCLUSION: Recette(secheresse=True, exclusion=True),
    Profil.M35_CODE_A_TORT: Recette(secheresse=True, code_sjd_a_tort=True),
    Profil.POPULATION_GENERALE: Recette(),
}

PARTS_PAR_DEFAUT: Mapping[Profil | str, float] = {
    Profil.SJD_SEROPOSITIVE_BIOPSIE: 0.06,
    Profil.SJD_SEROPOSITIVE_SANS_BIOPSIE: 0.04,
    Profil.SJD_SERONEGATIVE: 0.04,
    Profil.SJD_CONNECTIVITE_ASSOCIEE: 0.02,
    Profil.SJD_LYMPHOME: 0.01,
    Profil.LUPUS_ANTI_SSA: 0.08,
    Profil.SECHERESSE_AUTRE_CAUSE: 0.15,
    Profil.PORTEUR_CRITERE_EXCLUSION: 0.05,
    Profil.M35_CODE_A_TORT: 0.05,
    Profil.POPULATION_GENERALE: 0.50,
}


@dataclass(frozen=True)
class Observation:
    """Le Processus d'observation : ce que l'hôpital enregistre de ce qui est vrai."""

    proba_dosage_si_sjd: float = 0.9
    proba_dosage_si_temoin: float = 0.15
    proba_codage_si_sjd: float = 0.5
    proba_recodage_a_chaque_venue: float = 0.5
    proba_rendu_non_differencie: float = 0.3
    proba_traitement_si_sjd: float = 0.6
    proba_traitement_si_secheresse: float = 0.3
    proba_courrier_si_secheresse: float = 0.8
    proba_bilan_secheresse_si_temoin: float = 0.1
    venues_par_patient: int = 3


@dataclass(frozen=True)
class Scenario:
    """Les hypothèses d'un jeu synthétique, telles qu'un fichier TOML les décrit."""

    nom: str = "défaut"
    n_patients: int = 500
    graine: int = 0
    parts: Mapping[Profil | str, float] = field(default_factory=lambda: dict(PARTS_PAR_DEFAUT))
    part_ro52_isole_si_lupus: float = 0.4
    part_vhc_actif_si_exclusion: float = 0.7
    part_compte_rendu_manquant: float = 0.15
    absences: omop.Absences = omop.Absences.NULL
    observation: Observation = field(default_factory=Observation)
    debut: date = date(2010, 1, 1)
    fin: date = date(2024, 12, 31)

    def __post_init__(self) -> None:
        inconnus = [str(profil) for profil in self.parts if profil not in set(Profil)]
        if inconnus:
            raise ValueError(f"profil inconnu dans les parts : {sorted(inconnus)}")
        if not self.parts or sum(self.parts.values()) <= 0:
            raise ValueError("les parts doivent nommer au moins un profil, de part non nulle")
        if self.observation.venues_par_patient < 1:
            raise ValueError("venues_par_patient doit valoir au moins 1")
        object.__setattr__(self, "parts", {Profil(cle): part for cle, part in self.parts.items()})

    @classmethod
    def charger(cls, chemin: Path) -> Scenario:
        contenu: dict[str, Any] = tomllib.loads(chemin.read_text(encoding="utf-8"))
        observation = Observation(**contenu.pop("observation", {}))
        if "absences" in contenu:
            contenu["absences"] = omop.Absences(contenu["absences"])
        parts = contenu.pop("parts", None)
        scenario = cls(**contenu, observation=observation)
        return replace(scenario, parts=parts) if parts is not None else scenario

    def en_toml(self) -> str:
        lignes = [
            f"nom = {json.dumps(self.nom, ensure_ascii=False)}",
            f"n_patients = {self.n_patients}",
            f"graine = {self.graine}",
            f"part_ro52_isole_si_lupus = {self.part_ro52_isole_si_lupus}",
            f"part_vhc_actif_si_exclusion = {self.part_vhc_actif_si_exclusion}",
            f"part_compte_rendu_manquant = {self.part_compte_rendu_manquant}",
            f'absences = "{self.absences.value}"',
            f"debut = {self.debut.isoformat()}",
            f"fin = {self.fin.isoformat()}",
            "",
            "[parts]",
            *(f"{Profil(profil).value} = {part}" for profil, part in self.parts.items()),
            "",
            "[observation]",
            *(f"{nom} = {valeur}" for nom, valeur in vars(self.observation).items()),
        ]
        return "\n".join(lignes) + "\n"


@dataclass(frozen=True)
class CheminsJeu:
    omop: Path
    etat_reel: Path
    scenario: Path


def generer(scenario: Scenario, sortie: Path) -> CheminsJeu:
    """Écrit un jeu OMOP en Parquet, l'État réel qui l'a produit, et le scénario suivi."""
    reel = random.Random(f"{scenario.graine}-état réel")
    observation = random.Random(f"{scenario.graine}-processus d'observation")
    vocabulaire = Vocabulaire.par_defaut()

    profils = _repartir(scenario, reel)
    tables: dict[str, list[dict[str, Any]]] = {
        "person": [],
        "visit_occurrence": [],
        "measurement": [],
        "condition_occurrence": [],
        "drug_exposure": [],
        "note": [],
        "procedure_occurrence": [],
        "etat_reel": [],
    }
    compteur = _Compteur()

    for person_id, profil in enumerate(profils, start=1):
        # Tiré pour tout le monde, appliqué au seul lupus : le flux de l'État réel ne doit
        # pas dépendre de la composition des profils.
        ro52_isole = reel.random() < scenario.part_ro52_isole_si_lupus
        maladie_excluante = reel.choice(vocabulaire.diagnostics.groupe("criteres_exclusion"))
        vhc_actif = reel.random() < scenario.part_vhc_actif_si_exclusion
        # Tirés pour tout le monde, appliqués aux seuls patients concernés : le flux de
        # l'État réel ne doit pas dépendre de la composition des profils.
        faits = _faits_cliniques(reel)
        recette = RECETTES[profil]
        if profil is Profil.LUPUS_ANTI_SSA and ro52_isole:
            # Un anti-Ro52 isolé n'est pas un Anti-SSA : ce patient ne doit jamais compter.
            recette = replace(recette, anti_ssa_reel=False, anti_ro52_reel=True)
        if recette.exclusion:
            # Une hépatite C chronique mais inactive n'exclut pas : le critère vise
            # l'hépatite active, et l'État réel doit dire la même chose que la règle.
            exclut = maladie_excluante != CODE_VHC or vhc_actif
            recette = replace(recette, critere_exclusion=maladie_excluante, exclusion=exclut)
        tables["person"].append(
            {
                "person_id": person_id,
                "gender_concept_id": 8532 if reel.random() < 0.9 else 8507,
                "year_of_birth": reel.randint(1940, 1995),
            }
        )
        tirages = _tirer(scenario, observation, vocabulaire)
        redaction = random.Random(tirages.graine_redaction)
        compte_rendu_manquant = (
            tirages.u_compte_rendu_manquant < scenario.part_compte_rendu_manquant
        )
        biopsie = faits.biopsie if recette.biopsie else None
        secheresse = faits.secheresse if recette.secheresse else None
        tables["etat_reel"].append(
            {
                "person_id": person_id,
                "profil": profil.value,
                "sjd": recette.sjd,
                "anti_ssa_reel": recette.anti_ssa_reel,
                "anti_ro52_reel": recette.anti_ro52_reel,
                "biopsie": recette.biopsie,
                "secheresse": recette.secheresse,
                "connectivite": recette.connectivite,
                "lymphome": recette.lymphome,
                "exclusion": recette.exclusion,
                "critere_exclusion": recette.critere_exclusion,
                "vhc_actif": vhc_actif if recette.critere_exclusion == CODE_VHC else None,
                "focus_score": biopsie.focus_score if biopsie else None,
                "grade_chisholm": biopsie.grade_chisholm if biopsie else None,
                "sialadenite": biopsie.sialadenite if biopsie else None,
                "schirmer": secheresse[0] if secheresse else None,
                "oss": secheresse[1] if secheresse else None,
                "debit_salivaire": secheresse[2] if secheresse else None,
            }
        )
        venues = _venues(person_id, tirages, vocabulaire, compteur)
        tables["visit_occurrence"] += venues
        tables["measurement"] += _dosages(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )
        tables["measurement"] += _biologie(
            person_id, recette, vhc_actif, tirages, vocabulaire, compteur, venues
        )
        tables["condition_occurrence"] += _diagnostics(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )
        tables["drug_exposure"] += _traitements(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )
        if biopsie is not None:
            tables["procedure_occurrence"] += _acte_biopsie(
                person_id, tirages, vocabulaire, compteur, venues
            )
            if not compte_rendu_manquant:
                tables["note"].append(
                    _note(
                        person_id,
                        "anatomopathologie",
                        "Compte rendu d'anatomopathologie",
                        compte_rendu_biopsie(biopsie, redaction),
                        tirages,
                        vocabulaire,
                        compteur,
                        venues,
                        rang=2,
                    )
                )
        # Un bilan de sécheresse n'est ni systématique chez le malade, ni impossible chez
        # le témoin : sans cela, la seule présence du courrier trahirait l'État réel.
        courrier_redige = (
            tirages.u_courrier_manquant < scenario.observation.proba_courrier_si_secheresse
            if recette.secheresse
            else tirages.u_bilan_secheresse_temoin
            < scenario.observation.proba_bilan_secheresse_si_temoin
        )
        if courrier_redige:
            secheresse = faits.secheresse
            tables["note"].append(
                _note(
                    person_id,
                    "courrier",
                    "Courrier de consultation",
                    courrier_secheresse(*secheresse, redaction),
                    tirages,
                    vocabulaire,
                    compteur,
                    venues,
                    rang=3,
                )
            )

    dossier_omop = sortie / "omop"
    for nom in (
        "person",
        "visit_occurrence",
        "measurement",
        "condition_occurrence",
        "drug_exposure",
        "note",
        "procedure_occurrence",
    ):
        omop.ecrire_table(dossier_omop, nom, tables[nom], absences=scenario.absences)
    chemin_etat_reel = omop.ecrire_table(sortie, "etat_reel", tables["etat_reel"])
    chemin_scenario = sortie / "scenario.toml"
    chemin_scenario.write_text(scenario.en_toml(), encoding="utf-8")
    return CheminsJeu(omop=dossier_omop, etat_reel=chemin_etat_reel, scenario=chemin_scenario)


class _Compteur:
    """Des identifiants stables d'une table à l'autre."""

    def __init__(self) -> None:
        self._suivants: dict[str, int] = {}

    def suivant(self, table: str) -> int:
        valeur = self._suivants.get(table, 0) + 1
        self._suivants[table] = valeur
        return valeur


@dataclass(frozen=True)
class Tirages:
    """Tous les tirages du Processus d'observation pour un patient, faits d'avance.

    Le nombre de tirages consommés par patient ne dépend d'aucune probabilité : sans cela,
    changer un réglage décalerait le flux aléatoire et deux scénarios ne différeraient plus
    seulement par ce réglage.
    """

    jours: tuple[date, ...]
    nombre_venues: int
    indices_venues: tuple[int, ...]
    u_dosage: float
    u_rendu_non_differencie: float
    u_codage_sjd: float
    u_recodages: tuple[float, ...]
    u_compte_rendu_manquant: float
    u_courrier_manquant: float
    u_bilan_secheresse_temoin: float
    graine_redaction: int
    u_traitement_sjd: float
    u_traitement_secheresse: float
    code_connectivite: str
    code_lupus: str
    code_evocateur: str
    code_assechant: str


_VENUES_A_TIRER = 8


def _tirer(scenario: Scenario, observation: random.Random, vocabulaire: Vocabulaire) -> Tirages:
    maximum = scenario.observation.venues_par_patient
    diagnostics, medicaments = vocabulaire.diagnostics, vocabulaire.medicaments
    return Tirages(
        jours=tuple(_jour(observation, scenario) for _ in range(maximum)),
        nombre_venues=observation.randint(1, maximum),
        indices_venues=tuple(observation.randrange(maximum) for _ in range(_VENUES_A_TIRER)),
        u_dosage=observation.random(),
        u_rendu_non_differencie=observation.random(),
        u_codage_sjd=observation.random(),
        u_recodages=tuple(observation.random() for _ in range(maximum)),
        u_compte_rendu_manquant=observation.random(),
        u_courrier_manquant=observation.random(),
        u_bilan_secheresse_temoin=observation.random(),
        graine_redaction=observation.randrange(2**32),
        u_traitement_sjd=observation.random(),
        u_traitement_secheresse=observation.random(),
        code_connectivite=observation.choice(diagnostics.groupe("connectivites")),
        code_lupus=observation.choice(diagnostics.groupe("lupus_ou_myosite")),
        code_evocateur=observation.choice(medicaments.groupe("evocateurs_sjd")),
        code_assechant=observation.choice(medicaments.groupe("assechants")),
    )


def _repartir(scenario: Scenario, reel: random.Random) -> list[Profil]:
    """Répartit les patients selon les parts demandées, puis brasse l'ordre.

    Les restes vont aux profils dont la part fractionnaire est la plus grande, pour qu'un
    profil rare écrit en dernier dans le fichier ne soit pas rogné par un arrondi.
    """
    total = sum(scenario.parts.values())
    quotas = {
        Profil(cle): scenario.n_patients * part / total for cle, part in scenario.parts.items()
    }
    effectifs = {profil: int(quota) for profil, quota in quotas.items()}
    ordre = sorted(quotas, key=lambda profil: (-(quotas[profil] % 1), profil.value))
    for rang in range(scenario.n_patients - sum(effectifs.values())):
        effectifs[ordre[rang % len(ordre)]] += 1

    profils = [profil for profil, nombre in effectifs.items() for _ in range(nombre)]
    reel.shuffle(profils)
    return profils


def _jour(hasard: random.Random, scenario: Scenario) -> date:
    etendue = (scenario.fin - scenario.debut).days
    return scenario.debut + timedelta(days=hasard.randint(0, etendue))


def _venues(
    person_id: int, tirages: Tirages, vocabulaire: Vocabulaire, compteur: _Compteur
) -> list[dict[str, Any]]:
    return [
        {
            "visit_occurrence_id": compteur.suivant("visit_occurrence"),
            "person_id": person_id,
            "visit_concept_id": vocabulaire.visites.concept("externe"),
            "visit_start_date": jour,
            "visit_end_date": jour,
        }
        for jour in tirages.jours[: tirages.nombre_venues]
    ]


def _venue(tirages: Tirages, venues: Sequence[Mapping[str, Any]], rang: int) -> Mapping[str, Any]:
    return venues[tirages.indices_venues[rang] % len(venues)]


def _dosages(
    person_id: int,
    recette: Recette,
    scenario: Scenario,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Le dosage a-t-il été prescrit, et sous quelle forme le laboratoire l'a-t-il rendu ?"""
    prescrit = tirages.u_dosage < (
        scenario.observation.proba_dosage_si_sjd
        if recette.sjd
        else scenario.observation.proba_dosage_si_temoin
    )
    if not prescrit:
        return []

    anti_ssa = vocabulaire.anti_ssa
    if tirages.u_rendu_non_differencie < scenario.observation.proba_rendu_non_differencie:
        # Un dosage global ne sépare pas Ro52 de Ro60 : un Ro52 isolé ressort « anti-SSA
        # positif ». C'est le faux positif que la Définition computable doit affronter.
        concept = anti_ssa.anti_ssa_non_differencie[0]
        positif = recette.anti_ssa_reel or recette.anti_ro52_reel
        rendus = [(concept, positif)]
    else:
        # Un panel qui différencie rend les deux analytes, quel que soit le patient.
        rendus = [
            (anti_ssa.anti_ro60[0], recette.anti_ssa_reel),
            (anti_ssa.anti_ro52[0], recette.anti_ro52_reel),
        ]

    venue = _venue(tirages, venues, 0)
    return [
        {
            "measurement_id": compteur.suivant("measurement"),
            "person_id": person_id,
            "measurement_concept_id": concept,
            "measurement_date": venue["visit_start_date"],
            "value_as_number": None,
            "value_as_concept_id": (
                anti_ssa.valeur_positive if positif else anti_ssa.valeur_negative
            ),
            "range_high": None,
            "measurement_source_value": "anti-SSA",
            "visit_occurrence_id": venue["visit_occurrence_id"],
        }
        for concept, positif in rendus
    ]


def _biologie(
    person_id: int,
    recette: Recette,
    vhc_actif: bool,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Une hépatite C codée s'accompagne d'une PCR : c'est elle qui dit si elle est active."""
    if recette.critere_exclusion != CODE_VHC:
        return []

    venue = _venue(tirages, venues, 4)
    return [
        {
            "measurement_id": compteur.suivant("measurement"),
            "person_id": person_id,
            "measurement_concept_id": vocabulaire.biologie.concept("pcr_vhc"),
            "measurement_date": venue["visit_start_date"],
            "value_as_number": None,
            "value_as_concept_id": (
                vocabulaire.valeur_positive if vhc_actif else vocabulaire.valeur_negative
            ),
            "range_high": None,
            "measurement_source_value": "PCR VHC",
            "visit_occurrence_id": venue["visit_occurrence_id"],
        }
    ]


def _diagnostics(
    person_id: int,
    recette: Recette,
    scenario: Scenario,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    diagnostics = vocabulaire.diagnostics
    codes: list[str] = []
    code_sjd_pose = recette.sjd and (
        tirages.u_codage_sjd < scenario.observation.proba_codage_si_sjd
    )
    if code_sjd_pose or recette.code_sjd_a_tort:
        codes.append(CODE_SJD)
    if recette.connectivite:
        codes.append(tirages.code_lupus if not recette.sjd else tirages.code_connectivite)
    if recette.lymphome:
        codes.append("C88.4")
    if recette.critere_exclusion:
        codes.append(recette.critere_exclusion)
    if recette.secheresse and not recette.sjd:
        codes.append("R68.2")

    lignes = []
    for rang, code in enumerate(codes, start=1):
        venue = _venue(tirages, venues, rang)
        lignes.append(_diagnostic(person_id, code, diagnostics, venue, compteur))
        if code != CODE_SJD:
            continue
        # Un patient suivi est recodé à ses venues *suivantes* : sans cela, la variante de
        # Robustesse du Comparateur CIM-10 (deux occurrences) ne retiendrait personne. Le
        # recodage part de la venue qui porte déjà le code, sinon il la redouble sans
        # ajouter la moindre date distincte.
        depart = venues.index(venue) + 1
        for venue_suivante, u_recodage in zip(venues[depart:], tirages.u_recodages, strict=False):
            if u_recodage < scenario.observation.proba_recodage_a_chaque_venue:
                lignes.append(_diagnostic(person_id, code, diagnostics, venue_suivante, compteur))
    return lignes


def _diagnostic(
    person_id: int,
    code: str,
    diagnostics: Table,
    venue: Mapping[str, Any],
    compteur: _Compteur,
) -> dict[str, Any]:
    return {
        "condition_occurrence_id": compteur.suivant("condition_occurrence"),
        "person_id": person_id,
        "condition_concept_id": diagnostics.concept(code),
        "condition_start_date": venue["visit_start_date"],
        "condition_source_value": code,
        "visit_occurrence_id": venue["visit_occurrence_id"],
    }


def _traitements(
    person_id: int,
    recette: Recette,
    scenario: Scenario,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    medicaments = vocabulaire.medicaments
    codes: list[str] = []
    if recette.sjd and tirages.u_traitement_sjd < scenario.observation.proba_traitement_si_sjd:
        codes.append(tirages.code_evocateur)
    if recette.lymphome:
        codes.append("rituximab")
    if (
        recette.secheresse
        and not recette.sjd
        and tirages.u_traitement_secheresse < scenario.observation.proba_traitement_si_secheresse
    ):
        codes.append(tirages.code_assechant)

    lignes = []
    for rang, code in enumerate(codes, start=6):
        venue = _venue(tirages, venues, rang % _VENUES_A_TIRER)
        debut = venue["visit_start_date"]
        lignes.append(
            {
                "drug_exposure_id": compteur.suivant("drug_exposure"),
                "person_id": person_id,
                "drug_concept_id": medicaments.concept(code),
                "drug_exposure_start_date": debut,
                "drug_exposure_end_date": debut + timedelta(days=90),
                "drug_source_value": code,
                "visit_occurrence_id": venue["visit_occurrence_id"],
            }
        )
    return lignes


@dataclass(frozen=True)
class FaitsCliniques:
    """Ce qu'une biopsie et un bilan de sécheresse montreraient, s'ils étaient faits."""

    biopsie: Biopsie
    secheresse: tuple[int, int, float]


def _faits_cliniques(reel: random.Random) -> FaitsCliniques:
    """Tirés pour tout patient, appliqués aux seuls profils concernés.

    La nature de la sialadénite commande le focus score : une sialadénite sclérosante ou
    granulomateuse ne permet aucun décompte de foyers, une glande normale en donne un à
    zéro. Le grade de Chisholm-Mason découle ensuite du score. Sans cette cohérence, un
    extracteur lisant correctement le compte rendu serait compté en erreur.
    """
    tirage = reel.random()
    if tirage < 0.10:
        sialadenite = reel.choice(SIALADENITES_NON_FOCALES)
        focus_score: float | None = None
    elif tirage < 0.35:
        sialadenite = SIALADENITE_ABSENTE
        focus_score = 0.0
    elif tirage < 0.50:
        sialadenite = SIALADENITE_FOCALE
        focus_score = reel.choice([0.3, 0.5, 0.8])
    else:
        sialadenite = SIALADENITE_FOCALE
        focus_score = round(reel.uniform(1.0, 4.0), 1)

    return FaitsCliniques(
        biopsie=Biopsie(
            focus_score=focus_score,
            grade_chisholm=grade_pour(focus_score),
            sialadenite=sialadenite,
        ),
        secheresse=(
            reel.randint(0, 15),
            reel.randint(0, 10),
            round(reel.uniform(0.0, 0.4), 2),
        ),
    )


def _acte_biopsie(
    person_id: int,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """L'acte dit qu'une biopsie a eu lieu, même quand son compte rendu manque."""
    venue = _venue(tirages, venues, 2)
    return [
        {
            "procedure_occurrence_id": compteur.suivant("procedure_occurrence"),
            "person_id": person_id,
            "procedure_concept_id": vocabulaire.notes.concept("biopsie_glande_salivaire"),
            "procedure_date": venue["visit_start_date"],
            "procedure_source_value": "HAHB001",
            "visit_occurrence_id": venue["visit_occurrence_id"],
        }
    ]


def _note(
    person_id: int,
    classe: str,
    titre: str,
    texte: str,
    tirages: Tirages,
    vocabulaire: Vocabulaire,
    compteur: _Compteur,
    venues: Sequence[Mapping[str, Any]],
    rang: int,
) -> dict[str, Any]:
    venue = _venue(tirages, venues, rang)
    return {
        "note_id": compteur.suivant("note"),
        "person_id": person_id,
        "note_date": venue["visit_start_date"],
        "note_class_concept_id": vocabulaire.notes.concept(classe),
        "note_title": titre,
        "note_text": texte,
        "visit_occurrence_id": venue["visit_occurrence_id"],
    }
