# Méthodologie M1 — préparation des observations

Statut : pipeline de préparation et comptages bruts. L'harmonisation et ses intervalles ne sont pas encore validés par M1. La baseline Django de démonstration est un traitement distinct.

## Sources et périmètre

Les entrées sont les fichiers pays Gabon fournis dans `data/raw/gabon`, accompagnés de `AttributesReadme.txt`. Le lot initial recense 48 CSV : 26 MODIS, 14 VIIRS S-NPP et 8 VIIRS NOAA-20 (préfixe archive `viirs-jpss1`). Les sommes de lignes sont respectivement 59 282, 147 745 et 85 562. Elles désignent des détections thermiques, pas des incendies distincts.

Ce lot utilise le périmètre des fichiers pays, sans effectuer de jointure avec un polygone. L'identifiant national GA est une étiquette de jeu de données, pas une preuve que le même ensemble de points est sélectionné par les frontières PostGIS de M2. Les résultats doivent être réconciliés avant comparaison des agrégats des deux systèmes.

## Audit des entrées

`pipeline.inventory` produit un manifeste des fichiers et de leurs SHA256, ainsi que des contrôles de schéma, dates/heures, coordonnées WGS84, domaines de confiance, nombres et doublons exacts. Le rapport ne modifie pas les entrées et ne constitue pas une validation complète de couverture d'observation.

## Principes de normalisation

- Conserver les dates d'acquisition en UTC et accepter les heures HHMM sans zéro initial en les normalisant explicitement.
- Préserver la plateforme : Terra et Aqua restent distincts ; S-NPP et NOAA-20 ne sont pas additionnés pour former une nouvelle série physique.
- Harmoniser les noms de colonnes d'export sans déclarer les températures de brillance de bandes différentes physiquement équivalentes.
- Conserver la confiance originale. Les catégories nominales des capteurs n'établissent pas une probabilité comparable entre instruments.
- Conserver les types thermiques, versions et indicateurs NRT ; aucune valeur absente ne devient implicitement type 0, confiance nominale ou jour.
- Relier chaque ligne au fichier, à sa ligne CSV et à son empreinte. Documenter la clé déterministe d'observation et la politique de doublons dans `m1-normalization.md`.
- Les valeurs invalides doivent provoquer un rejet explicite ou l'échec du traitement. Un résultat partiel ne doit pas être présenté comme complet.

## Agrégation mensuelle

Compter séparément source, satellite, mois UTC et politique de sélection. La vue « toutes détections » conserve les types d'entrée. Une sélection `type = 0`, lorsqu'elle est livrée, correspond à des candidats feux de végétation selon le produit ; elle n'est pas équivalente au masque statique Django et ne certifie pas la nature de chaque source.

La disponibilité des fichiers, le nombre de détections et la couverture d'observation sont trois informations différentes. Un mois sans ligne dans un fichier disponible peut avoir un comptage recensé nul, avec couverture d'observation inconnue. Un fichier attendu absent doit produire un statut d'entrée manquante et une valeur indisponible, pas un zéro.

Les premiers mois et premières années doivent être distingués : MODIS débute dans ce jeu le 1er novembre 2000, S-NPP le 20 janvier 2012 et NOAA-20 le 1er avril 2018. Une première année tronquée ne rend pas tous ses mois partiels. Les frontières de début sont explicites dans le protocole ; elles ne sont pas déduites de chaque première détection régionale. Aqua n'est pas attendu avant juillet 2002.

Les tableaux de préparation ne fabriquent aucune valeur harmonisée ni intervalle. Leur contrat d'export et leurs statuts sont décrits dans `m1-normalization.md`.

## Validation attendue avant harmonisation

1. Réconcilier les effectifs source → normalisation → agrégation et contrôler les empreintes d'entrée.
2. Définir la zone d'application et le filtre de chaque modèle ; ne pas généraliser une calibration nationale à un polygone libre sans évaluation.
3. Figer les traitements appris (notamment un masque de persistance) avant la période d'évaluation indépendante.
4. Séparer les rôles d'apprentissage, de sélection, de calibration des intervalles et de test final. Publier MAE, biais et comportement par saison et régime.
5. Vérifier la continuité entre plateformes et la disponibilité réelle des produits avant tout raccordement, notamment pour 2026.

Aucun coefficient ni gain du guide n'est automatiquement retenu dans le pipeline M1. Une méthode non concluante reste expérimentale et les séries brutes restent accessibles.

## Sources de référence

- `data/raw/gabon/AttributesReadme.txt`, documentation accompagnant les fichiers fournis.
- [NASA FIRMS — produits, versions et disponibilité](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- [NASA FIRMS — interruptions et problèmes connus](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).
- [NASA MODIS — historique des plateformes](https://modis-images.gsfc.nasa.gov/).

## Interface avec M2

Les sorties M1 résident dans `data/processed/`. Elles sont consommées par un futur import versionné côté M2 ; la présence d'un fichier ne signifie pas qu'il est déjà chargé en base. L'import devra conserver les statuts, la provenance, la politique de filtrage et la version du traitement, puis vérifier la concordance fichier → DB → API → export. Voir `HANDOFF.md` pour la responsabilité des composants.

## Masque statique et grille 0,25° (lot H3–H12)

`python -m pipeline.static_mask_audit` reproduit le masque de cellules M2 à 0,05° : origine de cellule par `FLOOR(coordonnée × 20)`, seuil de 20 points de type 2/3 ou détections S-NPP dans au moins 48 mois distincts. Le masque est rétrospectif, calculé sur tout l'archive disponible ; toutes les détections d'une cellule signalée sont identifiées, sans supprimer de ligne source. Les fichiers `static_mask_audit.json` et `static_mask_cells.csv` listent les cellules et leur exposition.

`python -m pipeline.grid_025` agrège par mois, source, satellite et cellule 0,25° et conserve quatre vues : détections brutes, type 0, type 0 hors des cellules candidates et toutes détections situées dans une cellule candidate. Les sorties `grid_025_monthly.csv`, `grid_025_monthly.json` et `manifest.json` contiennent les empreintes des entrées et sorties. Elles ne représentent pas encore une série d'harmonisation ni un filtre scientifiquement validé.

Sur l'archive M1 (2000–2025, 292 589 lignes), le masque signale 183 cellules sur 3 227 occupées ; 109 876 détections s'y trouvent, dont 52 023 de type 0 (22,20 % des 234 366 type 0). La grille 0,25° contient 41 957 lignes mois-source-satellite-cellule. Ces mesures portent sur les fichiers pays du Gabon sans vérification de géométrie administrative.
