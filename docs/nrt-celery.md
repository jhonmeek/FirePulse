# Acquisition FIRMS quasi temps réel

Le flux périodique est désactivé par défaut. Pour l'activer localement, configurer `FIRMS_MAP_KEY` et `FIRMS_NRT_ENABLED=true` dans `.env`, puis lancer `docker compose --profile nrt up -d --build`. Le planificateur Celery Beat soumet la tâche selon `FIRMS_NRT_INTERVAL_SECONDS` (3600 s par défaut).

Le worker demande une fenêtre glissante NOAA-20 NRT de deux jours UTC par défaut (`FIRMS_NRT_LOOKBACK_DAYS`, entre 1 et 5), conserve la réponse brute dans un dossier horodaté de `data/nrt`, puis crée un CSV dérivé limité aux points strictement dans la frontière GA. Seul ce CSV est transmis à `import_firms`. Le manifeste dérivé garde les empreintes du CSV brut et du CSV filtré. Une réponse sans point dans GA est conservée comme acquisition, sans import.

L'import existant déduplique les fichiers par SHA-256 et les observations par hash. Un passage avec un fichier déjà connu ne régénère ni masque ni grille. Un champ FIRMS `type` absent reste inconnu (`null`) ; il n'est pas assimilé au type 0. Les données brutes et manifestes restent disponibles pour audit. Des versions NRT révisées peuvent encore produire des observations distinctes si le champ `version` change ; la réconciliation NRT vers produit standard doit être définie avant de prétendre à une série scientifique définitive.

Commandes de suivi :

```sh
docker compose --profile nrt ps
docker compose --profile nrt logs -f celery-worker celery-beat
```

Le flux ne garantit pas une détection à chaque exécution : disponibilité/coverage restent inconnues, les données NRT peuvent être révisées et le polygone d'acquisition comprend des pays voisins. Le produit est une requête NOAA-20 NRT déclarée, non une vérification indépendante. Une anomalie thermique n'établit pas sa cause. L'import régénère le masque statique et la grille par la commande backend existante.

Ne pas activer ce flux en production sans configurer les secrets via le gestionnaire de secrets du déploiement, dimensionner le volume `data/nrt`, définir une politique de rétention et surveiller les logs/retards Beat. La clé est transmise à l'API FIRMS dans son URL ; limiter l'accès aux journaux et aux traces réseau.
