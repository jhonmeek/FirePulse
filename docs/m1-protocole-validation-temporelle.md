# Proposition M1 — validation temporelle de l'harmonisation

Statut : **protocole à examiner avec M2**, aucun nouveau score ni intervalle n'est validé par ce document. La baseline existante reste disponible pour la démonstration avec son statut en revue.

## Question et limites

Estimer, pour un même mois et périmètre, le nombre de détections S-NPP à partir de MODIS, puis mesurer l'erreur et la couverture d'un intervalle de prédiction. Ce sont des détections recensées, non des incendies distincts. Les capteurs diffèrent et les nuages, passages et produits affectent leurs observations ([NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/alerts/notes.php)). Les données fournies ne permettent pas d'estimer directement la couverture d'observation.

## Découpage proposé pour une nouvelle expérience

| Rôle | Période | Fonction |
|---|---|---|
| Apprentissage | février 2012–décembre 2016 | Ajuster les paramètres candidats et construire, si applicable, le masque à partir de cette période ou d'une source indépendante figée. |
| Sélection | 2017–2019 | Comparer les candidats et figer modèle, transformation, filtre et règles d'éligibilité. |
| Calibration intervalle | 2020–2022 | Calculer le quantile des résidus du modèle figé ; ne pas réajuster le modèle sur ces mois. |
| Évaluation | 2023–2025 | Calculer métriques et couverture après gel de tous les choix. |

Ces années 2020–2025 ont déjà servi au benchmark et à la calibration de la baseline, et ses résultats ont été examinés. Le bloc 2023–2025 est donc un **test de la nouvelle procédure**, pas un jeu final aveugle au projet. Une future période réellement inédite, avec données de référence compatibles et disponibilité vérifiée, est nécessaire pour une évaluation finale indépendante. Ne pas présenter cette proposition comme une garantie de couverture à 80 % : les dépendances temporelles et changements de régime peuvent invalider l'échangeabilité supposée par les garanties conformes classiques ([Prinzhorn et al., 2024](https://proceedings.mlr.press/v230/prinzhorn24a.html)).

## Exécution et critères de rapport

1. Figer fichiers et versions, frontière, requête de sélection et empreintes ; comparer à l'export PostGIS M2. Identifier explicitement les mois absents, partiels ou à couverture inconnue ; ne pas les transformer en zéros sans preuve de disponibilité.
2. Pour le filtrage, publier la variante sans masque et une variante avec masque construit uniquement à partir de la période permise. Le masque rétrospectif 2000–2025 de la baseline utilise des années futures et ne convient pas comme masque d'évaluation indépendante.
3. Ajuster et comparer les modèles sur les mêmes mois éligibles. Après sélection, figer tous les paramètres et calculer le quantile sur le seul bloc de calibration. Décrire les exclusions et la taille de chaque échantillon.
4. Sur le bloc d'évaluation : publier MAE, RMSE, biais, R² lorsque défini, couverture et largeur des intervalles, nombre de mois, résultats par saison et filtre. Rendre explicite l'incertitude liée au faible nombre de mois et ne pas sélectionner le modèle sur ce bloc après consultation.
5. Le pont NOAA-20/S-NPP doit avoir une période d'ajustement et une période d'évaluation distinctes, avec recouvrement et disponibilité réels documentés. L'existence de fichiers jusqu'à 2025 ne démontre pas la disponibilité des données NRT 2026 ni une validation pour les zones personnalisées.

M1 définit et évalue le protocole dans `pipeline/` et `data/processed/` ; M2 reste responsable du calcul et de l'import dans Django/PostGIS ; M3 est responsable de l'affichage de l'état de validation. Les périodes proposées et leur faisabilité doivent être revues conjointement avant de qualifier les résultats.
