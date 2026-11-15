# Couche maritime exploratoire

La carte `front-bis` propose le bouton **Observations maritimes**. La couche violette montre un instantané indépendant du calendrier terrestre : détections thermiques NASA FIRMS demandées en VIIRS NOAA-20 NRT pour le 10–14 novembre 2026. La couverture est inconnue, le produit est déclaré par la requête mais non vérifié indépendamment, et le champ NASA `type` est absent. Une détection n'est pas un incendie ni une torchère confirmée. Cette couche ne modifie ni la base de données ni les statistiques terrestres.

Le périmètre utilisé est le polygone Gabon MRGID 8476 de [Marine Regions World EEZ v12](https://www.marineregions.org/eezmethodology.php), obtenu le 15 novembre 2026 via son [service WFS](https://marineregions.org/webservices.php). Il s'agit d'un référentiel indicatif et non d'une délimitation juridique. Les points sur la frontière sont exclus. L'emprise de requête `[6.9,-6.5,11.2,1.1]` couvre l'enveloppe du polygone de référence ; cela ne garantit pas la couverture satellite. La période est partielle et les valeurs NRT peuvent être révisées.

L'instantané `front-bis/public/data/gabon-maritime-observations.geojson` contient quatre points. Il conserve les empreintes SHA-256 du CSV original et du polygone, la date d'acquisition du fichier et les métadonnées de la requête. Ne pas redistribuer le polygone Marine Regions dans le dépôt : le fournisseur demande de renvoyer les utilisateurs vers ses services. La [NASA décrit le type VIIRS 3](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) comme détection sur l'eau ; ce champ est toutefois indisponible dans notre CSV NRT et n'a pas été inventé.

Le CSV brut NASA de 47 lignes et son manifeste sont versionnés dans `data/fixtures/maritime/` : les 43 points hors polygone ou sur sa frontière ne sont pas attribués à la ZEE. Le polygone reste à télécharger auprès du fournisseur. Installer les dépendances géographiques avec `python -m pip install -r pipeline/requirements-geo.txt`. Pour reconstruire :

```sh
python -m pipeline.maritime_snapshot --source <source.csv> --manifest <source.manifest.json> --boundary <gabon-eez.geojson> --output <nouveau-fichier.geojson>
```

La commande vérifie notamment empreinte, période, emprise, géométrie, identifiant et nombre de lignes ; elle refuse d'écraser une sortie existante. La clé FIRMS ne figure ni dans les sources versionnées ni dans l'instantané. L'affichage de la carte ne constitue pas une validation opérationnelle ou une importation PostGIS. L'intégration API et les données historiques maritimes nécessitent un travail complémentaire M2/M3.
