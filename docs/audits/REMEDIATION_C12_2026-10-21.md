# C12 — Stockage atomique des séries et caches

Les deux constats C12 sont corrigés et validés localement. Un import ne remplace
plus silencieusement une série après avoir écarté des lignes invalides ; séries,
copies de marché et association au ticker sont publiées ensemble. Les lectures
concurrentes et les réponses d’historique en cache restent indépendantes.

Travail autorisé avec modifications et tests ciblés, **sans commit ni push**.
La politique C11 reste **3 jours calendaires pour cours EOD et FX de reporting,
borne incluse**. Aucune décision métier supplémentaire n’est déclarée approuvée.

## Résultat par constat

| Constat | Résultat obtenu | Validation locale |
|---|---|---|
| M03-09 — imports insuffisamment contrôlés | Rejet intégral des dates dupliquées/manquantes/ambiguës, des nombres non finis, nuls, négatifs, booléens ou absents ; conventions obligatoires ; identifiants sans collision ; aucun changement de série ou d’association après échec de téléchargement, de sérialisation ou de publication. | JSON, Excel, HTTP, pannes injectées, arrêt brutal d’un processus et écritures concurrentes |
| M03-11 — cache modifiable par un appelant | Chaque appel reçoit une copie profonde indépendante. Les demandes identiques simultanées partagent le chargement. Le cache distingue installation, ordre du panier, paramètres, politique et génération du stockage. Un effacement ou une nouvelle publication empêche une ancienne demande de réinstaller son résultat dans le cache courant. | Listes et métadonnées imbriquées, huit lecteurs simultanés, chargement partagé, effacement pendant une requête et deux racines de données |

## Publication et reprise

`core/market_storage.py` conserve des objets Parquet/JSON immuables dans
`market_storage/objects/`. Un manifeste donne les adresses logiques actives.
Les adresses logiques du manifeste sont relatives au répertoire de données :
une copie/restauration dans un autre répertoire reste lisible. Une transaction
prépare ses fichiers, les ferme et synchronise leur contenu,
puis remplace **un seul manifeste** par renommage atomique. Une panne avant ce
remplacement laisse l’ancienne génération lisible. Aucun fichier actif n’est
réécrit sur place.

Le téléchargement AMC publie dans cette même transaction sa série ajustée, sa
colonne brute, l’association instrument/ticker et les copies brutes/ajustées
consommées par C11. La sauvegarde d’un profil de dividendes regroupe aussi ses
observations et son diagnostic. Le cache FX utilise le même mécanisme de
publication pour son fichier. Le remplissage automatique AMC réutilise le
chemin d’ingestion validé.

Les écritures sont sérialisées par un verrou de processus et un verrou de
fichier interprocessus. Les ajouts d’observations brutes relisent la version
commise sous verrou avant fusion : deux ajouts concurrents ne perdent pas de
dates ni d’associations. Les cours ajustés gardent la règle C11 de remplacement
de leur lot, pour éviter le mélange d’époques d’ajustement.

Une lecture locale voit un seul manifeste pendant son parcours. Les anciens
objets restent accessibles à cette lecture après une nouvelle publication.
Un téléchargement vérifie également que ses fichiers cibles n’ont pas changé
pendant son attente : une ancienne réponse ne peut pas écraser un remplacement
plus récent. Le refus demande un nouveau chargement. Pour une lecture de marché
qui a déjà obtenu une réponse fournisseur valide, l’échec de persistance reste
explicite dans `storage_error` et n’altère pas le stock courant.

Les anciens fichiers restent lisibles sans migration lorsqu’ils sont désignés
sans ambiguïté. Les nouveaux noms susceptibles de perdre des caractères, de
dépasser la limite ancienne ou de collisionner par casse portent une empreinte
complète. `A/B` et `A B` restent distincts. Un ancien `A_B.parquet` n’est pas
attribué automatiquement à l’un de ces deux noms. Une suppression masque les
adresses logiques et ne réactive pas un ancien fichier. Le stock partagé du
fournisseur reste distinct de la suppression d’une entrée AMC.

Les lecteurs historiques de campagnes suivent également le manifeste et gardent
les empreintes des fichiers réellement lus. L’installateur des séries de référence E
publie son lot dans le magasin explicitement demandé, vérifie les collisions sur
les générations actives et ne modifie pas la racine de données de l’application.
Il utilise la distribution Structura actuelle ; aucune campagne IA n’est lancée.

## Import manuel

Le formulaire demande une **devise reconnue par C03**, une **convention de
rendement total** et l’**unité de devise**. Les séries principales acceptées sont
les cours ajustés dividendes/splits et les NAV de rendement total. Un cours brut
seul ne remplace pas une série utilisée pour les rendements totaux.

