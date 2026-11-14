# Lot M1 n°1 — Inventaire et qualité

Commande reproductible depuis la racine :

```powershell
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
```

Le pipeline standard-library produit `data_manifest.json`, `quality_report.json` et un résumé Markdown. Le manifeste inventorie les chemins relatifs, tailles, SHA256, schémas, effectifs, dates, mois observés, satellites, versions et types. Le rapport signale notamment les colonnes requises absentes/vides selon le produit, lignes CSV irrégulières/erreurs de lecture, dates et heures invalides ou non paddées, coordonnées hors bornes/non finies, valeurs numériques/domaines inhabituels, doublons et divergences année fichier/date. Les valeurs source sont conservées.

Les noms de colonnes sont comparés aux colonnes effectivement présentes et aux attributs FIRMS documentés par le `AttributesReadme.txt` livré localement. Les champs numériques requis sont `brightness`, `bright_t31`, `scan`, `track`, `frp` pour MODIS, et `bright_ti4`, `bright_ti5`, `scan`, `track`, `frp` pour VIIRS. Les domaines de confiance sont évalués par capteur : MODIS numérique 0–100; VIIRS `l`, `n` ou `h`. Une valeur hors liste est rapportée comme anomalie sans réécriture. La distinction version/collection standard (SP) et near-real-time (NRT) doit être interprétée à partir des métadonnées FIRMS et des versions présentes, sans les déduire des seuls noms de fichiers.

Le README NASA indique la projection géographique WGS84. L’absence de polygone empêche toute validation d’appartenance au Gabon ou des frontières; seules les bornes générales latitude/longitude sont contrôlées. Un mois non observé est `unknown`, jamais une preuve de couverture complète ni un zéro de détection.

NASA FIRMS a documenté le 15 juin 2025 un problème de traitement de certains produits VIIRS Vxx14IMGML Collection 2 : types 0/2 affectés par les versions de traitement 1/2 et corrigés par reprocessing en version 3. Cette note est une limite à vérifier dans les métadonnées; l’audit n’établit pas les lignes concernées et ne reclassifie aucune valeur. Cela ne constitue pas une affirmation sur MODIS. Source primaire : [NASA FIRMS outage notice](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

Les sorties JSON sont triées et sans date d’exécution ni chemin absolu. Les métriques sont des contrôles exploratoires reproductibles, pas des benchmarks validés ni une validation scientifique des observations.

## Résultats du lot initial

Exécution du 14 novembre 2026 : 48 CSV et 292 589 lignes, dont 59 282 MODIS, 147 745 S-NPP et 85 562 NOAA-20. Les totaux sont confirmés par une lecture indépendante des CSV. Aucune colonne requise absente, valeur requise vide, ligne irrégulière, date/heure invalide, valeur numérique invalide/non finie, coordonnée hors bornes, valeur de confiance/type/jour-nuit hors domaine, divergence d'année ni doublon exact détecté par ces contrôles. Ces résultats ne constituent pas une validation de couverture, de classification des feux ou de calibration.

Les empreintes SHA256 des 48 fichiers sont identiques avant et après l'exécution. Les sorties incluent les champs de traçabilité sans modifier les sources.

Vérification : `python -m unittest discover -s tests -v` — quatre tests réussis. Ils couvrent entrées absentes/vides, schémas par produit, confiance, doublons intra/inter-fichiers, valeurs non finies, heures non paddées, année incohérente, lecture irrégulière/erreur de décodage, protection du dossier brut et stabilité des sorties sur des jeux synthétiques. Le CLI a aussi été relancé sur les fichiers réels et les résultats ont été rapprochés des comptages indépendants. Ce lot utilise uniquement la bibliothèque standard Python.
