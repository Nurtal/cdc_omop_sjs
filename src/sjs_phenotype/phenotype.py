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
from sjs_phenotype.concepts import Vocabulaire
from sjs_phenotype.extraction import Origine
from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut, niveau_pour

CODE_VHC = "B18.2"

_REQUETE_ANTI_SSA = """
WITH resultats AS (
    SELECT
        person_id,
        {jour} AS jour,
        CASE
            WHEN {valeur_codee} = $positive THEN 'positif'
            WHEN {valeur_codee} = $negative THEN 'négatif'
            WHEN {nombre} IS NOT NULL AND {seuil} IS NOT NULL
                 AND {nombre} > {seuil} THEN 'positif'
            WHEN {nombre} IS NOT NULL AND {seuil} IS NOT NULL THEN 'négatif'
        END AS statut
    FROM read_parquet($measurement)
    WHERE list_contains($concepts, measurement_concept_id)
)
SELECT
    p.person_id,
    count(r.statut) AS nb_resultats,
    count(*) FILTER (WHERE r.statut = 'positif') AS nb_positifs,
    min(r.jour) FILTER (WHERE r.statut = 'positif') AS premiere_preuve
FROM read_parquet($person) p
LEFT JOIN resultats r ON r.person_id = p.person_id
GROUP BY p.person_id
ORDER BY p.person_id
"""


_REQUETE_ITEMS = """
WITH resultats AS (
    SELECT
        person_id,
        {jour} AS jour,
        {nombre} {sens} $seuil AS positif,
        measurement_type_concept_id = $type_nlp AS du_texte
    FROM read_parquet($measurement)
    WHERE list_contains($concepts, measurement_concept_id) AND {nombre} IS NOT NULL
)
SELECT
    person_id,
    count(*) AS nb_resultats,
    count(*) FILTER (WHERE positif) AS nb_positifs,
    min(jour) FILTER (WHERE positif) AS premiere_preuve,
    -- L'origine doit suivre la preuve qui décide du Statut, pas n'importe quelle ligne :
    -- sinon le retrait de source attribuerait au texte un Item tranché par le structuré.
    count(*) FILTER (WHERE positif AND du_texte) AS nb_positifs_texte,
    count(*) FILTER (WHERE du_texte) AS nb_texte
FROM resultats
GROUP BY person_id
"""

_REQUETE_EXCLUSIONS = """
SELECT DISTINCT c.person_id, c.condition_concept_id
FROM read_parquet($condition) c
WHERE list_contains($codes, c.condition_concept_id)
ORDER BY c.person_id, c.condition_concept_id
"""

_REQUETE_VHC_ACTIF = """
SELECT DISTINCT person_id
FROM read_parquet($measurement)
WHERE measurement_concept_id = $pcr AND {valeur_codee} = $positive
"""


@dataclass(frozen=True)
class Parametres:
    vocabulaire: Vocabulaire = field(default_factory=Vocabulaire.par_defaut)
    absences: omop.Absences = omop.Absences.NULL


def run_phenotype(dossier_omop: Path, parametres: Parametres | None = None) -> list[LignePhenotype]:
    """Calcule la table phénotype pour tous les patients du dossier OMOP."""
    parametres = parametres or Parametres()
    absences = omop.Absences(parametres.absences)
    requete = _REQUETE_ANTI_SSA.format(
        jour=_lue("measurement_date", "DATE", absences),
        valeur_codee=_lue("value_as_concept_id", "BIGINT", absences),
        nombre=_lue("value_as_number", "DOUBLE", absences),
        seuil=_lue("range_high", "DOUBLE", absences),
    )
    vocabulaire = parametres.vocabulaire
    with omop.connexion() as con:
        lignes = con.execute(
            requete,
            {
                "positive": vocabulaire.valeur_positive,
                "negative": vocabulaire.valeur_negative,
                "concepts": list(vocabulaire.anti_ssa.anti_ssa),
                "measurement": str(dossier_omop / "measurement.parquet"),
                "person": str(dossier_omop / "person.parquet"),
            },
        ).fetchall()
        exclusions = _exclusions(con, dossier_omop, vocabulaire, absences)
        items = _items_mesures(con, dossier_omop, vocabulaire, absences)
    return [
        _ligne(
            int(person_id),
            nb_resultats,
            nb_positifs,
            premiere_preuve,
            exclusions.get(int(person_id), ()),
            items.get(int(person_id), {}),
        )
        for person_id, nb_resultats, nb_positifs, premiere_preuve in lignes
    ]


