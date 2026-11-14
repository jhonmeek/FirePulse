# FirePulse — M1 Data & Science

Pipeline scientifique pour l'analyse et l'harmonisation des détections de points chauds MODIS et VIIRS au Gabon.

## État du développement

Le premier lot implémente l'inventaire reproductible et les contrôles de qualité des CSV présents dans `data/raw/gabon`. Les données brutes restent inchangées. Les coefficients et benchmarks du guide v2 ne sont pas encore validés par ce pipeline.

## Prérequis

Python 3.10 ou plus récent. Le lot d'inventaire utilise uniquement la bibliothèque standard, sans installation de dépendance ni clé NASA.

Depuis la racine du dépôt :

```powershell
python -m unittest discover -s tests -v
python -m pipeline.inventory --input data/raw/gabon --output data/processed/audit
```

Le manifeste et le rapport qualité JSON sont des résultats d'audit, pas des séries harmonisées utilisables comme résultats scientifiques finaux. Voir `docs/m1-data-audit.md` pour les contrôles, formats, limites et instructions de reproduction.

## Sources et limites

- Données fournies dans le dépôt, accompagnées de `data/raw/gabon/AttributesReadme.txt`.
- [NASA FIRMS — documentation et ressources](https://firms.modaps.eosdis.nasa.gov/).
- [NASA FIRMS — différences entre produits et disponibilité](https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html).
- [NASA FIRMS — anomalies connues et interruptions](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).

La présence de détections ne permet pas de déduire une couverture d'observation complète. Le fichier pays ne remplace pas une validation des frontières géographiques. Un point chaud n'est pas nécessairement un incendie distinct.

## Contributions M1

Travail sur `m1/data-science`, contrôles et revue des changements avant proposition d'intégration dans `main`. Les artefacts d'audit sont séparés des fichiers bruts. Les étapes suivantes sont la normalisation, les agrégations mensuelles et l'évaluation de l'harmonisation.
