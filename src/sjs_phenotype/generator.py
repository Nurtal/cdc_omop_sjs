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
from sjs_phenotype.concepts import Vocabulaire


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
    proba_rendu_non_differencie: float = 0.3
    proba_traitement_si_sjd: float = 0.6
    proba_traitement_si_secheresse: float = 0.3
    venues_par_patient: int = 3


@dataclass(frozen=True)
class Scenario:
    """Les hypothèses d'un jeu synthétique, telles qu'un fichier TOML les décrit."""

    nom: str = "défaut"
    n_patients: int = 500
    graine: int = 0
    parts: Mapping[Profil | str, float] = field(default_factory=lambda: dict(PARTS_PAR_DEFAUT))
    part_ro52_isole_si_lupus: float = 0.4
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
        parts = contenu.pop("parts", None)
        scenario = cls(**contenu, observation=observation)
        return replace(scenario, parts=parts) if parts is not None else scenario

    def en_toml(self) -> str:
        lignes = [
            f"nom = {json.dumps(self.nom, ensure_ascii=False)}",
            f"n_patients = {self.n_patients}",
            f"graine = {self.graine}",
            f"part_ro52_isole_si_lupus = {self.part_ro52_isole_si_lupus}",
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
        "etat_reel": [],
    }
    compteur = _Compteur()

    for person_id, profil in enumerate(profils, start=1):
        # Tiré pour tout le monde, appliqué au seul lupus : le flux de l'État réel ne doit
        # pas dépendre de la composition des profils.
        ro52_isole = reel.random() < scenario.part_ro52_isole_si_lupus
        recette = RECETTES[profil]
        if profil is Profil.LUPUS_ANTI_SSA and ro52_isole:
            # Un anti-Ro52 isolé n'est pas un Anti-SSA : ce patient ne doit jamais compter.
            recette = replace(recette, anti_ssa_reel=False, anti_ro52_reel=True)
        tables["person"].append(
            {
                "person_id": person_id,
                "gender_concept_id": 8532 if reel.random() < 0.9 else 8507,
                "year_of_birth": reel.randint(1940, 1995),
            }
        )
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
            }
        )
        tirages = _tirer(scenario, observation, vocabulaire)
        venues = _venues(person_id, tirages, vocabulaire, compteur)
        tables["visit_occurrence"] += venues
        tables["measurement"] += _dosages(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )
        tables["condition_occurrence"] += _diagnostics(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )
        tables["drug_exposure"] += _traitements(
            person_id, recette, scenario, tirages, vocabulaire, compteur, venues
        )

    dossier_omop = sortie / "omop"
    for nom in (
        "person",
        "visit_occurrence",
        "measurement",
        "condition_occurrence",
        "drug_exposure",
    ):
        omop.ecrire_table(dossier_omop, nom, tables[nom])
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
    u_traitement_sjd: float
    u_traitement_secheresse: float
    code_connectivite: str
    code_lupus: str
    code_exclusion: str
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
        u_traitement_sjd=observation.random(),
        u_traitement_secheresse=observation.random(),
        code_connectivite=observation.choice(diagnostics.groupe("connectivites")),
        code_lupus=observation.choice(diagnostics.groupe("lupus_ou_myosite")),
        code_exclusion=observation.choice(diagnostics.groupe("criteres_exclusion")),
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
    elif recette.anti_ro52_reel and not recette.anti_ssa_reel:
        concept, positif = anti_ssa.anti_ro52[0], True
    else:
        concept, positif = anti_ssa.anti_ro60[0], recette.anti_ssa_reel

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
        codes.append("M35.0")
    if recette.connectivite:
        codes.append(tirages.code_lupus if not recette.sjd else tirages.code_connectivite)
    if recette.lymphome:
        codes.append("C88.4")
    if recette.exclusion:
        codes.append(tirages.code_exclusion)
    if recette.secheresse and not recette.sjd:
        codes.append("R68.2")

    lignes = []
    for rang, code in enumerate(codes, start=1):
        venue = _venue(tirages, venues, rang)
        lignes.append(
            {
                "condition_occurrence_id": compteur.suivant("condition_occurrence"),
                "person_id": person_id,
                "condition_concept_id": diagnostics.concept(code),
                "condition_start_date": venue["visit_start_date"],
                "condition_source_value": code,
                "visit_occurrence_id": venue["visit_occurrence_id"],
            }
        )
    return lignes


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
