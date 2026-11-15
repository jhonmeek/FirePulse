# Acquisition FIRMS quasi temps réel

Le flux périodique est désactivé par défaut. Pour l'activer localement, configurer `FIRMS_MAP_KEY` et `FIRMS_NRT_ENABLED=true` dans `.env`, puis lancer `docker compose --profile nrt up -d --build`. Le planificateur Celery Beat soumet la tâche selon `FIRMS_NRT_INTERVAL_SECONDS` (3600 s par défaut).

Le worker demande une fenêtre glissante NOAA-20 NRT de deux jours UTC par défaut (`FIRMS_NRT_LOOKBACK_DAYS`, entre 1 et 5), conserve la réponse brute dans un dossier horodaté de `data/nrt`, puis crée un CSV dérivé limité aux points strictement dans la frontière GA. Seul ce CSV est transmis à `import_firms`. Le manifeste dérivé garde les empreintes du CSV brut et du CSV filtré. Une réponse sans point dans GA est conservée comme acquisition, sans import.

L'import déduplique les fichiers par SHA-256 et les observations strictement identiques par hash. Un passage avec un fichier déjà connu ne régénère ni masque ni grille. Pour les lignes NRT déjà enregistrées, une seule observation contribue aux masques, grilles, séries mensuelles et sorties de points lorsque `source`, `satellite`, minute UTC et latitude/longitude arrondies à 5 décimales sont identiques : la première importée (plus petit identifiant) gagne. Les autres lignes et leurs lots restent en base pour audit ; les fichiers bruts et manifestes sont conservés. La migration applique cette règle aux lignes NRT historiques, sans modifier les observations SP. `--force` reconstruit les dérivés sans supprimer un lot déjà connu. Un champ FIRMS `type` absent reste inconnu (`null`) ; il n'est pas assimilé au type 0. Cette clé exacte est une règle opérationnelle de comptage, pas une preuve qu'une détection est un feu distinct ; elle ne rapproche pas les points déplacés, les heures corrigées, ni NRT et SP. La réconciliation NRT vers produit standard reste à définir avec M1/M2 avant de prétendre à une série scientifique définitive.

Pour M1 : documenter les changements de coordonnées ou d'heure entre extractions, ainsi que les versions et la couverture effective ; la clé ci-dessus ne les résout pas. Pour M2 : définir séparément une règle versionnée et réversible de priorité SP/NRT et de recalcul des séries avant toute comparaison scientifique. Aucune ligne SP historique n'est supprimée par cette correction.

Cette limite suit la documentation officielle [NASA FIRMS sur les archives](https://firms.modaps.eosdis.nasa.gov/download/) et [sur les produits de l'API](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html) : les données NRT peuvent être remplacées par des données standard destinées aux analyses scientifiques.

**Visibilité API des observations sans `type` :** elles restent consultables dans les points bruts (`/api/v1/hotspots/?mode=points&region=GA&month=2026-11&filter_static=false`) avec `hotspot_type: null`, ainsi que dans l'export de points (`/api/v1/export/?dataset=points&region=GA&month=2026-11&filter_static=false`) avec une colonne `hotspot_type` vide. Avec `filter_static=true` (valeur par défaut), ces deux réponses les excluent : seules les observations de `hotspot_type=0` **et** `is_static_masked=false` sont retenues. La même règle s'applique aux agrégats mensuels filtrés ; les agrégats `filter_static=false` comptent les observations retenues après la déduplication décrite ci-dessus, y compris celles de type inconnu. Le type inconnu n'est donc ni déclaré feu de végétation ni perdu des données brutes.

Commandes de suivi :

```sh
docker compose --profile nrt ps
docker compose --profile nrt logs -f celery-worker celery-beat
```

Le flux ne garantit pas une détection à chaque exécution : disponibilité/coverage restent inconnues, les données NRT peuvent être révisées et le polygone d'acquisition comprend des pays voisins. Le produit est une requête NOAA-20 NRT déclarée, non une vérification indépendante. Une anomalie thermique n'établit pas sa cause. L'import régénère le masque statique et la grille par la commande backend existante.

Ne pas activer ce flux en production sans configurer les secrets via le gestionnaire de secrets du déploiement, dimensionner le volume `data/nrt`, définir une politique de rétention et surveiller les logs/retards Beat. La clé est transmise à l'API FIRMS dans son URL ; limiter l'accès aux journaux et aux traces réseau.
