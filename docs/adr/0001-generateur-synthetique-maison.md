# Générateur synthétique maison plutôt que Synthea

Les données synthétiques servent à concevoir et évaluer la Définition computable avant l'EDS. Synthea n'a pas de module SjD, et générer les patients avec les règles du phénotype rendrait l'évaluation circulaire. On écrit donc un générateur maison qui produit directement des tables OMOP à partir d'un État réel caché et d'un Processus d'observation explicite (prescription, saisie, codage, erreurs, profils confondants). C'est ce qui permet de mesurer de vraies performances et la Robustesse en dégradant les données de façon contrôlée.

## Considered Options

- Synthea + module SjD écrit sur mesure + ETL-Synthea : lourd, contrôle limité du Processus d'observation.
- Jeux OMOP synthétiques existants (Eunomia, SynPUF) : aucune SjD.

## Consequences

Les performances mesurées sur synthétique ne valent que sous les hypothèses du Processus d'observation : elles valident la logique de la Définition computable, pas sa validité clinique.
