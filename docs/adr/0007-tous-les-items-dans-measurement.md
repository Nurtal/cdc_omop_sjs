# Tous les Items ACR/EULAR dans MEASUREMENT

Le seul concept standard approchant le débit salivaire, SNOMED `251339001` « Whole saliva
flow rate » (OMOP 4088662), relève du domaine **Observation** — et surtout ne porte pas le
qualificatif « non stimulé », alors que le critère ACR/EULAR vise précisément le débit non
stimulé (≤ 0,1 mL/min). Il ne dit donc pas ce que le projet mesure.

On déclare un concept local « débit salivaire non stimulé », comme pour le focus score et
l'Ocular Staining Score (ADR-0006), et les cinq Items vivent tous dans MEASUREMENT. Le
concept standard le plus proche est enregistré dans le jeu de concepts sous
`concept_standard_proche`, pour qu'un site receveur puisse faire le lien.

## Considered Options

Écrire le débit salivaire dans OBSERVATION avec le concept standard, par fidélité au
domaine OMOP. Rejeté pour deux raisons : le concept ne signifie pas « non stimulé », donc
la fidélité serait apparente et le sens faux ; et la Définition computable devrait lire
deux tables pour rassembler cinq Items qui forment un seul score, ce qui complique la
règle sans rien gagner.

Post-coordonner avec le qualificatif SNOMED `255371003` « Unstimulated ». OMOP ne
représente pas les expressions post-coordonnées : il aurait fallu les aplatir en un
concept, c'est-à-dire revenir à un concept local.

## Consequences

Un site qui aurait déjà relié son débit salivaire à 4088662 dans OBSERVATION ne serait pas
reconnu par la Définition computable telle quelle : la correspondance vers le concept local
fait partie du travail de portage, au même titre que les codes de biologie locaux.

La décision tient en un identifiant de concept et une table. Si l'usage du réseau OHDSI se
fixe autrement, elle se défait sans toucher à la logique du phénotype.