JSON et Excel gardent les formats de colonnes existants. Les dates texte sont
au format `AAAA-MM-JJ` ; aucune date numérique ou conversion de format local
n’est devinée. Une colonne brute facultative `price_close` exige une date
explicite de référence des unités de titres, comprise entre la dernière
observation et aujourd’hui. La date d’import n’est pas inventée comme date des
unités. L’API rejette une convention manquante avant tout remplacement.

Le composant d’import transmet fichier et conventions ensemble. Le bouton de
choix du fichier reste désactivé tant que les conventions obligatoires sont
absentes. Le refus serveur est affiché par le parcours existant. Les droits
administrateur des écritures restent appliqués ; les refus sans session et
pour un utilisateur ordinaire sont testés.

## Dépendances et scénario transverse

- **C03 :** référentiel de devises réutilisé ; aucune modification des identités
  juridiques, droits ou référentiels existants.
- **C05 :** ancre de fin de mois et règlement TARGET conservés. Les dates et
  snapshots contractuels ne sont pas régénérés par le stockage.
- **C11 :** seuil de trois jours et distinctions brut/ajusté, couverture et
  provenance conservés. Les 33 cas de gouvernance C11 passent, dont le passage
  Product/calcul/booking. Les caches CCR et leurs lecteurs locaux passent aussi.
- **C10 :** le stockage rejette la publication d’une ancienne réponse devenue
  incompatible ; les protections des interfaces existantes restent en place.
- **Studies :** le dossier de marché autonome conserve sa priorité et ne dépend
  pas du manifeste partagé. Les alias de noms restent utilisables ; ses tests
  dédiés passent. Cela ne constitue pas un nouvel audit des modules 18/19.

**T04 est validé localement par un scénario combiné** : grille du 31 janvier
sans dérive, règlement traversant les fêtes TARGET, panier avec série arrêtée,
FX ancien exclu, import invalide refusé sans mutation, puis lecture des données
stockées avec fournisseur désactivé. Les validations C03/C05/C11 antérieures
restent jointes. La recette graphique et la qualification production restent
ouvertes ; la finalité officielle relève toujours de C13. Aucun autre scénario
transverse ou chantier n’est clos par C12.

## Validation et preuves

- **160 cas backend ciblés sur 12 fichiers**, tous réussis en **18,73 s**, dont
  **57 nouveaux cas C12**. Les appels HTTP externes sont bloqués. Les tests
  couvrent des lecteurs et écrivains en threads, deux processus écrivains, un
  processus arrêté avant publication, les erreurs de disque, la reprise, la copie
  du magasin dans un autre répertoire et les lecteurs directs de caches.
- **637 tests frontend sur 72 fichiers**, tous réussis, puis build Vite en
  **12,07 s**. Six nouveaux tests contrôlent le formulaire d’import et ses
  conventions. La sortie est temporaire ; `frontend/dist` préexistant est préservé.
- Le premier contrôle de compatibilité a signalé un message de dividende vide
  qui avait perdu le ticker ; il est corrigé. Le premier test du composant
  utilisait un contexte Vue incomplet ; sa fixture est corrigée. Les contrôles
  concernés sont verts dans les sélections finales.
- Lecture ciblée avant correction, puis régressions déterministes après
  correction. Aucun nouveau résultat exécuté avant correction n’est revendiqué.

Les [preuves consolidées](remediation-lot-0-2026-10-20/C12_VALIDATION.json)
contiennent les critères, cas exécutés, empreintes et contrôles de conservation.
Les journaux locaux sont dans `.runtime/diagnostic-acceptance/c12-2026-10-21/`.
Les rapports et preuves C01 à C11 restent conservés à l’identique.

## Limites opérationnelles

Les générations antérieures sont conservées pour les lecteurs en cours ; aucun
nettoyage automatique n’est introduit. Un arrêt brutal avant publication peut
laisser un objet non référencé, qui n’est jamais consommé. La rétention et la
surveillance de l’espace disque doivent être définies avant exploitation durable.
Une sauvegarde du marché doit inclure le **manifeste, ses objets et les anciens
fichiers encore utilisés**, pas seulement les anciennes séries Parquet.

La validation porte sur les fichiers locaux et les processus testés. Elle ne
certifie pas les garanties d’un partage réseau, une panne d’alimentation ou la
disponibilité réelle du fournisseur. Les imports refusés ne réparent pas
automatiquement les anciens fichiers ambigus ou insuffisamment documentés.

Pas de suite backend complète, de recette graphique manuelle, de migration,
de campagne IA ou d’utilisation de la base métier. Aucun serveur démarré ;
les processus auxiliaires de test sont terminés. Aucun commit ni push.
