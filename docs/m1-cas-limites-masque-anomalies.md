# M1 — vérification des cas limites

## Masque de cellules candidates

Le test `tests/test_static_mask_thresholds.py` utilise des données synthétiques pour vérifier le seuil inclusif de 20 détections de type 2/3 ou 48 mois S-NPP distincts, ainsi que les coordonnées négatives et la non-répétition des mois. Il vérifie la règle de l'audit M1 ; il ne valide ni les seuils sur le plan scientifique, ni l'équivalence spatiale exacte avec PostGIS, ni la classification de torchères.

## Médiane historique nulle (B = 0)

Dans le calcul existant des anomalies, lorsque la médiane B est nulle et la valeur H disponible, le pourcentage est indéfini (`null`) et l'écart absolu est H − B. Exemple synthétique : H = 30, B = 0 donne un écart de 30, pas un pourcentage. Cet exemple n'est pas une observation réelle 2026.

Revue statique : le classement `/anomalies/` exclut les pourcentages `null` ; un écart absolu peut donc apparaître dans le calendrier sans figurer dans ce classement. Les valeurs déjà fournies lors de l'import peuvent être conservées : vérifier leur cohérence relève de M2. L'interface M3 doit rendre visible la différence entre « pourcentage non défini » et « aucune anomalie ».

La présence d'un zéro dans une série ne prouve pas que l'observation satellitaire était complète. Le comportement en base active et le rendu à l'écran n'ont pas été vérifiés dans cette revue ; les tests backend spécifiques B = 0 et la décision d'affichage restent à coordonner avec M2 et M3.

## Audit des comptes Terra 2000–2002

`python -m pipeline.terra_early_audit --raw-dir <csv-bruts> --monthly <monthly_counts.csv> --output <nouveau-rapport.json>` rapproche les comptes Terra bruts et de type 0, mois par mois, de novembre 2000 à décembre 2002. Le rapport comprend les SHA-256 des entrées et signale les écarts ; la sortie ne peut pas écraser un fichier existant. Un code de sortie 1 indique des écarts, 2 une erreur d'entrée ou d'écriture.

Sur les fichiers locaux examinés : 2 599 détections Terra, dont 1 546 de type 0, et aucun écart avec les 26 mois du calendrier M1. Les mois jusqu'en juin 2002 correspondent à la période Terra seule du protocole M2 ; le second semestre 2002 est inclus uniquement pour contrôler les comptes Terra, alors qu'Aqua est également disponible. Il s'agit d'une vérification de cohérence des comptes pays, ni d'une validation de l'harmonisation ni d'une preuve de couverture ou d'appartenance géographique.
