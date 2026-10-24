# Recette graphique des parcours métier — 23 octobre 2026

**Résultat : chaîne principale exécutée dans le navigateur, neuf anomalies corrigées localement et revérifiées sur leur périmètre.** Le registre distingue cette recette de la campagne backend précédente et de la qualification déployée. Aucun commit ni push.

[Preuve structurée](remediation-lot-0-2026-10-20/GRAPHICAL_VALIDATION.json) · [registre courant](remediation-lot-0-2026-10-20/REGISTER.json) · [campagne backend antérieure](BACKEND_FULL_VALIDATION_2026-10-23.md).

## Conditions et portée

Recette native dans le navigateur intégré, au format bureau, sur trois services isolés : portail `18100`, BNP Paribas `18101`, Leonteq `18105`. Provisionnement et identité utilisent le mécanisme hybride existant ; aucun contournement du marqueur de retrait de l'ancien environnement. Les bases sont sous `.runtime/hybrid-saas/graphical-2026-10-23/`. `backend/data/structura.db`, absent au départ, reste absent. Les données fictives, exports et captures restent dans les répertoires de recette ignorés par Git.

Le serveur utilise l'application réelle. Un adaptateur local ne remplace que les routes statiques pour servir le build isolé. Les API, permissions, transitions, calculs, signatures et transactions métier restent celles de l'application. Le scénario de marché natif `SYNTHETIC_SCENARIO`, seed 42, fournit les observations fictives ; les appels externes `requests`/`curl_cffi` sont bloqués dans les services. Ce garde ne constitue pas une certification d'isolation réseau de tout le navigateur ou de toutes les bibliothèques. Aucun prix Yahoo réel n'est qualifié par cette recette.

**48 points de contrôle** conservent un DOM, une capture et une note ; il s'agit de jalons, pas de 48 scénarios indépendants. Le dossier local est `.runtime/diagnostic-acceptance/graphical-2026-10-23/`. Les trois services ont été arrêtés par leur protocole natif ; sortie des processus et libération des ports vérifiées.

## Parcours obtenus à l'écran

| Parcours | Résultat observé | Limite de la preuve |
|---|---|---|
| Portail et contextes | Six organisations proposées ; accès Leonteq puis BNP ; profils Super utilisateur, Front et Opérations exercés | Pas de reprise d'un ancien workspace Admin ni de déploiement TLS |
| Permissions | Front refusé sur Booking ; Opérations refusé sur Pricer ; consultation RFQ permise sans invitation au calcul privé | Pas de revue complète de toutes les habilitations D05 |
| Economics / calendrier | Phoenix mémoire AIR.PA, coupon 8 %, barrières 100/70/60, 1 an ; refus d'un coupon manquant et de la règle de jointure non choisie ; choix explicites observation/règlement | Mono, GBM, taux déterministe ; pas de qualification de tous les modèles ni calendriers en panier |
| Pricer → Product | Calcul réel à 5 000 trajectoires, seed 42 : **101,0468 %**, IC affiché [100,81 ; 101,28] ; conservation de Product 1 et de ses termes v1 | Un calcul d'exploration ne constitue pas une cotation exécutable |
| Product → RFQ → quote → booking | Même Product 1/v1 ; preuve de calcul conservée ; quote BNP 100, ferme, révision 3, sélectionnée ; revue explicite puis Deal 1 `LEON-20261023-001`, 1 M EUR ; rechargement du même dossier | Quote manuelle ; pas d'accord réseau bilatéral ni de seconde jambe distante |
| Fixing / alertes | Refresh collectif ; fixing automatique synthétique correctement refusé ; exception manuelle sourcée et motivée appliquée au strike ; registre officiel v1 validé | Ce refus est attendu. Pas de coupon arrivé à échéance, cash réel ou correction après paiement |
| MtM / historique / note | VR-1 : **101,0952 %**, IC [100,98 ; 101,21], 20 000 trajectoires ; heures locales cohérentes ; deux notes figées distinctes ; nouveau PDF relu et rendu sur deux pages | Note d'une valorisation unique, pas d'attribution complète entre deux dates |
| Risque / stress | Greeks disponibles par métrique ; theta absent affiché comme indisponible ; choc spot −20 % et vol +10 points : 101,10 → 86,46 %, variation **−146 376 EUR** | Pas de VaR positive avec historique long ni de qualification des sensibilités avancées |
| CCR | Navigation native corrigée ; calcul borné 64/64, deux horizons, sans re-fetch ; résultat incomplet explicite, MtM préparé, PFE/CVA indisponibles lorsque les historiques/crédits manquent | Aucun résultat CVA complet ni contrôle de limite PFE/CVA qualifié par ce jeu de données |
| Clients / CRM | Client fictif, mandat EUR, contact et opportunité liés ; clôture perdue refusée sans motif puis acceptée avec motif Timing | Pas de conversion multi-devises ni d'opportunité gagnée avec attribution historique déplacée |
| Optimizer | Budget annoncé 60 s, 1 candidat, 4 000 trajectoires, 1 worker ; Athena 12 mois confirmé : coupon 15,69 %, prix 100,03 %, IC [99,78 ; 100,28] ; export JSON réel ; reprise des paramètres | Une cellule de grille, pas un optimum global ni un test de dépassement de budget |
| Réinvestissement | Scan lancé ; candidat exclu avec **« Dividende inconnu : hypothèse explicite requise avant proposition. »** | Le refus est attendu ; aucune proposition positive figée ni PDF de roll validé ici |
| Production / UAT | Prévisualisation puis génération explicite d'un lot de 1 Capital Garanti / 100 kEUR, 1 pricing, 1 deal ; Production conserve son seul deal manuel de 1 M EUR, UAT son seul deal de 100 kEUR | Pas de suppression du lot ni de toute la matrice historique du générateur |
| Démo et autre installation | RFQ : prix, panier, nominal, paramètres, script et calculs masqués puis restaurés ; BNP ne voit aucune RFQ Leonteq ; file RFQ reçues BNP vide | Masquage de présentation du dossier consulté ; pas d'audit exhaustif des exports ou de toutes les vues Démo |

