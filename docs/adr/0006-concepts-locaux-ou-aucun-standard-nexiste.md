# Concepts locaux là où aucun standard n'existe

ADR-0002 promettait des concepts standard uniquement. La vérification du 2026-09-21
(voir `docs/vocabulaire-athena.md`) a montré que deux Items ACR/EULAR 2016 n'en ont aucun,
ni en LOINC ni en SNOMED CT : le **focus score** de biopsie de glande salivaire (3 points)
et l'**Ocular Staining Score** (1 point). Le projet leur attribue donc des identifiants
locaux, dans la plage OMOP réservée `>= 2 000 000 000`.

Cette entorse est rendue visible plutôt que tue : chaque manifeste d'exécution liste les
concepts locaux jeu par jeu, et `docs/vocabulaire-athena.md` consigne, pour chaque item,
ce qui a été cherché et ce qui n'existe pas.

## Considered Options

Détourner un concept voisin. SNOMED `126766000` « Lymphoepithelial sialadenitis of
Sjögren's syndrome » est un diagnostic du domaine Condition, pas un score ; `415349007`
« Rose bengal staining of eye » est une procédure, et ne couvre ni la fluorescéine ni le
vert de lissamine de l'OSS. Porter une valeur numérique sur l'un ou l'autre aurait produit
des données fausses pour tout site qui les relirait comme le standard les définit.

Laisser `measurement_concept_id = 0` et ne garder que `measurement_source_value`. Fidèle
aux conventions OMOP pour un code non relié, mais la Définition computable ne pourrait
plus désigner ces Items autrement que par du texte source, propre à chaque site.

## Consequences

Un autre site OMOP ne peut pas relier ces deux Items sans adopter les mêmes identifiants
locaux, ou les remapper. Si le projet est partagé dans le réseau OHDSI, une soumission
LOINC auprès de Regenstrief pour ces deux mesures lèverait la difficulté à la source.

Les identifiants locaux restants (diagnostics CIM-10, biologie, médicaments, classes de
notes) sont, eux, provisoires : leurs jeux portent `a_verifier: true` et devront être
reliés aux concepts standard avant l'EDS.
