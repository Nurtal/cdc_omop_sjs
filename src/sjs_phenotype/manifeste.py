"""Manifeste d'exécution : ce qui rend un résultat rattachable à ce qui l'a produit.

Un chiffre sans manifeste n'est pas reproductible — on ignore quel code, quels concepts
et quels paramètres l'ont produit. Deux exécutions identiques donnent deux manifestes
identiques, hors horodatage : c'est la définition de la Reproductibilité retenue par le
projet, distincte de la Robustesse et de la Portabilité.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata, resources
from pathlib import Path
from typing import Any

from sjs_phenotype.concepts import PREMIER_CONCEPT_LOCAL, Vocabulaire


def jeux_de_concepts() -> tuple[str, ...]:
    """Les jeux de concepts effectivement livrés, lus dans le paquet.

    Une liste écrite en dur laisserait un jeu ajouté plus tard hors de l'empreinte du
    vocabulaire — or c'est précisément ce que cette empreinte sert à détecter.
    """
    fichiers = resources.files("sjs_phenotype.jeux_de_concepts")
    return tuple(
        sorted(
            fichier.name.removesuffix(".json")
            for fichier in fichiers.iterdir()
            if fichier.name.endswith(".json")
        )
    )


def empreinte_fichier(chemin: Path) -> str:
    """Empreinte SHA-256 d'un fichier, tronquée : elle sert à comparer, pas à sécuriser."""
    return hashlib.sha256(chemin.read_bytes()).hexdigest()[:16]


def empreinte_texte(texte: str) -> str:
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Manifeste:
    """Tout ce qu'il faut pour rejouer une exécution et reconnaître ses résultats."""

    version_code: str
    horodatage: str
    travail: str
    absences: str
    scenario: dict[str, Any]
    entrees: dict[str, str]
    vocabulaire: dict[str, Any]

    def en_json(self) -> dict[str, Any]:
        return {
            "version_code": self.version_code,
            "horodatage": self.horodatage,
            "travail": self.travail,
            "absences": self.absences,
            "scenario": self.scenario,
            "entrees": self.entrees,
            "vocabulaire": self.vocabulaire,
        }

    def ecrire(self, chemin: Path) -> Path:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(
            json.dumps(self.en_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return chemin

    @classmethod
    def lire(cls, chemin: Path) -> Manifeste:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
        return cls(**contenu)

    @classmethod
    def produire(
        cls,
        travail: Path,
        scenario: dict[str, Any] | None = None,
        absences: str = "null",
    ) -> Manifeste:
        """Relève l'état du code, des concepts et des entrées au moment de l'exécution.

        `absences` est l'encodage réellement employé pour lire les données, qui peut
        différer de celui du scénario : sans cela, deux exécutions aux Statuts différents
        produiraient le même manifeste.
        """
        return cls(
            version_code=_version_code(),
            horodatage=datetime.now(UTC).isoformat(timespec="seconds"),
            travail=str(travail),
            absences=str(absences),
            scenario=scenario or {},
            entrees=_empreintes_entrees(travail),
            vocabulaire=etat_vocabulaire(),
        )


def etat_vocabulaire() -> dict[str, Any]:
    """L'état des jeux de concepts : empreinte, concepts locaux, instantanés à vérifier.

    Les concepts locaux (≥ 2 000 000 000) sont une entorse assumée aux concepts standard
    (ADR-0006) : elle doit rester visible dans chaque résultat, pas seulement dans le code.
    """
    noms = jeux_de_concepts()
    empreintes: dict[str, str] = {}
    a_verifier: list[str] = []
    for nom in noms:
        fichier = resources.files("sjs_phenotype.jeux_de_concepts") / f"{nom}.json"
        texte = fichier.read_text(encoding="utf-8")
        empreintes[nom] = empreinte_texte(texte)
        instantane = json.loads(texte).get("instantane_vocabulaire", {})
        if instantane.get("a_verifier"):
            a_verifier.append(nom)

    return {
        "empreinte": empreinte_texte("".join(empreintes[nom] for nom in noms)),
        "jeux": empreintes,
        "jeux_a_verifier": sorted(a_verifier),
        "concepts_locaux": concepts_locaux(),
        "seuil_concept_local": PREMIER_CONCEPT_LOCAL,
    }


def concepts_locaux() -> dict[str, list[int]]:
    """Les concepts locaux, nommés jeu par jeu plutôt que comptés.

    Un lecteur qui voit « 17 » ne sait pas lesquels : l'entorse aux concepts standard
    (voir ADR-0006) doit être lisible, pas seulement chiffrée.
    """
    vocabulaire = Vocabulaire.par_defaut()
    tables = {
        "biologie": vocabulaire.biologie,
        "diagnostics": vocabulaire.diagnostics,
        "items": vocabulaire.items,
        "medicaments": vocabulaire.medicaments,
        "notes": vocabulaire.notes,
        "visites": vocabulaire.visites,
    }
    locaux = {
        nom: sorted(
            concept_id
            for concept_id in table.concepts.values()
            if concept_id >= PREMIER_CONCEPT_LOCAL
        )
        for nom, table in tables.items()
    }
    anti_ssa = vocabulaire.anti_ssa
    locaux["anti_ssa"] = sorted(
        concept_id
        for concept_id in (
            *anti_ssa.anti_ro60,
            *anti_ssa.anti_ro52,
            *anti_ssa.anti_ssa_non_differencie,
            *anti_ssa.anti_ssb,
            anti_ssa.valeur_positive,
            anti_ssa.valeur_negative,
        )
        if concept_id >= PREMIER_CONCEPT_LOCAL
    )
    return {nom: ids for nom, ids in sorted(locaux.items()) if ids}


def _empreintes_entrees(travail: Path) -> dict[str, str]:
    """Les fichiers lus par l'exécution, chacun avec son empreinte."""
    empreintes: dict[str, str] = {}
    for chemin in sorted((travail / "omop").glob("*.parquet")):
        empreintes[f"omop/{chemin.name}"] = empreinte_fichier(chemin)
    scenario = travail / "scenario.toml"
    if scenario.exists():
        empreintes["scenario.toml"] = empreinte_fichier(scenario)
    return empreintes


def _version_code() -> str:
    try:
        return metadata.version("sjs-phenotype")
    except metadata.PackageNotFoundError:  # pragma: no cover - paquet non installé
        return "inconnue"