# Chaque Item numérique, ses concepts et le sens de son seuil : « ≥ » pour le focus score
# et l'OSS, « ≤ » pour le Schirmer et le débit salivaire. Le Schirmer en a plusieurs — un
# site qui code par œil doit être reconnu comme un site qui ne latéralise pas.
_SEUILS: Mapping[Item, tuple[str, float, bool]] = {
    Item.FOCUS_SCORE: ("focus_score", 1.0, True),
    Item.OSS: ("oss", 5.0, True),
    Item.SCHIRMER: ("schirmer", 5.0, False),
    Item.DEBIT_SALIVAIRE: ("debit_salivaire", 0.1, False),
}


def _concepts_item(vocabulaire: Vocabulaire, code: str) -> list[int]:
    """Tous les concepts d'un Item : le groupe s'il existe, le code seul sinon."""
    try:
        membres = vocabulaire.items.groupe(code)
    except KeyError:
        membres = (code,)
    return [vocabulaire.items.concept(membre) for membre in membres]


def _items_mesures(
    con: Any, dossier_omop: Path, vocabulaire: Vocabulaire, absences: omop.Absences
) -> dict[int, dict[Item, tuple[Statut, date | None, bool]]]:
    """Les Items numériques, quelle que soit l'origine de la mesure.

    La Définition computable lit MEASUREMENT sans se soucier de savoir si la valeur a été
    saisie au dossier ou extraite d'un compte rendu ; elle retient seulement d'où elle
    vient, pour préparer le retrait de source.
    """
    chemin = dossier_omop / "measurement.parquet"
    if not chemin.exists():
        return {}

    type_nlp = vocabulaire.items.concept("type_nlp")
    resultats: dict[int, dict[Item, tuple[Statut, date | None, bool]]] = {}
    for item, (code, seuil, au_dessus) in _SEUILS.items():
        requete = _REQUETE_ITEMS.format(
            nombre=_lue("value_as_number", "DOUBLE", absences),
            jour=_lue("measurement_date", "DATE", absences),
            sens=">=" if au_dessus else "<=",
        )
        lignes = con.execute(
            requete,
            {
                "measurement": str(chemin),
                "concepts": _concepts_item(vocabulaire, code),
                "seuil": seuil,
                "type_nlp": type_nlp,
            },
        ).fetchall()
        for person_id, nb_resultats, nb_positifs, preuve, nb_pos_texte, nb_texte in lignes:
            statut = _statut(nb_resultats, nb_positifs)
            # Un Item positif doit son origine à la preuve positive ; un Item négatif, à
            # l'ensemble des résultats qui l'ont rendu négatif.
            du_texte = bool(nb_pos_texte) if nb_positifs else bool(nb_texte)
            resultats.setdefault(int(person_id), {})[item] = (statut, preuve, du_texte)
    return resultats


def _exclusions(
    con: Any, dossier_omop: Path, vocabulaire: Vocabulaire, absences: omop.Absences
) -> dict[int, tuple[str, ...]]:
    """Les Critères d'exclusion calculables, sur tout l'historique du patient.

    Le critère est nommé d'après l'identifiant de concept, jamais d'après
    `condition_source_value` : ce texte libre est souvent vide dans un export OMOP.

    L'hépatite C n'exclut que si elle est active : le code CIM-10 doit être accompagné
    d'une PCR positive. Deux critères (radiothérapie cervico-faciale, maladie à IgG4) n'ont
    pas de code OMS spécifique et ne sont pas appliqués ; l'évaluation le signale.
    """
    chemin = dossier_omop / "condition_occurrence.parquet"
    if not chemin.exists():
        return {}

    codes = vocabulaire.diagnostics.groupe("criteres_exclusion")
    lignes = con.execute(
        _REQUETE_EXCLUSIONS,
        {
            "condition": str(chemin),
            "codes": [vocabulaire.diagnostics.concept(code) for code in codes],
        },
    ).fetchall()

    vhc_actif = {
        int(person_id)
        for (person_id,) in con.execute(
            _REQUETE_VHC_ACTIF.format(valeur_codee=_lue("value_as_concept_id", "BIGINT", absences)),
            {
                "measurement": str(dossier_omop / "measurement.parquet"),
                "pcr": vocabulaire.biologie.concept("pcr_vhc"),
                "positive": vocabulaire.valeur_positive,
            },
        ).fetchall()
    }

    concept_vhc = vocabulaire.diagnostics.concept(CODE_VHC)
    exclusions: dict[int, tuple[str, ...]] = {}
    for person_id, concept_id in lignes:
        # Le code seul ne dit pas si l'hépatite C est active : la PCR le dit.
        if concept_id == concept_vhc and int(person_id) not in vhc_actif:
            continue
        critere = vocabulaire.diagnostics.code(int(concept_id))
        exclusions[int(person_id)] = exclusions.get(int(person_id), ()) + (critere,)
    return exclusions


