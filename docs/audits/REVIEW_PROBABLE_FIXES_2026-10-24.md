# Archives KID, uploads et bootstrap legacy — confrontation et corrections

État du 24/10/2026. Intervention locale sur un checkout déjà modifié, à la demande
de Philippe. Aucun commit, push, démarrage de service ou accès à la base privée.
La suite backend complète n'a pas été exécutée.

Les trois mécanismes suspectés sont établis dans le code antérieur. Cela établit
des défauts de contrôle et de traçabilité ; aucune exploitation ni perte en
production n'a été démontrée. Cette intervention ne change pas les formules de
pricing ni le statut indicatif du KID.

## PR01 — Une archive KID pouvait recevoir des chiffres déclarés par le client

**Constat.** `/api/kid/save` vérifiait l'accès et le rattachement au Product,
mais enregistrait SRI, MRM, CRM, VEV, horizons et coûts du corps de requête sans
preuve qu'ils provenaient du calcul serveur. Le rattachement contractuel ne
prouvait donc pas l'origine des chiffres, du scénario ou de ses paramètres.

**Correction.** `/api/kid/compute` retourne une preuve signée par l'instance,
avec les inputs effectifs, le résultat complet, l'utilisateur et son organisation,
l'empreinte des termes, la date de calcul et l'identité du moteur et de
l'implémentation KID. Sur Product existant, son ID et sa version sont aussi liés.
Pour un calcul effectué avant conservation du Product, les termes doivent
correspondre exactement à ceux du Product ensuite retenu.

La sauvegarde vérifie cette preuve, les chiffres, les termes et l'identité avant
toute écriture, puis conserve la preuve avec le rattachement final. Le navigateur
transmet la preuve sans la reconstruire. Une erreur de révision Product annule
l'ensemble de la transaction. La sauvegarde ne relance aucun pricing.

**Compatibilité.** Une nouvelle sauvegarde sans preuve valide est refusée en
HTTP 422 : les clients API doivent recalculer puis transmettre
`calculation_receipt`. Les anciennes lignes sont conservées et exposées comme
`LEGACY_UNVERIFIED`, sans leur inventer une preuve. Une preuve ou des chiffres
archivés altérés donnent `INVALID_EVIDENCE` ; une preuve valide donne
`SERVER_COMPUTED`.

La migration ajoute `calculation_evidence_json` avec `{}` pour l'historique.
Le passage d'une ancienne colonne VEV non nullable conserve également les liens
Product, les versions, les preuves déjà présentes, les index et les triggers.
Cette migration a été vérifiée sur des bases temporaires, sans migration de la
base de Philippe.

**Limites.** Le KID reste `INDICATIVE_NON_PRIIPS`. La signature démontre une
origine et une intégrité internes à l'instance ; elle ne constitue ni une
validation réglementaire, ni un horodatage tiers, ni une preuve opposable face à
un administrateur disposant de la clé. La rotation ou perte de la clé peut
invalider la vérification d'archives antérieures. Les anciennes archives ne
deviennent pas rétrospectivement reproductibles.

## PR02 — L'upload documentaire n'avait pas de budget applicatif

**Constat.** `/api/documents` lisait le fichier en entier avec `await file.read()`
avant écriture, sans plafond de taille dans ce chemin. Une éventuelle limite de
proxy n'était pas une garantie apportée par l'application.

**Correction.** Le plafond est de **20 Mio par fichier** ; le corps HTTP complet
est limité à **21 Mio**, dont 1 Mio de marge pour l'encapsulation multipart.
Un middleware compte les octets réellement reçus avant le parseur multipart :
un `Content-Length` absent ou mensonger ne contourne pas le plafond. Un corps
trop grand est refusé en HTTP 413, y compris derrière un préfixe ASGI.

Le corps accepté est temporairement spoolé, puis le fichier est copié par blocs
de 64 Kio avec contrôle de la taille réelle. Les fichiers partiels sont supprimés
sur dépassement ou erreur ; une collision ne supprime pas un fichier préexistant.
L'échec d'enregistrement ou de révision Product annule l'écriture SQL et supprime
le fichier nouvellement créé.

**Limites.** Ces plafonds concernent l'upload générique `/api/documents`.
Ils ne prouvent pas la sûreté de tous les autres imports. Il n'y a pas ici de
quota global de stockage, de qualification antivirus, de test de saturation
concurrente ou de garantie sur la configuration du proxy. Les tests de seuil
réduisent les constantes pour vérifier exactement les frontières sans générer
de gros fichiers ; ce ne sont pas des mesures de charge à 20 Mio.

## PR03 — Un démarrage non configuré créait des comptes partagés

**Constat.** Le fallback legacy de `_seed` pouvait créer l'organisation Demo et
deux comptes à mots de passe publiés dans le dépôt. Les installations métier et
le workspace Admin disposent déjà de chemins de bootstrap identifiés ; ce
fallback implicite n'était pas nécessaire à leur fonctionnement.

