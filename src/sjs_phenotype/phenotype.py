"""Seam 1 : un dossier OMOP en Parquet entre, une table phénotype sort.

La Définition computable transpose les critères ACR/EULAR 2016. Elle n'utilise jamais
les codes CIM-10 de SjD, et ne lit jamais l'État réel du jeu synthétique.

À ce jalon, seul l'Item Anti-SSA est calculé : les quatre autres viennent du texte, qui
n'est pas encore extrait. Ils portent donc le Statut « non documenté », et comme l'Anti-SSA
ne vaut que 3 points, personne n'atteint Défini.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sjs_phenotype import omop
from sjs_phenotype.concepts import JeuDeConcepts
from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut, niveau_pour

_REQUETE_ANTI_SSA = """
WITH resultats AS (
    SELECT
        person_id,
        measurement_date,
        CASE
            WHEN value_as_concept_id = $positive THEN 'positif'
            WHEN value_as_concept_id = $negative THEN 'négatif'
            WHEN value_as_number IS NOT NULL AND range_high IS NOT NULL
                 AND value_as_number > range_high THEN 'positif'
            WHEN value_as_number IS NOT NULL AND range_high IS NOT NULL THEN 'négatif'
        END AS statut
    FROM read_parquet($measurement)
    WHERE list_contains($concepts, measurement_concept_id)
)
SELECT
    p.person_id,
    count(r.statut) AS nb_resultats,
    count(*) FILTER (WHERE r.statut = 'positif') AS nb_positifs,
    min(r.measurement_date) FILTER (WHERE r.statut = 'positif') AS premiere_preuve
FROM read_parquet($person) p
LEFT JOIN resultats r ON r.person_id = p.person_id
GROUP BY p.person_id
ORDER BY p.person_id
"""


@dataclass(frozen=True)
class Parametres:
    concepts: JeuDeConcepts = field(default_factory=JeuDeConcepts.par_defaut)


def run_phenotype(dossier_omop: Path, parametres: Parametres | None = None) -> list[LignePhenotype]:
    """Calcule la table phénotype pour tous les patients du dossier OMOP."""
    parametres = parametres or Parametres()
    with omop.connexion() as con:
        lignes = con.execute(
            _REQUETE_ANTI_SSA,
            {
                "positive": parametres.concepts.valeur_positive,
                "negative": parametres.concepts.valeur_negative,
                "concepts": list(parametres.concepts.anti_ssa),
                "measurement": str(dossier_omop / "measurement.parquet"),
                "person": str(dossier_omop / "person.parquet"),
            },
        ).fetchall()
    return [_ligne(*brute) for brute in lignes]


def _ligne(
    person_id: int, nb_resultats: int, nb_positifs: int, premiere_preuve: date | None
) -> LignePhenotype:
    statuts = {item: Statut.NON_DOCUMENTE for item in Item}
    statuts[Item.ANTI_SSA] = _statut(nb_resultats, nb_positifs)

    score_observe = sum(item.points for item, s in statuts.items() if s is Statut.POSITIF)
    score_atteignable = score_observe + sum(
        item.points for item, s in statuts.items() if s is Statut.NON_DOCUMENTE
    )
    preuves = [(premiere_preuve, Item.ANTI_SSA.points)] if premiere_preuve else []
    return LignePhenotype(
        person_id=int(person_id),
        statuts=statuts,
        score_observe=score_observe,
        score_atteignable=score_atteignable,
        niveau=niveau_pour(score_observe, score_atteignable),
        dates_atteinte=_dates_atteinte(preuves, score_atteignable),
    )


def _statut(nb_resultats: int, nb_positifs: int) -> Statut:
    """Un résultat exploitable dit positif ou négatif ; son absence ne dit rien."""
    if nb_positifs:
        return Statut.POSITIF
    if nb_resultats:
        return Statut.NEGATIF
    return Statut.NON_DOCUMENTE


def _dates_atteinte(
    preuves: Sequence[tuple[date, int]], score_atteignable: int
) -> dict[Niveau, date]:
    """Première date où les preuves accumulées suffisent pour chaque Niveau."""
    dates: dict[Niveau, date] = {}
    cumul = 0
    for jour, points in sorted(preuves):
        cumul += points
        if Niveau.PROBABLE not in dates and cumul >= 3 and score_atteignable >= 4:
            dates[Niveau.PROBABLE] = jour
        if Niveau.DEFINI not in dates and cumul >= 4:
            dates[Niveau.DEFINI] = jour
    return dates


def ecrire(table: Sequence[LignePhenotype], dossier: Path) -> Path:
    """Écrit la table phénotype dans `<dossier>/phenotype.parquet` et rend son chemin."""
    lignes: list[Mapping[str, Any]] = [
        {
            "person_id": ligne.person_id,
            **{f"statut_{item.value}": str(ligne.statuts[item]) for item in Item},
            "score_observe": ligne.score_observe,
            "score_atteignable": ligne.score_atteignable,
            "niveau": str(ligne.niveau),
            "date_probable": ligne.dates_atteinte.get(Niveau.PROBABLE),
            "date_defini": ligne.dates_atteinte.get(Niveau.DEFINI),
        }
        for ligne in table
    ]
    return omop.ecrire_table(dossier, "phenotype", lignes)


def lire(chemin: Path) -> list[LignePhenotype]:
    """Relit une table phénotype écrite par `ecrire`."""
    table = []
    for brute in omop.lire(chemin):
        dates = {
            niveau: brute[colonne]
            for niveau, colonne in (
                (Niveau.PROBABLE, "date_probable"),
                (Niveau.DEFINI, "date_defini"),
            )
            if brute[colonne] is not None
        }
        table.append(
            LignePhenotype(
                person_id=int(brute["person_id"]),
                statuts={item: Statut(brute[f"statut_{item.value}"]) for item in Item},
                score_observe=int(brute["score_observe"]),
                score_atteignable=int(brute["score_atteignable"]),
                niveau=Niveau(brute["niveau"]),
                dates_atteinte=dates,
            )
        )
    return table
