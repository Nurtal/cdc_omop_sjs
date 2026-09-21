"""Seam 2 : une table phénotype entre, des tables de résultats sortent.

Fonction pure : aucune lecture de fichier, aucun accès au jeu de données. C'est ce qui
permet de vérifier les chiffres sur de petites tables écrites à la main.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sjs_phenotype.modele import Item, LignePhenotype, Niveau, Statut

PROFIL_INCONNU = "profil inconnu"

NIVEAUX_IDENTIFIES: tuple[Niveau, ...] = (Niveau.DEFINI, Niveau.PROBABLE)


@dataclass(frozen=True)
class Concordance:
    """Accord entre le phénotype et le Comparateur CIM-10, sans référence (ADR-0004).

    Kappa et Jaccard décrivent un recouvrement, pas une performance : aucun des deux
    ensembles n'est un standard de référence. Ils valent None quand les deux repérages
    sont vides — il n'y a alors rien à comparer.
    """

    les_deux: int
    phenotype_seul: int
    comparateur_seul: int
    aucun_des_deux: int
    kappa: float | None
    jaccard: float | None
    ids_phenotype_seul: tuple[int, ...]
    ids_comparateur_seul: tuple[int, ...]

    @property
    def total(self) -> int:
        return self.les_deux + self.phenotype_seul + self.comparateur_seul + self.aucun_des_deux

    def en_json(self) -> dict[str, Any]:
        return {
            "les_deux": self.les_deux,
            "phenotype_seul": self.phenotype_seul,
            "comparateur_seul": self.comparateur_seul,
            "aucun_des_deux": self.aucun_des_deux,
            "kappa": self.kappa,
            "jaccard": self.jaccard,
            "ids_phenotype_seul": list(self.ids_phenotype_seul),
            "ids_comparateur_seul": list(self.ids_comparateur_seul),
        }


def concordance(
    table: Sequence[LignePhenotype],
    comparateur: Collection[int],
    niveaux: Sequence[Niveau] = NIVEAUX_IDENTIFIES,
) -> Concordance:
    """Confronte les patients identifiés et ceux du Comparateur CIM-10."""
    retenus = set(niveaux)
    codes = set(comparateur)
    identifies = {ligne.person_id for ligne in table if ligne.niveau in retenus}
    tous = {ligne.person_id for ligne in table}

    les_deux = identifies & codes
    phenotype_seul = identifies - codes
    comparateur_seul = codes - identifies
    aucun_des_deux = tous - identifies - codes

    return Concordance(
        les_deux=len(les_deux),
        phenotype_seul=len(phenotype_seul),
        comparateur_seul=len(comparateur_seul),
        aucun_des_deux=len(aucun_des_deux),
        kappa=_kappa(
            len(les_deux), len(phenotype_seul), len(comparateur_seul), len(aucun_des_deux)
        ),
        jaccard=_jaccard(len(les_deux), len(identifies | codes)),
        ids_phenotype_seul=tuple(sorted(phenotype_seul)),
        ids_comparateur_seul=tuple(sorted(comparateur_seul)),
    )


def _jaccard(intersection: int, union: int) -> float | None:
    return intersection / union if union else None


def _kappa(
    les_deux: int, phenotype_seul: int, comparateur_seul: int, ni_lun_ni_lautre: int
) -> float | None:
    """Kappa de Cohen sur le tableau 2×2.

    Indéfini quand les deux repérages s'accordent parfaitement sur une seule catégorie :
    l'accord attendu vaut alors 1 et le dénominateur s'annule.
    """
    total = les_deux + phenotype_seul + comparateur_seul + ni_lun_ni_lautre
    if not total:
        return None

    observe = (les_deux + ni_lun_ni_lautre) / total
    part_phenotype = (les_deux + phenotype_seul) / total
    part_comparateur = (les_deux + comparateur_seul) / total
    attendu = part_phenotype * part_comparateur + (1 - part_phenotype) * (1 - part_comparateur)
    if attendu == 1:
        return None
    return (observe - attendu) / (1 - attendu)


@dataclass(frozen=True)
class Effectifs:
    """Combien de patients par Niveau de certitude, par Statut d'Item, et par Profil."""

    total: int
    par_niveau: Mapping[Niveau, int]
    par_niveau_hors_exclus: Mapping[Niveau, int]
    exclus: int
    par_statut: Mapping[Item, Mapping[Statut, int]]
    par_profil: Mapping[str, int]
    criteres_non_appliques: tuple[str, ...] = ()

    def en_json(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "par_niveau": {str(niveau): nombre for niveau, nombre in self.par_niveau.items()},
            "par_niveau_hors_exclus": {
                str(niveau): nombre for niveau, nombre in self.par_niveau_hors_exclus.items()
            },
            "exclus": self.exclus,
            "criteres_non_appliques": list(self.criteres_non_appliques),
            "par_statut": {
                str(item): {str(statut): nombre for statut, nombre in statuts.items()}
                for item, statuts in self.par_statut.items()
            },
            "par_profil": dict(self.par_profil),
        }


