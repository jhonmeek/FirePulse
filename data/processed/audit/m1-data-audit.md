# M1 n°1 — Inventaire et qualité

Fichiers CSV : **48** · lignes : **292589**

## Résumé par produit

| Produit | Fichiers | Lignes |
|---|---:|---:|
| modis | 26 | 59282 |
| viirs-jpss1 | 8 | 85562 |
| viirs-snpp | 14 | 147745 |

## Points d’interprétation

- Les mois absents sont `unknown` : ils ne prouvent ni couverture réelle ni zéro détection.
- Sans polygone, les bornes WGS84 ne prouvent pas l’appartenance au Gabon ni le respect de ses frontières.
- Les schémas s’appuient sur les colonnes des fichiers et `AttributesReadme.txt` fourni avec les données. Une anomalie de domaine est signalée, jamais corrigée.
- L’avis NASA FIRMS du 15 juin 2025 décrit un défaut de traitement VIIRS Vxx14IMGML Collection 2 (types 0/2, versions de traitement 1/2, corrigé par version 3). Cet audit ne peut pas déterminer les lignes affectées et ne reclassifie rien : https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html
- Aucun benchmark n’est revendiqué comme validé.

Détails déterministes : `data_manifest.json` et `quality_report.json`. Aucun horodatage volatile ni chemin absolu n’est enregistré.
