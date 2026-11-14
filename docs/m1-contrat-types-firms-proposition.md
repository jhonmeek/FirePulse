# Proposition M1 — séries par type FIRMS pour M2 et M3

Statut : proposition à revoir avec M2 et M3, avec un premier agrégat M1 ; aucune route API ni classification nouvelle n'est livrée. Un point chaud est une détection thermique, pas nécessairement un incendie distinct.

## Catégories exclusives pour les produits qui fournissent `type`

| Code source | Libellé de présentation | Limite |
|---|---|---|
| 0 | Feu de végétation présumé | Classification du produit, non confirmation au sol. |
| 1 | Activité volcanique présumée | À confronter à une référence volcanologique si nécessaire. |
| 2 | Autre source thermique terrestre statique | Ne signifie pas automatiquement une torchère. |
| 3 | Détection offshore ou sur l'eau | Ne signifie pas automatiquement une torchère. |
| absent | Type indisponible | Conserver l'indisponibilité ; ne pas remplacer par 0. |

La NASA décrit ces types pour les produits standards [MODIS](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf) et [VIIRS](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf). Certains flux NRT ne fournissent pas cet attribut : vérifier le produit et sa version avant de l'utiliser.

## Contrat de préparation proposé

Une ligne représente `(region, dataset_scope, month, source, satellite, type_nasa)` ; `detection_count` compte les lignes source sans dédupliquer ni harmoniser. Conserver `status`, `observation_coverage`, les versions et le manifeste d'empreintes. Somme des catégories = nombre brut pour le même périmètre/mois/capteur ; le compte indisponible de type est distinct d'un mois sans données. Une entrée annuelle absente ou un capteur indisponible donne une valeur indisponible, pas zéro. Une absence de détection recensée dans un fichier présent ne prouve pas l'absence de feu.

La persistance constitue un indicateur séparé, `in_persistent_cell`, dont les valeurs possibles sont vrai, faux ou inconnue. Elle peut chevaucher tous les types et ne doit pas être ajoutée aux catégories exclusives dans une même somme. Préciser la période de construction du masque, sa grille, ses seuils et ses empreintes. Le masque rétrospectif 2000–2025 n'est pas un masque figé avant le test 2023–2025.

## Limites et coordination

- Les données historiques M1 actuelles exigent `hotspot_type` dans le normaliseur ; elles ne permettent pas encore d'ingérer une ligne NRT sans type. Adapter séparément l'ingestion future et ses tests avant de prétendre gérer ce cas.
- Les comptes de types sont bruts et ne constituent pas les séries harmonisées par capteur. Les produits FIRMS, leurs périodes et versions peuvent différer ; la couverture reste inconnue.
- M1 définit et vérifie les agrégats dans `pipeline/` et `data/processed/` ; M2 définit l'import et le contrat API ; M3 présente barres empilées par type et couche de persistance séparée. La géométrie du fichier pays M1 diffère du filtre PostGIS M2 ; comparer des périmètres équivalents.
- Ne pas promettre une identification de torchère ou une confiance chiffrée sans source externe datée, contrôle géospatial et évaluation indépendante. Aucun catalogue externe n'est intégré par cette proposition.

## Premier agrégat M1

`python -m pipeline.monthly_types --output data/processed/monthly-types/monthly-types.json` vérifie les empreintes du calendrier, du manifeste normalisé et des CSV, puis rapproche les comptes par type des comptes mensuels existants. L'exécution sur l'archive fournie réconcilie 292 589 détections et produit 1 208 lignes mois/plateforme. Les cinq catégories sont des champs exclusifs dans `type_counts` ; elles sont toutes `null` si le compte brut est indisponible. La persistance est `not_evaluated` dans ce premier résultat : aucune estimation par type/cellule n'est encore publiée. La commande refuse de remplacer un fichier existant ; choisir un autre chemin pour une nouvelle exécution.

La structure exacte de l'API et des graphiques reste à décider avec M2/M3. Le normaliseur actuel rejette encore les entrées NRT sans `type` ; la catégorie `unavailable` du contrat et de l'agrégateur ne signifie pas que ces entrées peuvent déjà être importées.

## Précontrôle d'un fichier récent

`python -m pipeline.nrt_preflight --input chemin/fichier.csv --output chemin/rapport.json` inspecte un CSV fourni localement : empreinte, dates, coordonnées, heures, versions et présence du champ type. Un type absent ou vide est compté `type_unavailable`, sans le transformer en type 0 ; un code hors domaine est signalé invalide. La commande refuse de remplacer un rapport existant et renvoie un code d'échec si des anomalies sont détectées.

Ce précontrôle ne télécharge ni ne normalise les observations, ne valide ni frontière ni couverture et ne prouve pas à lui seul le niveau de traitement NRT. Les cas NRT ont été vérifiés sur des données synthétiques ; aucune acquisition 2026 réelle n'est incluse.

`python -m pipeline.nrt_ingest --input chemin/fichier.csv --product VIIRS_NOAA20_NRT --output chemin/preparation.json` constitue une préparation séparée pour 2026 : elle refuse les lignes invalides ou hors 2026 et compte par mois et type, avec `unavailable` pour un type absent. Le produit est déclaré par l'opérateur et marqué non vérifié ; les mois absents restent inconnus. Ce premier adaptateur n'écrit pas de lignes normalisées individuelles, ne met pas à jour le calendrier historique, ne remplace pas l'import PostGIS et ne prouve pas la couverture. La compatibilité avec un fichier NRT réel et son raccordement complet restent à vérifier.

`python -m pipeline.nrt_observations --input chemin/fichier.csv --product VIIRS_NOAA20_NRT --output chemin/observations.json` prépare séparément chaque observation 2026 et conserve ses champs originaux, numéro de ligne et SHA-256 du CSV. L'heure est normalisée en UTC, le type NASA manquant est `null` et son statut `unavailable`. La commande vérifie la cohérence du capteur déclaré, les dates, coordonnées, valeurs numériques optionnelles et catégories ; elle ne remplace pas un fichier existant. Le produit déclaré reste marqué non vérifié ; l'absence de doublons, la couverture, la classification et l'import en base ne sont pas garantis. Les 40 points NOAA-20 NRT du 14 novembre 2026 filtrés localement dans GA ont été préparés ; ils proviennent d'une seule journée et ne constituent pas un historique 2026 complet. Le normaliseur historique et le calendrier 2000–2025 ne sont pas modifiés.
