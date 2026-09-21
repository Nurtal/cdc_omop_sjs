"""Lecture et écriture des tables OMOP en Parquet, via DuckDB (ADR-0002).

Les colonnes gardent leur nom OMOP. Une valeur absente est écrite NULL : rien, jamais,
ne doit transformer une absence en résultat (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import duckdb


class Absences(StrEnum):
    """Comment une source encode une valeur absente.

    L'EDS interroge ses Parquet avec ClickHouse, dont les colonnes n'acceptent pas NULL :
    l'absence y devient 0, chaîne vide ou 1970-01-01. Le pipeline doit savoir laquelle des
    deux conventions il lit, sans quoi une absence passerait pour un résultat (ADR-0005).
    """

    NULL = "null"
    DEFAUTS = "defauts"


SENTINELLES: Mapping[str, Any] = {
    "BIGINT": 0,
    "INTEGER": 0,
    "DOUBLE": 0.0,
    "VARCHAR": "",
    "DATE": date(1970, 1, 1),
    "BOOLEAN": False,
}

SCHEMAS: Mapping[str, Mapping[str, str]] = {
    "person": {
        "person_id": "BIGINT",
        "gender_concept_id": "BIGINT",
        "year_of_birth": "INTEGER",
    },
    "measurement": {
        "measurement_id": "BIGINT",
        "person_id": "BIGINT",
        "measurement_concept_id": "BIGINT",
        "measurement_date": "DATE",
        "value_as_number": "DOUBLE",
        "value_as_concept_id": "BIGINT",
        "range_high": "DOUBLE",
        "measurement_source_value": "VARCHAR",
        "visit_occurrence_id": "BIGINT",
    },
    "visit_occurrence": {
        "visit_occurrence_id": "BIGINT",
        "person_id": "BIGINT",
        "visit_concept_id": "BIGINT",
        "visit_start_date": "DATE",
        "visit_end_date": "DATE",
    },
    "condition_occurrence": {
        "condition_occurrence_id": "BIGINT",
        "person_id": "BIGINT",
        "condition_concept_id": "BIGINT",
        "condition_start_date": "DATE",
        "condition_source_value": "VARCHAR",
        "visit_occurrence_id": "BIGINT",
    },
    "drug_exposure": {
        "drug_exposure_id": "BIGINT",
        "person_id": "BIGINT",
        "drug_concept_id": "BIGINT",
        "drug_exposure_start_date": "DATE",
        "drug_exposure_end_date": "DATE",
        "drug_source_value": "VARCHAR",
        "visit_occurrence_id": "BIGINT",
    },
    "etat_reel": {
        "person_id": "BIGINT",
        "profil": "VARCHAR",
        "sjd": "BOOLEAN",
        "anti_ssa_reel": "BOOLEAN",
        "anti_ro52_reel": "BOOLEAN",
        "biopsie": "BOOLEAN",
        "secheresse": "BOOLEAN",
        "connectivite": "BOOLEAN",
        "lymphome": "BOOLEAN",
        "exclusion": "BOOLEAN",
        "critere_exclusion": "VARCHAR",
        "vhc_actif": "BOOLEAN",
    },
    "phenotype": {
        "person_id": "BIGINT",
        "statut_focus_score": "VARCHAR",
        "statut_anti_ssa": "VARCHAR",
        "statut_oss": "VARCHAR",
        "statut_schirmer": "VARCHAR",
        "statut_debit_salivaire": "VARCHAR",
        "score_observe": "INTEGER",
        "score_atteignable": "INTEGER",
        "niveau": "VARCHAR",
        "date_probable": "DATE",
        "date_defini": "DATE",
        "exclu": "BOOLEAN",
        "criteres_exclusion": "VARCHAR",
    },
}


def connexion() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:")


def ecrire_table(
    dossier: Path,
    nom: str,
    lignes: Sequence[Mapping[str, Any]],
    absences: Absences = Absences.NULL,
) -> Path:
    """Écrit `lignes` dans `<dossier>/<nom>.parquet`, selon le schéma déclaré.

    Une ligne dont les clés ne correspondent pas au schéma est refusée : une clé mal
    orthographiée écrirait une colonne de NULL, que la Définition computable lirait comme
    « non documenté ». Une faute de frappe ne doit pas devenir une absence clinique.
    """
    schema = SCHEMAS[nom]
    absences = Absences(absences)
    for ligne in lignes:
        _verifier_colonnes(nom, schema, ligne)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{nom}.parquet"
    colonnes = ", ".join(f'"{colonne}" {type_}' for colonne, type_ in schema.items())
    with connexion() as con:
        con.execute(f'CREATE TABLE "{nom}" ({colonnes})')
        if lignes:
            valeurs = ", ".join("?" for _ in schema)
            con.executemany(
                f'INSERT INTO "{nom}" VALUES ({valeurs})',
                [
                    [_valeur(ligne[colonne], type_, absences) for colonne, type_ in schema.items()]
                    for ligne in lignes
                ],
            )
        con.execute(f'COPY "{nom}" TO ? (FORMAT PARQUET)', [str(chemin)])
    return chemin


def _valeur(valeur: Any, type_: str, absences: Absences) -> Any:
    """Écrit l'absence telle que la source concernée l'écrirait."""
    if valeur is None and absences is Absences.DEFAUTS:
        return SENTINELLES[type_]
    return valeur


def _verifier_colonnes(nom: str, schema: Mapping[str, str], ligne: Mapping[str, Any]) -> None:
    manquantes = sorted(set(schema) - set(ligne))
    inconnues = sorted(set(ligne) - set(schema))
    if manquantes or inconnues:
        raise ValueError(
            f"table {nom} : colonnes manquantes {manquantes}, colonnes inconnues {inconnues}"
        )


def lire(chemin: Path) -> list[dict[str, Any]]:
    """Lit un fichier Parquet et rend ses lignes comme des dictionnaires."""
    with connexion() as con:
        resultat = con.execute("SELECT * FROM read_parquet(?)", [str(chemin)])
        colonnes = [description[0] for description in resultat.description or []]
        return [dict(zip(colonnes, ligne, strict=True)) for ligne in resultat.fetchall()]