Le sens `vente` du Deal est celui de la banque et correspond ici à une position longue pour Structura, conformément à Q10. Les calculs et signes n'ont pas été inversés.

## Anomalies corrigées

Les identifiants G01–G09 forment un suivi graphique distinct des 132 constats initiaux et des 180 cas de tests F01–F21. Aucun de ces inventaires historiques n'est renuméroté ou gonflé.

| ID | Priorité | Défaut et correction | Dépendances / validation |
|---|---|---|---|
| G01 | P1 | Une installation fraîchement initialisée refusait son propre schéma au redémarrage : table d'identité Admin créée mais non enregistrée dans les métadonnées du nouveau processus. Enregistrement explicite avant preflight ; une identité Admin occupée reste refusée. | C02 ; deux initialisations natives en processus frais, identité et utilisateurs inchangés, base mixte refusée ; 36 tests voisins réussis |
| G02 | P1 | Le prix à l'émission s'affichait mais sa conservation RFQ échouait sur `valuation_date`. La comparaison utilise le strike lorsque le reçu de pricing à l'émission ne porte pas de date de valorisation ; reçu signé inchangé. | C06/C18 ; conservation réelle réussie, reçu à l'émission refusé pour le lendemain ; 61 tests voisins réussis ; booking UI obtenu |
| G03 | P2 | Après création/sélection depuis Product, l'URL restait une intention de nouvelle RFQ ; rechargement incorrect. La sélection remplace désormais l'URL par l'identifiant du dossier. | C06/C07/C08 ; test de route et rechargement graphique du dossier booké, sans création supplémentaire |
| G04 | P1 | Le refresh collectif actualisait les alertes sans recharger les détails déjà ouverts ni invalider le MtM courant. Détails et erreurs rechargeables, réponses périmées écartées et résultats MtM invalidés. | C10/C13/C18/C26 ; tests refresh, erreur/retry et MtM en vol ; exception et traitement visibles à l'écran |
| G05 | P2 | Historiques valorisation/risque et lots UAT interprétaient des timestamps UTC comme locaux. Réutilisation du parseur UTC existant ; dates contractuelles inchangées. | C19/C21/C27 ; 15:05 UTC → 17:05 et lot 15:26 UTC → 17:26 vérifiés |
| G06 | P2 | Le lien CCR quittait le routeur à hash et menait à une 404. Utilisation du RouterLink natif. | C21 ; clic réel, ouverture du CCR et calcul obtenus |
| G07 | P2 | Un profil sans pricing recevait une invitation à calculer ; une quote close sélectionnée déclenchait à tort l'avertissement « meilleur prix non retenu ». Projection réservée aux profils autorisés ; comparaison uniquement en présence d'une meilleure quote éligible. | C01/C23 ; deux tests de restitution, relecture Opérations à l'écran sans invitation ni fausse alerte |
| G08 | P2 | Le PDF annonçait systématiquement Yahoo, y compris pour un run synthétique. Source effective issue du run dans l'annexe, mention générique corrigée pour note et explain. | C11/C19 ; 54 tests voisins réussis ; nouveau PDF 2 pages, source synthétique exacte, aucune mention Yahoo ; ancienne version conservée octet pour octet |
| G09 | P2 | Le mode Démo laissait visibles les valeurs du dossier RFQ. Réutilisation des masques de présentation existants pour panier, nominal, prix, paramètres, script, cotations et panneaux de calcul. Le panneau CCR reste monté pendant le masquage pour conserver sa saisie et ses résultats. | C01/C27 ; build et tests frontend réussis ; captures Démo activé/désactivé sur les assets finaux, valeurs métier conservées |

