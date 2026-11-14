# Limites scientifiques et techniques M1

## Ce que les données permettent d'affirmer

Les fichiers contiennent des détections de points chauds observées par des satellites. Les comptes ne mesurent ni un nombre d'incendies distincts, ni une surface brûlée, ni une mesure exhaustive de l'activité au sol. Une absence de détection n'est pas une preuve d'absence de feu.

## Couverture et géographie

- Les CSV de détections et leurs empreintes ne suffisent pas à mesurer tous les passages exploitables, les nuages ou les pertes de données. La couverture d'observation reste inconnue dans les agrégats M1 de préparation.
- Les archives initiales s'arrêtent à 2025. Aucune donnée 2026 n'est ajoutée implicitement, et aucun comptage récent n'est extrapolé pour remplir cette année.
- La sélection nationale M1 reprend le fichier pays fourni. Le découpage par provinces ou polygones personnalisés demande des frontières versionnées et une règle de sélection spatiale ; il n'est pas validé par ce lot.
- Une cellule préagrégée intersectant un polygone ne permet pas de connaître exactement le nombre de points dans la portion intersectée.

## Produits et filtrage

- Les résolutions, bandes et algorithmes diffèrent entre MODIS et VIIRS. Renommer des colonnes ne corrige pas ces différences.
- Les niveaux de confiance originaux sont conservés. Un niveau « nominal » n'est pas une probabilité identique pour les différents capteurs.
- Le type 0 signifie une classification du produit, pas une validation terrain. Les sources persistantes ne sont pas toutes des torchères, et un masque spatial peut exclure des feux de végétation voisins.
- Un avis FIRMS du 15 juin 2025 concerne l'étiquetage de certains produits mensuels VIIRS Collection 2. L'identification des traitements concernés nécessite les métadonnées exactes ; aucune correction automatique n'est déduite de la seule colonne version.

## Harmonisation et incertitude

Le pipeline de préparation M1 ne valide pas encore les modèles, coefficients, scores ou intervalles cités dans le guide ou la baseline Django. Les comptages mensuels sont livrés pour permettre cette évaluation ultérieure.

Une validation doit distinguer données manquantes et zéros recensés, éviter l'utilisation des années de test dans les traitements appris et mesurer les performances hors échantillon. Un intervalle calculé à partir du jeu de test ne constitue pas un test indépendant de sa propre couverture. Une évaluation récente ne prouve pas automatiquement la validité d'une rétrospection avant VIIRS.

Les intervalles custom restent indisponibles tant que leur méthode n'est pas évaluée. Une absence d'intervalle ne doit être affichée ni comme une incertitude nulle ni comme une estimation précise.

## Exploitation

- Le lot ne télécharge aucune donnée authentifiée et n'utilise aucun secret NASA.
- La compatibilité d'export doit être vérifiée avec M2 ; un script d'import de résultats scientifiques ne doit pas être supposé existant.
- La baseline backend conserve les réserves techniques identifiées lors de sa revue. Son intégration Git n'est pas une validation scientifique ni une preuve de sécurité ou de disponibilité de production.
- Les sorties représentent un état reproductible des fichiers fournis ; les mises à jour de produit peuvent nécessiter une nouvelle génération et une comparaison de provenance.

Références : `methodology.md`, `m1-data-audit.md`, `m1-normalization.md` et [journal officiel FIRMS](https://firms.modaps.eosdis.nasa.gov/content/notifications/firms/outages.html).
