# M1 — disponibilité FIRMS 2026 et proposition de gestion des extractions

État consulté via l'API officielle FIRMS `data_availability` le 15 novembre 2026. Les dates sont susceptibles d'évoluer lors des retraitements ; elles indiquent une disponibilité globale déclarée, pas une preuve de couverture ni d'absence de données manquantes au Gabon.

| Produit | Début renvoyé | Fin renvoyée |
|---|---|---|
| VIIRS NOAA-20 NRT | 2026-08-01 | 2026-11-14 |
| VIIRS NOAA-20 standard | 2018-04-01 | 2026-07-31 |
| VIIRS S-NPP NRT | 2026-08-01 | 2026-11-02 |
| VIIRS S-NPP standard | 2012-01-20 | 2026-07-31 |

NASA précise que les observations NRT sont progressivement remplacées dans les archives par les produits standard ; consulter les dates à chaque acquisition et conserver la réponse datée. Sources : [disponibilité API FIRMS](https://firms.modaps.eosdis.nasa.gov/api/data_availability/), [archive FIRMS](https://firms.modaps.eosdis.nasa.gov/download/).

L'extraction M1 GA préparée le 14 novembre concerne une seule journée NOAA-20 NRT : 52 détections dans le rectangle API, dont 40 strictement à l'intérieur de la frontière locale GA. Le champ NASA `type` est absent et reste indisponible ; ces 40 points ne sont ni un total mensuel, ni un nombre d'incendies distincts, ni une démonstration de couverture. Le fichier source, la frontière, les sorties et leurs empreintes sont conservés localement dans l'espace de travail ; aucun import DB n'a été effectué par M1.

Deux extractions supplémentaires couvrent les 5–9 et 10–14 novembre : respectivement 56 et 122 détections dans le rectangle, dont 32 et 65 strictement à l'intérieur de la frontière locale. Ces fenêtres sont distinctes ; celle du 10–14 recouvre intégralement la journée du 14 déjà citée, qu'il ne faut donc pas additionner une seconde fois. Les extractions ne représentent pas l'ensemble de 2026 et leur couverture reste inconnue.

## Acquisition reproductible

`python -m pipeline.firms_area_acquire --product VIIRS_NOAA20_NRT --start 2026-11-05 --days 5 --output-dir <dossier>` télécharge une fenêtre de 1 à 5 jours depuis l'API Area et produit un CSV brut accompagné d'un manifeste SHA-256, sans écraser les fichiers existants. La variable d'environnement locale `FIRMS_MAP_KEY` est nécessaire ; elle ne doit pas être copiée dans les commandes partagées ni les journaux. L'API NASA place la clé dans l'URL de requête : les proxys ou outils de diagnostic réseau peuvent donc la voir. Le produit est celui demandé, sans vérification indépendante de son identité. Le rectangle inclut les pays voisins : la sélection spatiale Gabon et la vérification de provenance sont des étapes distinctes. Le filtre spatial utilisé pour ces extractions est local et ne fait pas partie de cette commande.

## Proposition à valider avec M2

1. Pour chaque requête : enregistrer produit, capteur, niveau déclaré, dates demandées et renvoyées, date de récupération, emprise, SHA-256 du fichier original, frontière et version de traitement. Ne jamais conserver la MAP_KEY dans les manifestes, les URL partagées ou les journaux.
2. Garder les lignes d'origine et distinguer lignes reçues, copies de fichier et observations dédupliquées. `(source_sha256, source_line)` est un identifiant de ligne, pas la preuve d'une détection physique unique.
3. Identifier les fichiers strictement identiques par leur SHA-256. Des fichiers différents peuvent se chevaucher ; signaler les doublons candidats avec leurs références et ne pas supprimer automatiquement des observations proches sans règle validée par produit.
4. Conserver SP et NRT distincts et vérifier leur provenance via l'API et les métadonnées du téléchargement. Ne pas additionner automatiquement des extractions chevauchantes. Avant tout remplacement NRT par SP, définir avec M2 une stratégie versionnée et réversible, conserver les références aux deux lots et invalider les agrégats concernés.
5. Les périodes non demandées, les mois partiels et les périodes sans couverture vérifiée restent indisponibles ou partiels ; ne pas les convertir en zéros. Un type manquant reste inconnu et ne doit pas être converti en type 0.

Les outils M1 `nrt_observations` et `nrt_calendar` décrivent actuellement une seule extraction ; ils n'implémentent ni fusion multiextraits, ni suppression de doublons, ni décision SP/NRT. M2 porte la base, les migrations, l'import et l'API ; M3 porte l'affichage des statuts. Ces règles sont une proposition, non une validation de production ni une modification de leurs composants.
