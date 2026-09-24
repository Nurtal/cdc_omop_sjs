# Vérification des concepts standard

Recherche menée le 2026-09-21 sur les vocabulaires standardisés, pour savoir lesquels des
concepts du projet existent en LOINC ou SNOMED CT, et lesquels doivent rester locaux
(identifiants ≥ 2 000 000 000, voir ADR-0006).

## Sources

`athena.ohdsi.org`, `loinc.org` et `browser.ihtsdotools.org` refusent les requêtes
automatisées. Trois sources primaires ont été interrogées à la place :

- **OHDSI ATLAS demo WebAPI** — `atlas-demo.ohdsi.org/WebAPI/vocabulary/search/` : fait
  autorité pour `concept_id`, `standard_concept` et `domain_id`. Instance en version
  WebAPI 2.14.0 (build 2024-09-01), donc vocabulaire OMOP daté d'environ mi-2024.
- **Serveur de terminologie FHIR `tx.fhir.org/r4`** — LOINC 2.82, SNOMED CT international.
- **NLM Clinical Table Search Service** — recoupement LOINC.

Chaque absence ci-dessous correspond à une recherche sans résultat sur **deux** sources
indépendantes, pas à une déduction.

## Synthèse

| Item | Verdict | Concept retenu |
|---|---|---|
| Focus score | Aucun concept standard | local |
| Ocular Staining Score | Aucun concept standard | local |
| Débit salivaire non stimulé | Partiel — pas de « non stimulé » | SNOMED 251339001 (4088662) |
| Schirmer | Disponible | LOINC 29003-1 / 29004-9 |
| Anti-SSA, Ro52, Ro60, SSB | Couverture complète | LOINC |

## Les deux trous de vocabulaire

**Focus score** et **Ocular Staining Score** n'ont aucun concept standard, ni LOINC ni
SNOMED. Ce sont pourtant deux Items ACR/EULAR 2016, pesant 3 points et 1 point. Ils
gardent donc des identifiants locaux.

Concepts voisins écartés, parce qu'ils ne portent pas la valeur numérique :

- SNOMED `126766000` « Lymphoepithelial sialadenitis of Sjögren's syndrome » (OMOP
  4130853) est un diagnostic histologique, dans le domaine Condition — pas un score.
- SNOMED `415349007` « Rose bengal staining of eye » (OMOP 4187472) est la procédure de
  coloration. L'utiliser pour porter un OSS serait un détournement, et il ne couvre ni la
  fluorescéine ni le vert de lissamine.
- LOINC `85327-5` « Foci [#] in Breast cancer specimen » est spécifique au sein.

Si le projet est partagé dans le réseau OHDSI, ces deux manques mériteraient une
soumission LOINC auprès de Regenstrief.

## Débit salivaire : deux réserves

SNOMED `251339001` « Whole saliva flow rate » (OMOP **4088662**, standard) existe, mais :

1. **Aucune distinction stimulé / non stimulé.** La hiérarchie sous `251338009` ne contient
   que whole, parotid et submandibular. Le qualificatif `255371003` « Unstimulated » existe
   isolément, mais aucun concept pré-coordonné ne les combine. Or le critère ACR/EULAR vise
   spécifiquement le débit **non stimulé** (≤ 0,1 mL/min).
2. **Domaine OMOP = Observation**, pas Measurement. Une décision de modélisation reste donc
   à prendre au moment de l'extraction (#10) : suivre le domaine OMOP et écrire dans
   OBSERVATION, ou garder tous les Items dans MEASUREMENT au prix d'un écart au standard.

## Schirmer : les codes initialement retenus étaient les mauvais

Une note antérieure du projet citait LOINC 29008-0 et 29010-6. Vérification faite :

- `29008-0` = « Left eye Tear secretion break up [Time] Schirmer test » — propriété *temps*,
  unités **secondes**. C'est un temps de rupture du film lacrymal, pas des millimètres.
- `29010-6` = « Left eye Tear secretion comment [Interpretation] » — texte libre.
- Les deux portent sur l'**œil gauche** seulement.

La famille compte huit codes, tous standard en OMOP, domaine Measurement. « Tear secretion
1 » désigne le Schirmer I (sans anesthésie), celui du critère ACR/EULAR :

| LOINC | concept_id | Libellé | Unité |
|---|---|---|---|
| **29003-1** | **3025758** | Right eye Tear secretion 1 Schirmer test | mm |
| **29004-9** | **3025415** | Left eye Tear secretion 1 Schirmer test | mm |
| 29005-6 | 3025963 | Right eye Tear secretion 2 Schirmer test | mm |
| 29006-4 | 3012780 | Left eye Tear secretion 2 Schirmer test | mm |
| 29007-2 | 3027307 | Right eye Tear secretion break up [Time] | s |
| 29008-0 | 3012972 | Left eye Tear secretion break up [Time] | s |
| 29009-8 | 3010700 | Right eye Tear secretion comment | — |
| 29010-6 | 3026322 | Left eye Tear secretion comment | — |

Aucun code LOINC non latéralisé n'existe. Pour un Schirmer sans latéralité, SNOMED
`397547000` « Schirmer I test » (OMOP **4287641**, domaine Measurement) convient.

## Sérologie : couverture complète

LOINC n'emploie jamais « Ro52 » ni « Ro60 » mais « Sjogrens syndrome-A extractable nuclear
**52kD** / **60kD** Ab » — d'où l'échec des recherches naïves. Tous standard, domaine
Measurement :

| Analyte | LOINC | concept_id | Libellé |
|---|---|---|---|
| Anti-SSA total | 8093-7 | **3015154** | Sjogrens syndrome-A extractable nuclear Ab [Presence] in Serum |
| Anti-SSA total, quanti | 17792-3 | 3023939 | …[Units/volume] in Serum |
| Anti-Ro60 | 53018-8 | **3040499** | …60kD Ab [Presence] in Serum |
| Anti-Ro60, quanti | 53019-6 | 3041423 | …60kD Ab [Units/volume] in Serum |
| Anti-Ro52 | 53016-2 | **3039348** | …52kD Ab [Presence] in Serum |
| Anti-Ro52, quanti | 53017-0 | 3041067 | …52kD Ab [Units/volume] in Serum |
| Anti-SSB/La | 8094-5 | **3008914** | Sjogrens syndrome-B extractable nuclear Ab [Presence] in Serum |
| Anti-SSB/La, quanti | 17791-5 | 3027450 | …[Units/volume] in Serum |

La famille compte 45 codes « in Serum » avec les variantes par méthode (immunoassay,
immunoblot, line blot). Elles seront utiles au moment de la correspondance des codes locaux
de l'EDS vers LOINC.

SNOMED offre `59260005` « Antibody to SS-A measurement » (OMOP 4241825) et `27904004`
« Antibody to lupus La protein measurement » (OMOP 4101092), mais **ne distingue pas Ro52
de Ro60** : pour cette granularité, LOINC est obligatoire.

## Limite de cette vérification

Les `concept_id` viennent d'une instance ATLAS dont le vocabulaire date d'environ septembre
2024. Les codes LOINC et SNOMED eux-mêmes sont confirmés sur LOINC 2.82. Aucun des codes
retenus n'est récent au point d'échapper à cette instance, mais un `concept_id` reste à
reconfirmer sur l'instantané de vocabulaire effectivement déployé à l'EDS.
