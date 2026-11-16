# Couche maritime exploratoire

La carte `front-bis` affiche par défaut la **ZEE et les points maritimes**. La couche violette montre un instantané indépendant du calendrier terrestre : détections thermiques NASA FIRMS demandées en VIIRS NOAA-20 NRT pour le 10–14 novembre 2026. La couverture est inconnue, le produit est déclaré par la requête mais non vérifié indépendamment, et le champ NASA `type` est absent. Une détection n'est pas un incendie ni une torchère confirmée. Cette couche ne modifie ni la base de données ni les statistiques terrestres.

Le périmètre utilisé est le polygone Gabon MRGID 8476 de [Marine Regions World EEZ v12](https://www.marineregions.org/eezmethodology.php), obtenu le 15 novembre 2026 via son [service WFS](https://marineregions.org/webservices.php). Il s'agit d'un référentiel indicatif et non d'une délimitation juridique. Les points sur la frontière sont exclus. L'emprise de requête `[6.9,-6.5,11.2,1.1]` couvre l'enveloppe du polygone de référence ; cela ne garantit pas la couverture satellite. La période est partielle et les valeurs NRT peuvent être révisées.

Le fond de ZEE affiché dans la carte est chargé à la demande depuis le [service WMS Marine Regions](https://www.marineregions.org/webservices.php), filtré sur MRGID 8476. Il requiert une connexion au fournisseur ; les quatre points de l'instantané local restent affichables hors ligne. La vue initiale inclut l'emprise de la ZEE et les quatre points. Le fond n'inclut pas les eaux territoriales et n'est pas une carte juridique.

Ce polygone ZEE ne couvre pas la mer territoriale côtière : des détections sur l'eau proches du littoral peuvent donc être exclues. La mer territoriale nécessite une couche de référence distincte ; elle n'est pas incluse dans cet instantané.

L'instantané `front-bis/public/data/gabon-maritime-observations.geojson` contient quatre points. Il conserve les empreintes SHA-256 du CSV original et du polygone, la date d'acquisition du fichier et les métadonnées de la requête. Ne pas redistribuer le polygone Marine Regions dans le dépôt : le fournisseur demande de renvoyer les utilisateurs vers ses services. La [NASA décrit le type VIIRS 3](https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html) comme détection sur l'eau ; ce champ est toutefois indisponible dans notre CSV NRT et n'a pas été inventé.

Le CSV brut NASA de 47 lignes et son manifeste sont versionnés dans `data/fixtures/maritime/` : les 43 points hors polygone ou sur sa frontière ne sont pas attribués à la ZEE. Le polygone reste à télécharger auprès du fournisseur. Installer les dépendances géographiques avec `python -m pip install -r pipeline/requirements-geo.txt`. Pour reconstruire :

```sh
python -m pipeline.maritime_snapshot --source <source.csv> --manifest <source.manifest.json> --boundary <gabon-eez.geojson> --output <nouveau-fichier.geojson>
```

La commande vérifie notamment empreinte, période, emprise, géométrie, identifiant et nombre de lignes ; elle refuse d'écraser une sortie existante. La clé FIRMS ne figure ni dans les sources versionnées ni dans l'instantané. L'affichage de la carte ne constitue pas une validation opérationnelle ou une importation PostGIS. L'intégration API et les données historiques maritimes nécessitent un travail complémentaire M2/M3.
