# Validation locale FIRMS NRT — 15 novembre 2026

## Acquisition réelle

- Source demandée : NASA FIRMS area API, `VIIRS_NOAA20_NRT`.
- Fenêtre demandée : 14–15 novembre 2026 UTC ; bbox `[8, -4, 15, 3]`.
- Résultat brut : 64 lignes, dont 42 strictement dans la géométrie `GA` de la base locale.
- Le manifeste brut et le manifeste du CSV dérivé sont conservés sous `data/nrt/manual-validation-20261115/`. Les deux empreintes SHA-256 ont été recalculées et correspondent aux manifestes.
- Le CSV brut ne contient pas de colonne `type`. Les observations correspondantes doivent rester de type inconnu (`null`), sans classification de feu de végétation.

## Limites de cette vérification

La réponse du service n'apporte pas de preuve indépendante du produit : le manifeste indique `requested_not_independently_verified`. La couverture d'observation demeure inconnue. La bbox contient des points hors Gabon ; seuls les 42 points du CSV dérivé respectent le filtre spatial strict.

Cette vérification a écrit des fichiers locaux ignorés par Git et lu la géométrie GA en base. Elle **n'a pas importé les 42 observations dans la base active** : le backend local et le worker proviennent actuellement de deux worktrees différents, et la migration ainsi que la priorité NRT/SP attendent la revue M2. Les tests automatisés d'import utilisent une réponse FIRMS simulée et une base PostGIS de test.

## Validation PostGIS et API isolée

Une base distincte `firepulse_nrt_validation` a été créée sur le PostGIS local, migrée jusqu'à `observations.0004_sp_priority`, puis alimentée avec les 10 géométries régionales de la base active. Le CSV dérivé réel y a produit 42 observations NRT, toutes de type inconnu, et 42 contributions à la grille brute NOAA-20 ; la grille filtrée en compte 0. La répétition du même import n'a ajouté aucun fichier ni observation. Les réponses API sur cette base donnent 42 points pour `recent-unknown-detections` et pour `hotspots` en `filter_static=false`, contre 0 en `filter_static=true`. La base active conserve 0 observation 2026 à la date du contrôle.

Ce résultat prouve la cohérence locale acquisition → filtre GA → import → grille → API pour cette extraction. Il ne prouve ni la couverture satellite, ni la classification des points, ni la correspondance future avec le produit SP. La base de validation est isolée du backend de l'application active.

## Suite M1/M2

1. M2 relit la PR #32, la migration `0003_nrt_counting` et la règle de priorité NRT/SP.
2. Après fusion et migration sur un stack cohérent, répéter la comparaison des comptes et des exports dans l'application active avant activation du planificateur.
3. Documenter la provenance du produit et la couverture avant toute interprétation scientifique des absences ou des tendances.