La recette a aussi rencontré deux incidents propres à son outillage : un argument de build mal transmis par PowerShell, puis l'absence de garde `__main__` dans l'adaptateur isolé lors du spawn Windows du générateur. Ils ont été corrigés dans `.runtime` ; la génération a ensuite abouti avec le générateur réel. Ces incidents ne sont pas comptés comme défauts applicatifs. Une page gardant les anciens assets après redémarrage a été remplacée par une page fraîche ; l'identité du script final a été contrôlée dans le DOM avant la validation G09.

## Validation et préservation

- Backend : **151 cas ciblés distincts réussis**, dans huit fichiers, sans échec ni ignoré dans ces trois campagnes finales (36 + 61 + 54). La reproduction G02 en échec est conservée séparément et n'entre pas dans le décompte des succès. Six nouveaux cas backend couvrent les gardes modifiées.
- Frontend : **737 tests réussis dans 83 fichiers**, puis build Vite réussi après la dernière modification. Six nouveaux tests frontend couvrent les corrections de route, refresh, réponse MtM périmée et restitution privée. Les contrôles Démo complémentaires sont graphiques.
- Base de recette relue en mode SQLite `query_only` : filiation Product/RFQ/Deal v1, quote retenue r3, reçu signé, fixing officiel, deux notes et leurs PDF, archive Optimizer/export, séparation UAT ; aucune violation de clé étrangère.
- Ancien PDF figé et nouveau PDF correspondent chacun aux octets conservés de leur propre version ; VR-1 et son contexte concordent dans les deux notes et le registre de valorisation.
- Les preuves backend antérieures, la référence figée de l'étape 1, le HEAD et la branche sont préservés. Les modifications préexistantes hors périmètre ne sont pas écrasées. Le build est produit sous `.runtime`, sans régénérer `frontend/dist`.

Le passage complet antérieur **3 943 succès / 3 ignorés** reste une preuve datée du code avant cette recette. La suite backend complète n'a pas été relancée ici ; cette livraison apporte les tests ciblés et la recette graphique ci-dessus. Aucun statut n'est transformé en certification globale ou de production.

## Suite priorisée et critères de sortie

| Ordre | Travail restant | Dépendances et arbitrages | Critère de validation |
|---|---|---|---|
| 1 | RFQ réseau bilatérale et exécution sur deux installations réelles de recette | C01/C03/C06/C08/C23 ; revue D05, identités juridiques et accords préparés | Publication, réception, calcul privé non divulgué, quote révisée, clôture irréversible, reprise après coupure et un seul booking par jambe avec reçus rapprochés |
| 2 | Lifecycle daté complet, correction après consommation et P&L cash | C13/C18/C19/C21/C22/C26 ; D06 correction après consommation, D07 paiement déclaré/confirmé | Coupon puis rappel/maturité, paiement à sa date réelle, correction versionnée, invalidation des indicateurs courants et rapprochement cash + variation de valeur ; archives antérieures inchangées |
| 3 | Risque positif avec données qualifiées et couverture complète | C11/C12/C21/C27 ; D08 domaine VaR/CCR | Historiques, crédit et recouvrement qualifiés ; résultat complet, exclusions et limites vérifiées ; scopes Production/UAT et dates d'arrêté identiques dans les archives |
| 4 | Roll positif, gel et export d'une proposition | C05/C18/C19/C25 ; conventions D09/D10 déjà confirmées | Dividende et prix de sortie explicités ; frais/quantité/récupération réconciliés ; PDF de la proposition figée identique après modification du marché vivant |
| 5 | Surfaces/calibrations, paniers et contraintes de budget en UI | C07/C10/C16/C17/C20 ; domaines D04, budget/SLA D12 | Tests d'erreur et de réponse tardive à l'écran ; seuils 5/10 pb et domaine C16 respectés ; dépassement/interruption explicites sans résultat qualifié abusif |
| 6 | Reprise historique, exploitation et recette déployée | C02/C19/C27, puis travaux précédents | Inventaire des anciennes installations/archives, migration attestée, reconnexion, sauvegarde/restauration et TLS ; matrice de profils, navigateurs et formats étroits définie et exécutée |

Les arbitrages déjà acceptés ne sont pas rouverts : règle de calendrier par produit, fusion des stubs longs, seuil de report de trois jours, cours disponible après clôture sans délai ajouté, funding hors drift/taux stochastiques, tolérances C16/C17, gel manuel et conservation des archives. Les décisions encore ouvertes restent identifiées comme telles ; aucune approbation nouvelle n'est déduite de cette recette.
