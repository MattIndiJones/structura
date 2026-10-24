# C13 — Finalité des cours et registre officiel

Livraison locale du 21 octobre 2026, sans commit ni push. Périmètre : M03-01,
M12-01, M12-02, M12-05 et M13-01. Les autres correctifs et les données métier
existantes sont conservés. Le registre reste ouvert pour les recettes transverses
et la qualification de production.

## Décision métier retenue

Philippe a remplacé son premier choix d'attente jusqu'au lendemain par :
« non pas de delai en fait tu prends le cours quand il sest dispo ».

La règle implémentée est donc **aucun délai ajouté après la fin de séance** :
une clôture non ajustée reçue après la clôture de la place peut être qualifiée
immédiatement. Une barre intrajournalière ne devient pas une clôture parce que le
champ fournisseur s'appelle `Close`. Le calendrier, le fuseau et l'heure de fin
de séance doivent être établis. Une place inconnue reste en exception contrôlée.
Une donnée téléchargée avant la clôture doit être rafraîchie ; le passage du temps
ne certifie pas le contenu déjà en cache.
La valeur reçue avant clôture reste visible dans l'observation indicative ; elle
ne crée aucune version officielle et ne peut déclencher un coupon ou un rappel.

Le report maximal reste de trois jours calendaires : J+3 admis, J+4 hors politique.
Le fixing du jour exige la barre exacte du jour. Les décisions manuelles sourcées
et motivées restent distinctes de l'adoption automatique de Yahoo.

## Changements et interactions

| Constat | Correction et critère couvert |
|---|---|
| M03-01 / M12-01 | Qualification par séance réelle, fuseau, heure de réception et politique explicite. Refus avant clôture, jours fériés, week-ends, fuseau incohérent et métadonnées absentes. Admissibilité dès la clôture, sans temporisation supplémentaire. |
| M12-02 | Une lacune du flux ne dégrade plus une version validée, qu'elle ait été capturée automatiquement ou par un utilisateur. Le diagnostic de source est audité séparément. Une panne totale peut laisser le rejeu officiel poursuivre son préfixe établi. |
| M12-05 | Décision d'exception, nouvelle version de fixing, rejeu, application, audit et révision Product sont préparés dans une seule transaction. Un échec technique provoque un rollback ; la même intention peut être réessayée. Un résultat métier explicitement bloqué reste restitué comme tel. |
| M13-01 | Le MtM lit les versions validées du registre, vérifie leur cohérence avec l'événement puis remplace les observations contractuelles correspondantes dans le rejeu. Les versions candidates et les conflits ne sont pas remplacés silencieusement par le fournisseur. |

- **C05** : aucune reconstruction ni modification du calendrier contractuel booké.
  Le calendrier de séance du fournisseur sert à qualifier sa publication ; il ne
  remplace pas les places d'observation et centres de règlement du produit.
- **C11** : seuil de trois jours conservé ; les données statistiques ajustées
  restent séparées du rejeu des fixings non ajustés. Le spot courant du fournisseur
  continue d'alimenter la vie future lorsqu'il est postérieur au fixing passé.
- **C12** : la copie locale des clôtures de référence, des splits et de leurs
  métadonnées utilise le manifeste atomique et le contrôle de version du stockage.
  Une copie locale admissible est réutilisée avant un nouveau téléchargement.
- **C01/C06** : les droits existants restent appliqués. Une opération de fixing
  enrichit le lifecycle et la révision du Product, sans modifier ses termes ni le
  contrat exécuté. Les fixtures d'Explain déclarent maintenant leur rôle utilisateur.
- **Calculs conservés** : un changement de fixing invalide les références courantes
  MtM et Greeks. Les anciens `ValuationRun` restent intacts et rejouables ; les
  nouveaux runs archivent les identifiants des versions effectivement consommées.

Le cas économique vérifié est un coupon à barrière 80 %, fixing officiel 90 et
historique fournisseur 40 : le coupon de 10 % est acquis et la mémoire est vidée.
Le spot courant postérieur reste 40. Une correction officielle à 70 retire le coupon
du nouveau calcul et porte 10 % en mémoire ; l'ancien run reste inchangé.

