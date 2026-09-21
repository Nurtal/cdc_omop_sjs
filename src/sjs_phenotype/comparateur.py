"""Comparateur CIM-10 : les patients porteurs d'un code de SjD.

Chemin délibérément distinct de la Définition computable, qui n'utilise jamais ces codes.
C'est ce qui rend la comparaison lisible : deux repérages indépendants, qu'on confronte
sans dire lequel a raison — sur l'EDS il n'y a pas de référence (ADR-0004).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sjs_phenotype import omop
from sjs_phenotype.concepts import Vocabulaire

CODE_SJD = "M35.0"

_REQUETE = """
SELECT person_id
FROM read_parquet($condition)
WHERE condition_concept_id = $code
GROUP BY person_id
HAVING count(DISTINCT condition_start_date) >= $minimum
ORDER BY person_id
"""


@dataclass(frozen=True)
class Comparateur:
    """Comment le Comparateur CIM-10 est construit.

    Le seuil compte des dates distinctes, non des lignes : deux diagnostics saisis le même
    jour décrivent une seule fois le patient, pas deux.
    """

    occurrences_minimum: int = 1
    vocabulaire: Vocabulaire = field(default_factory=Vocabulaire.par_defaut)

    def __post_init__(self) -> None:
        if self.occurrences_minimum < 1:
            raise ValueError("occurrences_minimum doit valoir au moins 1")


def comparateur_cim10(dossier_omop: Path, parametres: Comparateur | None = None) -> set[int]:
    """Les patients portant le code de SjD, toutes positions confondues."""
    parametres = parametres or Comparateur()
    chemin = dossier_omop / "condition_occurrence.parquet"
    if not chemin.exists():
        return set()

    with omop.connexion() as con:
        lignes = con.execute(
            _REQUETE,
            {
                "condition": str(chemin),
                "code": parametres.vocabulaire.diagnostics.concept(CODE_SJD),
                "minimum": parametres.occurrences_minimum,
            },
        ).fetchall()
    return {int(person_id) for (person_id,) in lignes}
