# « Non documenté » n'est pas « négatif »

Un Item ACR/EULAR absent de l'EDS peut l'être parce que l'examen n'a pas été fait, pas parce qu'il était négatif : dans un entrepôt hospitalier, l'absence est la règle, pas l'exception. Chaque item porte donc trois Statuts (positif, négatif, non documenté), et le patient reçoit un Score observé et un Score atteignable. De là les deux Niveaux de certitude : Défini (Score observé ≥4) et Probable (Score observé ≥3 et Score atteignable ≥4, donc bilan incomplet qui pourrait encore remplir les critères).

## Considered Options

Assimiler « non documenté » à « négatif » : plus simple, mais ne laisse subsister comme cas Définis que les patients au bilan complet, et transforme un défaut de recueil en jugement clinique. Cette variante est conservée comme analyse de Robustesse.

## Consequences

Le pipeline doit savoir si un examen a eu lieu (actes CCAM, présence d'un compte rendu), et jamais lire une valeur absente comme un 0 — d'où l'abandon de ClickHouse pour le calcul (voir ADR-0002).

Lorsqu'une source n'accepte pas l'absence et la remplace par une valeur par défaut, le pipeline neutralise ces valeurs à la lecture. La réciproque est assumée : un vrai 0 n'y est plus distinguable d'une absence et devient « non documenté ». On perd donc un résultat plutôt que d'en inventer un.