## Validation exécutée

**232 cas backend distincts réussis sur 12 fichiers ciblés**, dont 22 cas C13,
et **22 tests frontend** sur EventsTab et useBookingMtm. La preuve détaillée et les
commandes figurent dans [C13_VALIDATION.json](remediation-lot-0-2026-10-20/C13_VALIDATION.json).

- Séances Paris, New York et Tokyo ; changements d'heure ; séance écourtée US ;
  Noël et week-end ; horodatage naïf refusé ; barre conservée avant clôture refusée.
- Refus d'officialisation avant clôture puis acceptation immédiate après publication ;
  preuve archivée contenant la qualification ; bornes de report J+3/J+4.
- Lacune puis panne totale du fournisseur après officialisation automatique.
- Échec de rejeu et échec après préparation d'une application : aucune moitié
  de décision conservée, reprise réussie.
- Coupon/mémoire, correction officielle, invalidation du courant et rejeu hors réseau
  du run archivé ; tests voisins de lifecycle, fenêtres, MtM quotidien et Explain.

Aucun accès HTTP externe n'a été nécessaire aux tests métier. Les calendriers sont
locaux. Aucun serveur n'a été démarré ; aucune base métier n'a été créée ou ouverte.
Aucun fichier Vue n'a changé ; le build frontend n'a pas été relancé.

Une tentative plus large incluant les tests numériques Monte Carlo pré-strike a
été interrompue, puis remplacée par les tests de construction du résiduel pertinents
pour C13. La suite backend complète n'a pas été lancée.

Un échec préexistant est isolé :
`test_legacy_migration_marks_ambiguous_rows_for_manual_review` construit une base
minimale sans `products`, alors que la migration Product y crée un trigger.
Le test du snapshot d'avant C13 reproduit `no such table: main.products` ; les deux
fichiers de migration ont les mêmes SHA-256 qu'avant C13. Ce défaut reste à traiter
dans la maintenance des migrations. Il n'est pas compté parmi les cas réussis.
Le contrôle global `git diff --check` signale également une ligne vide préexistante
en fin de `api/opportunities.py`, fichier inchangé par C13.

## Limites et suites

- La qualification est une règle opérationnelle de clôture, **pas une attestation
  de cours officiel émise par la bourse ou par Yahoo**. Un fournisseur qui publie un
  champ erroné après clôture demeure un risque de source ; les contrôles de valeur,
  devise, split et variation restent actifs.
- La couverture des places est explicite et limitée. Les indices composites, places
  inconnues ou métadonnées absentes demandent une exception sourcée ; aucune place
  n'est devinée depuis la devise ou le suffixe du ticker.
- Les anciens strikes sans version restent des références historiques signalées
  `LEGACY_UNVERIFIED`, jamais des fixings certifiés. Aucune migration ou certification
  rétroactive des données réelles n'a été exécutée. Les candidats non versionnés sont
  refusés comme références de valorisation.
- Pour un payoff dépendant du chemin quotidien, les dates officielles priment, mais
  le reste de l'historique demeure fournisseur/indicatif. C13 ne certifie pas un chemin
  continu à partir des seuls fixings événementiels.
- Une copie locale n'est pas un abonnement aux révisions futures du fournisseur.
  Les corrections officielles restent gouvernées et versionnées ; la recette d'un
  flux de production et de ses notifications de révision reste à effectuer.
- **T08 est partiellement validé pour C13** : autorité, atomicité, MtM et conservation
  des runs couverts. Le moniteur, CCR, les courses entre calculs et corrections,
  l'attribution et la diffusion complète des invalidations restent à qualifier avec
  C18/C19/C21/C22/C26. Aucun de ces lots n'est clôturé par cette livraison.

La nouvelle dépendance `exchange-calendars==4.13.2` est déclarée et installée dans le
venv de travail. Son API de séances et de calendriers est documentée dans les
[sources du projet](https://github.com/gerrymanoim/exchange_calendars/blob/master/exchange_calendars/calendar_utils.py).
La version du calendrier et la politique de finalité sont conservées dans la preuve
du fixing ; les calendriers bookés existants ne sont pas modifiés.
