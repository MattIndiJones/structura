# C14 — Axe temporel et ordre des événements

Livraison locale du 21 octobre 2026, sans commit ni push. Les trois constats
M06-05, M06-06 et M13-02 sont corrigés et validés localement. Dépendances métier :
C05 et C09 ; contrôles voisins C13, MtM/Explain et worker VaR conservés.

## Résultat métier

Deux constatations du 31 janvier et du 1er février s'exécutent dans cet ordre,
même si elles utilisent le même nœud de diffusion. Inverser leurs blocs dans le
script ne change plus le coupon ou la mémoire. Chaque occurrence garde son rang,
sa fenêtre de constatation et sa date de paiement.

À date strictement identique, l'ordre de déclaration des blocs datés reste la
règle de départage explicite. Les blocs `AT MATURITY` sont exécutés après les
blocs datés encore actifs, et `STOP` empêche tous les blocs ultérieurs. Cette
convention reprend celle recommandée dans l'audit ; aucun arbitrage supplémentaire
n'est introduit dans les termes bookés.

À un jour de maturité, le MtM et le pricing en vie simulent désormais exactement
un jour. Le prix, les probabilités, les trajectoires et le profil partagent
`dt = T / max(1, round(T × 52))`. Les variables `REALVOL` utilisent le temps
effectivement diffusé, pour les événements datés comme pour la maturité.

## Correctifs et interactions

| Constat | Changement | Validation essentielle |
|---|---|---|
| M06-05 | Construction commune des occurrences, tri chronologique stable et copie par occurrence des dates/rangs/fenêtres/paiements. Le compteur interne avance par date, pas une seule fois par nœud. | Blocs inversés ; deux dates d'un même bloc dans le même pas ; deux calendriers ; dates ISO 31/01 puis 01/02 comparées au replay historique ; règle de simultanéité et STOP. |
| M06-06 | Axe partagé entre calcul principal et analyses, fenêtres et rangs raccordés au même `dt`, annualisation homogène de REALVOL et temps de rappel contractuels dans les sorties. | Digitale déterministe à un jour ; horizons courts et non ronds ; cohérence des cinq modèles ; blocs datés et terminaux ; trajectoires arrêtées à la date demandée. |
| M13-02 | Retrait du plancher hebdomadaire dans le MtM et le pricing en vie. Retrait du même plancher dans l'annualisation de l'upside résiduel. L'horizon exact voyage dans le contexte de valorisation et le worker VaR. | Call ATM sigma 50 % à un jour, référence analytique et convergence ; égalité MtM/worker sans choc ; construction du résiduel avant strike ; Explain voisin. |

- **C05** : les calendriers figés restent inchangés. Les temps résiduels étant
  enregistrés à six décimales, une tolérance de représentation de `1e-6` année
  préserve le dernier événement ; l'exécution reste bornée à l'horizon. Cette
  tolérance ne permet pas de consommer l'observation du lendemain. Les paiements
  restent attachés à leur occurrence et au règlement contractuel.
- **C09** : le panel indépendant de qualification utilise une horloge synthétique
  par rang. Ce contrat est conservé explicitement pour ses appels directs à
  l'évaluateur. Les consommateurs du pricing utilisent les occurrences datées.
  Les huit familles approuvées repassent leurs panels, sans changement des formules
  attendues, des scripts approuvés ou de leur empreinte.
- **C13** : les fixings officiels et leur versionnement restent inchangés ; le
  calcul du temps restant ne remplace pas le passé du produit. Les cas de coupon
  officiel, correction, rollback et rejeu d'un run archivé sont revalidés.
- **Traçabilité** : `time_axis` expose la politique, l'horizon, le nombre de pas,
  le pas effectif et l'ordre retenu. Il est aussi restitué dans les paramètres
  effectifs du MtM et la réponse du pricing en vie. La modification du moteur
  entre dans son empreinte existante.

## Preuve quantitative

Call ATM, spot/strike normalisés à 1, taux et dividendes nuls, sigma 50 %,
maturité `1 / 365,25`, paiement différé sans effet au taux nul. La référence est
`2 Φ(sigma × sqrt(T) / 2) − 1 = 1,0436925 %` du nominal.

| Paires antithétiques indépendantes | MtM, % du nominal | Demi-largeur de l'IC 95 %, points de nominal |
|---:|---:|---:|
| 4 000 | 1,0401 | 0,02525 |
| 16 000 | 1,0440 | 0,01270 |
| 64 000 | 1,0443 | 0,00635 |

L'intervalle se resserre avec l'échantillon et couvre la référence dans ces cas.
Le biais d'horizon d'environ sept jours est supprimé ; ces mesures ne qualifient
pas à elles seules les autres modèles, les barrières ou toutes les sensibilités.

## Validation exécutée

**241 cas backend distincts réussis sur 12 fichiers**, dont **25 cas C14**,
et **18 tests frontend** du composable Booking/MtM. Le groupe final comporte
237 cas ; quatre tests ciblés supplémentaires couvrent la construction pré-strike.
Un test de sensibilités résiduelles plus large est écarté de ce groupe ; les prix
et Greeks de référence du harnais nominal sont contrôlés sans modification de
leurs valeurs attendues. La suite backend complète n'a pas été lancée.

Les nouveaux tests ont aussi été exécutés contre les sources sauvegardées avant
C14 : **12 échecs reproduits et un cas de simultanéité déjà correct**. La même
fixture valide et les mêmes critères sont utilisés après correction. Les échecs
intermédiaires liés à l'arrondi C05 et à l'horloge synthétique C09 ont été résolus
avant la validation finale.

Les commandes, cas individuels, mesures et SHA-256 figurent dans
[C14_VALIDATION.json](remediation-lot-0-2026-10-20/C14_VALIDATION.json).
Les JUnit et journaux restent dans `.runtime/diagnostic-acceptance/c14-2026-10-21/`.
Les tests métier utilisent des données synthétiques, des bases temporaires et un
garde réseau. Aucun serveur n'a été démarré et aucune base métier n'a été créée
ou ouverte. Aucun fichier Vue n'a changé ; le build frontend n'a pas été relancé.

## Limites et suite du registre

- Le tri des événements ne densifie pas la grille de diffusion ou de monitoring :
  deux dates proches peuvent toujours lire le même spot simulé. Il corrige leur
  ordre, leurs attributs et leur horloge de flux ; il ne crée pas deux tirages
  journaliers indépendants. Les conventions de barrières restent suivies en C16.
- L'alignement de l'axe ne rend pas identiques toutes les hypothèses des analyses.
  Le funding, les taux stochastiques et la transmission complète des conventions
  aux analyses restent suivis en C15/C18. Les tests d'égalité prix/probabilités
  portent ici sur les hypothèses communes, avec seed et échantillon identiques.
- Le Mark-to-Future conserve sa convention propre de grille extérieure
  hebdomadaire. Il réutilise le tri des occurrences ; sa qualification complète
  d'exposition, de règlement et de CVA reste à faire avec C21/C22.
- **T03 est validé localement** sur la chaîne C05/C09/C14. T09 n'est validé ici que
  pour l'horizon court ; les chiffres CVA, les créances et le P&L au règlement
  restent ouverts. T06 et T07 ne sont pas clôturés par C14.
- Les résultats archivés et les contrats existants ne sont pas réécrits. Un
  nouveau calcul d'un cas affecté doit refléter le correctif ; le rapprochement
  d'anciens runs doit tenir compte de leur empreinte moteur. Aucun recalcul ou
  backfill des données réelles n'a été exécuté. Recette graphique et qualification
  de production restent ouvertes.