def _lue(colonne: str, type_: str, absences: omop.Absences) -> str:
    """Neutralise la valeur par défaut d'une source qui n'accepte pas NULL.

    Sans cela, un `range_high` absent encodé à 0 ferait basculer tout dosage numérique du
    côté « négatif », et un Schirmer absent, à 0 mm, deviendrait positif (ADR-0005).

    La réciproque est une perte assumée : une source qui n'accepte pas NULL ne permet plus
    de distinguer un vrai 0 d'une absence, et le vrai 0 devient « non documenté ». On perd
    donc un résultat plutôt que d'en inventer un — c'est aussi pourquoi le pipeline lit le
    Parquet et non ClickHouse (ADR-0002).
    """
    if absences == omop.Absences.NULL:
        return colonne
    return f"nullif({colonne}, {_litteral(omop.SENTINELLES[type_], type_)})"


def _litteral(sentinelle: Any, type_: str) -> str:
    if type_ == "DATE":
        return f"DATE '{sentinelle.isoformat()}'"
    if type_ == "VARCHAR":
        echappee = str(sentinelle).replace("'", "''")
        return f"'{echappee}'"
    return str(sentinelle)


def _ligne(
    person_id: int,
    nb_resultats: int,
    nb_positifs: int,
    premiere_preuve: date | None,
    criteres: tuple[str, ...] = (),
    items: Mapping[Item, tuple[Statut, date | None, bool]] | None = None,
) -> LignePhenotype:
    items = items or {}
    statuts = {item: Statut.NON_DOCUMENTE for item in Item}
    statuts[Item.ANTI_SSA] = _statut(nb_resultats, nb_positifs)
    origines = {item: Origine.AUCUNE for item in Item}
    if statuts[Item.ANTI_SSA] is not Statut.NON_DOCUMENTE:
        origines[Item.ANTI_SSA] = Origine.STRUCTUREE

    preuves_items: list[tuple[date, int]] = []
    for item, (statut, preuve, du_texte) in items.items():
        statuts[item] = statut
        origines[item] = Origine.TEXTE if du_texte else Origine.STRUCTUREE
        if statut is Statut.POSITIF and preuve is not None:
            preuves_items.append((preuve, item.points))

    score_observe = sum(item.points for item, s in statuts.items() if s is Statut.POSITIF)
    score_atteignable = score_observe + sum(
        item.points for item, s in statuts.items() if s is Statut.NON_DOCUMENTE
    )
    preuves = [(premiere_preuve, Item.ANTI_SSA.points)] if premiere_preuve else []
    preuves += preuves_items
    return LignePhenotype(
        person_id=int(person_id),
        statuts=statuts,
        score_observe=score_observe,
        score_atteignable=score_atteignable,
        niveau=niveau_pour(score_observe, score_atteignable),
        dates_atteinte=_dates_atteinte(preuves, score_atteignable),
        criteres_exclusion=criteres,
        origines=origines,
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
    """Écrit la table phénotype dans `<dossier>/phenotype.parquet` et rend son chemin.

    Toujours en NULL : ce que le projet produit n'a aucune raison d'imiter les valeurs par
    défaut d'un entrepôt qui n'accepte pas l'absence.
    """
    lignes: list[Mapping[str, Any]] = [
        {
            "person_id": ligne.person_id,
            **{f"statut_{item.value}": str(ligne.statuts[item]) for item in Item},
            "score_observe": ligne.score_observe,
            "score_atteignable": ligne.score_atteignable,
            "niveau": str(ligne.niveau),
            "date_probable": ligne.dates_atteinte.get(Niveau.PROBABLE),
            "date_defini": ligne.dates_atteinte.get(Niveau.DEFINI),
            "exclu": ligne.exclu,
            "criteres_exclusion": ", ".join(ligne.criteres_exclusion),
            **{
                f"origine_{item.value}": str(ligne.origines.get(item, Origine.AUCUNE))
                for item in Item
            },
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
                criteres_exclusion=tuple(
                    critere
                    for critere in (brute.get("criteres_exclusion") or "").split(", ")
                    if critere
                ),
                origines={
                    item: Origine(brute.get(f"origine_{item.value}") or Origine.AUCUNE)
                    for item in Item
                },
            )
        )
    return table
