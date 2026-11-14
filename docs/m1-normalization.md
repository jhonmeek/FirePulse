# M1 — normalisation et agrégations mensuelles

## Reproduction et fichiers

Depuis la racine du dépôt, avec Python standard (sans dépendance):

```sh
python -m pipeline.normalize --input data/raw/gabon --output data/processed/normalized
python -m pipeline.aggregate_monthly --input data/processed/normalized --output data/processed/monthly
```

La normalisation écrit un CSV par CSV source reconnu (`*_normalized.csv`), plus `manifest.json`. Les agrégats écrivent `monthly_counts.csv` et `manifest.json`. Le premier manifeste associe fichier d'entrée/sortie, SHA-256, nombres de lignes et doublons exacts, et l'empreinte SHA-256 du code normaliseur pour permettre de retracer le rebuild exact. Une ligne de sortie correspond à chaque ligne source; `observation_hash` sert à vérifier les répétitions, celles-ci ne sont pas supprimées. Un échec de lecture/validation survient avant remplacement de la sortie. Les données brutes ne sont jamais écrites.

Publication prévue: publier le manifeste normalisé et les sorties mensuelles (`monthly_counts.csv`, `calendar.json`, manifeste mensuel), pas les 48 fichiers normalisés annuels volumineux, qui restent locaux et reproductibles. Les CSV annuels se reconstruisent localement avec la commande et les empreintes source/code du manifeste. Les CSV d'entrée non reconnus ou les basenames en collision font échouer le lot.

## Contrat normalisé

`source` conserve MODIS et S-NPP et mappe JPSS-1 vers NOAA-20; `satellite` normalise en `Terra`, `Aqua`, `N` ou `N20`, tandis que `instrument_original` et `satellite_original` gardent les libellés source exacts. `brightness_mir`/`brightness_tir` sont des colonnes harmonisées de nom seulement, sans équivalence physique affirmée. Les catégories de confiance MODIS (seuils FIRMS 0–100 : <30, 30–<80, ≥80) sont étiquetées low/nominal/high; les lettres VIIRS L/N/H sont transcrites séparément vers ces trois étiquettes, sans prétendre à une équivalence probabiliste. La valeur source reste dans `confidence_raw`. Valeurs absentes restent vides. `is_nrt` n'est vrai que si le champ `version` contient `nrt` (insensible à la casse). `observation_hash` est le SHA-256 des champs source de la ligne, sans provenance; les hashes de fichier et lignes source sont aussi conservés.

Les timestamps sont UTC construits à partir de `acq_date` et `acq_time`; les heures sans zéro initial sont admises. Champs requis vides, type/daynight invalides, instrument/satellite incompatibles avec le produit, année incohérente, coordonnées hors WGS84, nombres non finis, date/heure invalides, colonnes requises manquantes et lignes mal formées font échouer le lot sans remplacer la sortie.

## Agrégat

Le périmètre régional est uniquement `GA` et `dataset_scope=country_file_unverified_geometry`: il reflète le fichier pays fourni, sans test point-dans-polygone. Le champ agrégé `satellite` reprend `Terra`, `Aqua`, `N` ou `N20`; `satellite_original` n'est pas un champ des agrégats. Les comptages par mois/source/satellite ne sont pas harmonisés. `count_type0_candidate` est une vue candidate; aucun masque spatial, calibration, filtre ou valeur harmonisée n'est appliqué. Dans `calendar.json`, les comptes sont des nombres JSON entiers ou `null`, et `harmonized_value` est toujours `null`; dans le CSV, `null` est rendu par un champ vide. Le calendrier dense `2000-11`–`2025-12` est spécifique à chaque source/satellite. Avant le début du protocole (MODIS/Terra 2000-11-01, Aqua 2002-07, S-NPP 2012-01-20, NOAA-20 2018-04-01), le compte est `null`/vide en CSV et le statut `not_available`. Une année produit absente donne `missing_input`; un fichier annuel présent sans détection dans un mois donne zéro et `no_detections_recorded`, couverture toujours inconnue. Seul janvier 2012 S-NPP porte `partial_period`; les mois initiaux MODIS/NOAA-20 ne le sont pas (années de démarrage partielles). La disponibilité d'Aqua commence en juillet 2002. La chronologie est fixe au protocole et ne découle pas des dates min/max observées.

## Calendrier, limites et contrat M2

Les sorties de ce lot décrivent les détections conservées et leur provenance, pas la fréquence d'observation, une couverture complète, un nombre d'incendies, ni une série comparable entre capteurs. Aucune calibration, suppression de doublons, masque de torchères, conversion physique, récupération de données 2026 ou import DB n'est inclus. Pour M2, les champs à consommer sont `region`, `dataset_scope`, `month`, `source`, `satellite_original`, `count_raw`, `count_type0_candidate`, `status` et `observation_coverage`; conserver les chaînes vides comme inconnues et ne pas les convertir en zéro. Vérifier le manifeste et les totaux avant chargement idempotent.

## Raccordement backend et validation du lot

Ne pas envoyer les CSV normalisés à `import_firms --data-dir` : cette commande M2 attend le schéma FIRMS brut, avec `acq_date` et `acq_time`. Le raccordement des sorties M1 nécessite l'adaptateur `--from-pipeline` annoncé dans `HANDOFF.md`, ou un import dédié. Le calendrier M1 est un contrat de préparation distinct du JSON d'API existant.

`monthly_counts.csv` contient des lignes par mois/source/satellite canonique. Les comptes JSON sont des entiers ou `null` ; en CSV, `null` est une cellule vide. `harmonized_value` reste indisponible. La sélection `count_type0_candidate` est un comptage des types 0 sans masque industriel : elle ne correspond pas au `filter_static=true` du backend existant.

Sur les 48 fichiers fournis : 292 589 lignes normalisées conservées, dont 234 366 étiquetées type 0. Le calendrier contient 1 208 lignes (302 mois × quatre plateformes), dont 844 avec détections recensées, une période partielle S-NPP en janvier 2012 et 363 lignes avant disponibilité. La couverture d'observation reste `unknown` dans tous les cas. L'année 2026 n'est pas intégrée à ce lot.

Les treize tests du dépôt passent après intégration du lot. Une vérification indépendante a rapproché chaque comptage mensuel et chaque compteur type 0 des CSV bruts, puis contrôlé les empreintes des entrées et sorties, les dates UTC, la provenance et les types JSON. Les tests d'intégration supplémentaires vérifient le refus d'un dossier de sortie non géré, la conservation d'une sortie publiée après entrée invalide et le déterminisme des régénérations avec alias satellite.

Les gros CSV d'observations normalisées restent locaux et reproductibles. Les deux manifestes et les petits CSV/JSON mensuels sont versionnés. Les données brutes et le backend ne sont pas modifiés.

## Références de domaine

Les noms de variables et produits sont ceux de `data/raw/gabon/AttributesReadme.txt` et des exports présents. Les seuils de confiance MODIS reprennent la documentation NASA FIRMS; ils constituent des classes descriptives, non une calibration entre capteurs. [NASA FIRMS — données et documentation](https://firms.modaps.eosdis.nasa.gov/).