**Correction.** Un démarrage sans identité d'installation ni configuration Admin
est refusé avant connexion et migration. La simulation exige explicitement
`STRUCTURA_BOOTSTRAP_PROFILE=simulation`, `STRUCTURA_WORKSHOP_CHILD=1` et un
`STRUCTURA_DATA_DIR` absolu correspondant au moteur, hors de `backend/data`,
sans marqueur de retrait ni identité métier/Admin existante.

La simulation ne crée aucun utilisateur sans instruction explicite. Pour préparer
une campagne neuve, le workshop génère un secret technique dans son répertoire
privé et fournit `bootstrap_credentials.json`. Le bootstrap crée alors uniquement
`workshop_admin`, avec un mot de passe haché. Les trois connexions techniques du
contrôleur utilisent ces identifiants, sans recours aux anciens mots de passe.
Le secret reste hors de l'état JSON exporté de la campagne. Le cache de baseline
privée est versionné séparément et conserve les identifiants correspondant à sa
base, sans copier la clé de signature de l'instance.

Au redémarrage, une désactivation, un changement de rôle ou un changement de
mot de passe du compte technique provoque un refus, sans restauration des
habilitations. Un compte technique n'est pas ajouté automatiquement à une
simulation déjà peuplée d'autres utilisateurs.

**Compatibilité et limites.** Une ancienne simulation possédant une base mais
pas le fichier privé est refusée à la reprise : il faut une nouvelle campagne.
Son book est conservé ; aucune conversion destructive ni réactivation n'est
effectuée. La consultation historique reste un chemin distinct en lecture seule.
Les installations et Admin configurés conservent leur bootstrap propre. Cette
correction ne supprime ni ne change des comptes présents dans une base réelle.
La confidentialité du répertoire privé dépend toujours des droits du système de
fichiers ; aucune certification de déploiement ni campagne complète avec services
en fonctionnement n'est revendiquée.

## Preuves de validation

Toutes les exécutions backend utilisent le harness isolé
`.runtime/diagnostic-acceptance/review-probable-fixes-2026-10-24/run_targeted.py` :
données temporaires, garde d'accès SQLite interdisant `backend/data`, variables
Structura réinitialisées et réseau externe bloqué. Les requêtes API passent par
TestClient/ASGI, sans lancer de serveur.

| Preuve | Résultat | Périmètre |
|---|---:|---|
| `targeted.xml` | 162 réussis | KID, Product, correctifs précédents, gouvernance et bootstraps identifiés |
| `bootstrap-final.xml` | 48 réussis | 43 cas du nouveau fichier de régression, bootstrap privé, provisionnement réel par API, révocation, reprise de baseline et compatibilité métier/Admin |
| `migration-final.xml` | 4 réussis | Conservation des index/triggers et des liens KID, ancienne migration VEV, redémarrages Admin |
| `frontend-build.log` | 784 réussis, 88 fichiers | Inclut deux nouveaux tests KidPanel : transmission de preuve et affichage du refus |
| Même journal | Build Vite réussi, 12,81 s | Compilation vers un répertoire isolé ; `frontend/dist` préservé |

Les passages backend se recouvrent : **170 cas distincts réussis**, et non la
somme des exécutions. Les dernières modifications de bootstrap et de migration
ont motivé leurs seuls passages complémentaires. Le premier journal
`regressions.xml` est intermédiaire et n'est pas ajouté à ces couvertures.

Les tests couvrent notamment le calcul KID réel puis sa conservation sans
recalcul, les chiffres/preuves altérés, le mauvais utilisateur ou Product, les
termes devenus différents, les nombres après sérialisation navigateur, l'absence
de preuve historique et les rollbacks. Pour les documents : seuil accepté/refusé,
taille réelle, flux interrompu, collision, nettoyage, corps sans longueur fiable
et préfixe de déploiement. Pour le bootstrap : refus avant création de base,
profil incomplet, base identifiée refusée comme simulation, absence de comptes
partagés, création explicite du compte technique, provisionnement via login/API,
non-restauration après révocation et conservation d'un ancien book refusé.

Les commandes exactes, empreintes des sources et journaux sont recensés dans
`verification.json` ; `task-only.patch` isole cette intervention des modifications
préexistantes du checkout. Les chemins de preuve sont relatifs à la racine du
dépôt, sous `.runtime/diagnostic-acceptance/review-probable-fixes-2026-10-24/`.

Le rapport consolidé et l'archive ZIP de la phase précédente n'ont pas été
régénérés dans cette intervention. Ils restent les preuves de leur état daté ;
la présente note décrit les corrections supplémentaires. Il reste à qualifier
séparément les exigences réglementaires KID, la sécurité et l'exploitation en
production et les parcours complets non couverts par ces tests ciblés.
