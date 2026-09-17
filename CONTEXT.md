# Phénotypage SjD

Phénotypage computationnel de la maladie de Sjögren à partir de données hospitalières multimodales au format OMOP, conçu sur données synthétiques puis appliqué à l'EDS du Centre de Données Cliniques (monocentrique).

## Language

### Maladie

**SjD**:
Maladie de Sjögren, primaire ou associée à une autre connectivite, telle que définie par les critères ACR/EULAR 2016.
_Avoid_: SjS, pSS, SGS, syndrome de Gougerot-Sjögren, syndrome sec

**Connectivite associée**:
Autre maladie auto-immune systémique (PR, lupus, sclérodermie…) coexistant avec la SjD ; attribut du patient, jamais motif d'exclusion.
_Avoid_: SjD secondaire, Sjögren secondaire

**Critère d'entrée**:
Condition préalable ACR/EULAR 2016 (symptôme de sécheresse ou suspicion sur un domaine ESSDAI) ; non calculée dans ce projet.

**Item ACR/EULAR**:
L'un des cinq éléments pondérés des critères ACR/EULAR 2016 : focus score ≥1 (3), Anti-SSA (3), OSS ≥5 (1), Schirmer ≤5 mm/5 min (1), débit salivaire non stimulé ≤0,1 mL/min (1).
_Avoid_: critère (ambigu), variable

**Statut d'item**:
Valeur d'un Item ACR/EULAR pour un patient : positif, négatif ou non documenté ; non documenté n'est jamais assimilé à négatif.

**Score observé**:
Somme des points des Items ACR/EULAR positifs d'un patient.

**Score atteignable**:
Score observé augmenté des points des Items ACR/EULAR non documentés ; score maximal que le patient pourrait avoir.

**Critère d'exclusion**:
Condition ACR/EULAR 2016 (radiothérapie cervico-faciale, VHC actif, VIH, sarcoïdose, amylose, GVH, maladie à IgG4) ; seules celles calculables sont appliquées.

**Exclu**:
Statut d'un patient qui atteint un Niveau de certitude mais présente un Critère d'exclusion ; il est signalé à part, pas retiré.

### Phénotype

**Définition computable**:
Transposition déterministe des critères ACR/EULAR 2016 en concepts OMOP, qui attribue à chaque patient un Niveau de certitude ; elle n'utilise jamais les codes CIM-10 de SjD.
_Avoid_: algorithme, modèle, classifieur

**Niveau de certitude**:
Palier attribué par la Définition computable : Défini (Score observé ≥4) ou Probable (Score observé ≥3 et Score atteignable ≥4).
_Avoid_: possible, score, probabilité, classe

**Date d'atteinte**:
Première date à laquelle les preuves d'un patient suffisent pour un Niveau de certitude donné.

**Identification**:
Attribution à chaque patient d'un Niveau de certitude par la Définition computable.
_Avoid_: repérage, sélection, détection

**Caractérisation**:
Description des patients identifiés selon une grille d'attributs fixée à l'avance (statut sérologique, biopsie, atteintes systémiques, lymphome, Connectivite associée…).
_Avoid_: sous-phénotypage, clustering

**Profil de preuves**:
Ensemble des preuves d'un patient, rangées par Source, à partir duquel l'Identification est calculée.
_Avoid_: features, vecteur, dossier

### Sources

**Source**:
Famille de données, disjointe des autres, mobilisée pour l'Identification, la Caractérisation ou la comparaison : Diagnostics codés, Auto-anticorps, Biologie, Anatomopathologie, Tests de sécheresse, Médicaments, Actes.
_Avoid_: modalité, domaine (réservé au sens OMOP), table

**Diagnostics codés**:
Codes CIM-10 attachés aux séjours et venues du patient.
_Avoid_: diagnostics, PMSI

**Auto-anticorps**:
Résultats d'anticorps dirigés contre le soi : anti-SSA/Ro60, anti-Ro52, anti-SSB/La, AAN, facteur rhumatoïde.
_Avoid_: immunologie, sérologie

**Anti-SSA**:
Anticorps anti-SSA/Ro60, ou anti-SSA rendu sans distinction Ro52/Ro60 ; un anti-Ro52 isolé n'est pas un Anti-SSA.
_Avoid_: anti-Ro (ambigu)

**Biologie**:
Résultats biologiques hors Auto-anticorps : électrophorèse et IgG, complément, cryoglobulines, β2-microglobuline, chaînes légères libres, NFS.
_Avoid_: bilan immunologique, données immunologiques

**Anatomopathologie**:
Résultats de biopsie de glande salivaire (sialadénite, focus score, grade de Chisholm-Mason, lymphome).
_Avoid_: histologie, BGSA

**Tests de sécheresse**:
Résultats des Items ACR/EULAR fonctionnels (OSS, Schirmer, débit salivaire non stimulé), extraits des comptes rendus.
_Avoid_: tests fonctionnels, bilan de sécheresse

**Médicaments**:
Expositions médicamenteuses évocatrices ou liées à la SjD (pilocarpine, hydroxychloroquine…).

**Actes**:
Actes CCAM pertinents, dont la réalisation d'une biopsie de glande salivaire.

### Évaluation

**Comparateur CIM-10**:
Ensemble des patients porteurs d'un code CIM-10 de SjD, comparé aux patients identifiés par la Définition computable, dont il est indépendant ; ce n'est pas une référence.
_Avoid_: gold standard, vérité terrain, référence

**Concordance**:
Degré d'accord entre deux ensembles de patients (phénotype, Comparateur CIM-10, variantes) en l'absence de référence.

**Complémentarité**:
Mesure dans laquelle une Source repère des patients que les autres Sources ne repèrent pas.

**Robustesse**:
Stabilité des résultats du phénotype face aux choix méthodologiques, aux données manquantes et aux périodes.

**Reproductibilité**:
Obtention des mêmes résultats à code, données et vocabulaires identiques.

### Données synthétiques

**État réel**:
Statut SjD et attributs qu'un patient synthétique possède par construction, invisibles pour la Définition computable.
_Avoid_: vérité terrain, label, gold standard

**Processus d'observation**:
Mécanisme simulé qui transforme l'État réel en données OMOP observables (prescription d'un examen, saisie du résultat, codage, erreurs).
_Avoid_: bruit, simulation
