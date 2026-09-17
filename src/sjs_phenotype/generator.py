"""Générateur de jeux OMOP synthétiques (ADR-0001).

Chaque patient reçoit un État réel — ce qu'il a vraiment — puis un Processus d'observation
décide de ce que l'hôpital en enregistre : examen prescrit ou non, résultat saisi ou non.
Les deux sont écrits séparément, et l'État réel reste hors du schéma OMOP : la Définition
computable ne doit jamais pouvoir le lire.

À ce jalon, deux profils seulement et une seule Source : les Auto-anticorps.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import JeuDeConcepts

PROFIL_SJD = "sjd_seropositive"
PROFIL_TEMOIN = "population_generale"


@dataclass(frozen=True)
class Scenario:
    """Les hypothèses d'un jeu synthétique : qui sont les patients, et ce qu'on observe d'eux."""

    n_patients: int = 200
    part_sjd: float = 0.3
    graine: int = 0
    proba_positif_si_sjd: float = 0.7
    proba_positif_si_temoin: float = 0.02
    proba_dosage_si_sjd: float = 0.9
    proba_dosage_si_temoin: float = 0.1
    debut: date = date(2010, 1, 1)
    fin: date = date(2024, 12, 31)


@dataclass(frozen=True)
class CheminsJeu:
    omop: Path
    etat_reel: Path


def generer(scenario: Scenario, sortie: Path) -> CheminsJeu:
    """Écrit un jeu OMOP en Parquet et, à côté, l'État réel qui l'a produit.

    Deux générateurs aléatoires distincts, tirés de la même graine : l'un pour l'État réel,
    l'autre pour le Processus d'observation. Sans cela, changer une probabilité de recueil
    déplacerait la suite des tirages et modifierait la maladie des patients suivants — les
    scénarios ne seraient plus comparables entre eux.
    """
    reel = random.Random(f"{scenario.graine}-état réel")
    observation = random.Random(f"{scenario.graine}-processus d'observation")
    concepts = JeuDeConcepts.par_defaut()

    personnes: list[dict[str, Any]] = []
    resultats: list[dict[str, Any]] = []
    etat_reel: list[dict[str, Any]] = []

    for person_id in range(1, scenario.n_patients + 1):
        sjd = reel.random() < scenario.part_sjd
        anti_ssa_reel = reel.random() < (
            scenario.proba_positif_si_sjd if sjd else scenario.proba_positif_si_temoin
        )
        genre = 8532 if reel.random() < 0.9 else 8507
        naissance = reel.randint(1940, 1995)

        # Tirés quoi qu'il arrive : un examen non prescrit ne doit pas décaler les suivants.
        dose = observation.random() < (
            scenario.proba_dosage_si_sjd if sjd else scenario.proba_dosage_si_temoin
        )
        jour = _jour(observation, scenario)

        personnes.append(
            {
                "person_id": person_id,
                "gender_concept_id": genre,
                "year_of_birth": naissance,
            }
        )
        etat_reel.append(
            {
                "person_id": person_id,
                "profil": PROFIL_SJD if sjd else PROFIL_TEMOIN,
                "sjd": sjd,
                "anti_ssa_reel": anti_ssa_reel,
            }
        )
        if dose:
            resultats.append(
                {
                    "measurement_id": person_id,
                    "person_id": person_id,
                    "measurement_concept_id": concepts.anti_ro60[0],
                    "measurement_date": jour,
                    "value_as_number": None,
                    "value_as_concept_id": (
                        concepts.valeur_positive if anti_ssa_reel else concepts.valeur_negative
                    ),
                    "range_high": None,
                    "measurement_source_value": "anti-SSA",
                }
            )

    dossier_omop = sortie / "omop"
    omop.ecrire_table(dossier_omop, "person", personnes)
    omop.ecrire_table(dossier_omop, "measurement", resultats)
    chemin_etat_reel = omop.ecrire_table(sortie, "etat_reel", etat_reel)
    return CheminsJeu(omop=dossier_omop, etat_reel=chemin_etat_reel)


def _jour(hasard: random.Random, scenario: Scenario) -> date:
    etendue = (scenario.fin - scenario.debut).days
    return scenario.debut + timedelta(days=hasard.randint(0, etendue))
