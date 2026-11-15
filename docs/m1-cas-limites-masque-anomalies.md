# M1 — vérification des cas limites

## Masque de cellules candidates

Le test `tests/test_static_mask_thresholds.py` utilise des données synthétiques pour vérifier le seuil inclusif de 20 détections de type 2/3 ou 48 mois S-NPP distincts, ainsi que les coordonnées négatives et la non-répétition des mois. Il vérifie la règle de l'audit M1 ; il ne valide ni les seuils sur le plan scientifique, ni l'équivalence spatiale exacte avec PostGIS, ni la classification de torchères.

## Médiane historique nulle (B = 0)

Dans le calcul existant des anomalies, lorsque la médiane B est nulle et la valeur H disponible, le pourcentage est indéfini (`null`) et l'écart absolu est H − B. Exemple synthétique : H = 30, B = 0 donne un écart de 30, pas un pourcentage. Cet exemple n'est pas une observation réelle 2026.

Revue statique : le classement `/anomalies/` exclut les pourcentages `null` ; un écart absolu peut donc apparaître dans le calendrier sans figurer dans ce classement. Les valeurs déjà fournies lors de l'import peuvent être conservées : vérifier leur cohérence relève de M2. L'interface M3 doit rendre visible la différence entre « pourcentage non défini » et « aucune anomalie ».

La présence d'un zéro dans une série ne prouve pas que l'observation satellitaire était complète. Le comportement en base active et le rendu à l'écran n'ont pas été vérifiés dans cette revue ; les tests backend spécifiques B = 0 et la décision d'affichage restent à coordonner avec M2 et M3.