def evaluer(
    table: Sequence[LignePhenotype],
    profils: Mapping[int, str] | None = None,
    criteres_non_appliques: Sequence[str] = (),
) -> Effectifs:
    """Compte les patients. `profils` vient de l'État réel, connu du seul jeu synthétique.

    Les patients Exclus sont comptés deux fois : dans `par_niveau`, qui décrit ce que la
    Définition computable trouve, et à part dans `par_niveau_hors_exclus`, qui décrit ce
    qu'il en reste une fois les Critères d'exclusion appliqués.
    """
    par_niveau = {niveau: 0 for niveau in Niveau}
    par_niveau_hors_exclus = {niveau: 0 for niveau in Niveau}
    exclus = 0
    par_statut = {item: {statut: 0 for statut in Statut} for item in Item}
    par_profil: dict[str, int] = {}
    for ligne in table:
        par_niveau[ligne.niveau] += 1
        if ligne.exclu:
            exclus += 1
        else:
            par_niveau_hors_exclus[ligne.niveau] += 1
        for item, statut in ligne.statuts.items():
            par_statut[item][statut] += 1
        if profils is not None:
            # Un État réel dépareillé (jeu régénéré, dossier réutilisé) doit se voir dans
            # les chiffres, pas faire tomber l'évaluation.
            profil = profils.get(ligne.person_id, PROFIL_INCONNU)
            par_profil[profil] = par_profil.get(profil, 0) + 1
    return Effectifs(
        total=len(table),
        par_niveau=par_niveau,
        par_niveau_hors_exclus=par_niveau_hors_exclus,
        exclus=exclus,
        par_statut=par_statut,
        par_profil=par_profil,
        criteres_non_appliques=tuple(criteres_non_appliques),
    )


def formater(effectifs: Effectifs) -> str:
    """Rendu lisible en terminal, dans le vocabulaire du glossaire."""
    lignes = [f"Patients : {effectifs.total}", "", "Niveau de certitude"]
    lignes += [f"  {niveau:<14} {nombre:>6}" for niveau, nombre in effectifs.par_niveau.items()]
    if effectifs.exclus:
        lignes += ["", f"Exclus (Critère d'exclusion ACR/EULAR) : {effectifs.exclus}"]
        lignes += [
            f"  hors exclus : {niveau} {nombre}"
            for niveau, nombre in effectifs.par_niveau_hors_exclus.items()
            if niveau is not Niveau.AUCUN
        ]
    if effectifs.criteres_non_appliques:
        lignes += [
            "",
            "Critères d'exclusion non appliqués (aucun code CIM-10 OMS spécifique) : "
            + ", ".join(effectifs.criteres_non_appliques),
        ]
    lignes += ["", "Statut par Item ACR/EULAR"]
    for item, statuts in effectifs.par_statut.items():
        detail = "  ".join(f"{statut} {nombre}" for statut, nombre in statuts.items())
        lignes.append(f"  {item:<16} {detail}")
    if effectifs.par_profil:
        lignes += ["", "Profil (État réel, jeu synthétique)"]
        lignes += [
            f"  {profil:<32} {nombre:>6}" for profil, nombre in sorted(effectifs.par_profil.items())
        ]
    return "\n".join(lignes)


def formater_concordance(accord: Concordance, occurrences: int = 1) -> str:
    """Rendu lisible : un tableau croisé, puis les deux indices d'accord."""
    occurrence = "occurrence" if occurrences == 1 else "occurrences"
    lignes = [
        f"Concordance avec le Comparateur CIM-10 (M35.0, ≥ {occurrences} {occurrence})",
        "",
        f"{'':<22}{'codé':>10}{'non codé':>12}",
        f"{'identifié':<22}{accord.les_deux:>10}{accord.phenotype_seul:>12}",
        f"{'non identifié':<22}{accord.comparateur_seul:>10}{accord.aucun_des_deux:>12}",
        "",
        f"  kappa    {_indice(accord.kappa)}",
        f"  Jaccard  {_indice(accord.jaccard)}",
        "",
        "  Aucun des deux repérages n'est une référence : ces indices décrivent un",
        "  recouvrement, pas une performance.",
    ]
    return "\n".join(lignes)


def _indice(valeur: float | None) -> str:
    return "sans objet" if valeur is None else f"{valeur:.3f}"
