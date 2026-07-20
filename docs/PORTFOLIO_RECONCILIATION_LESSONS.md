# Reconstruction de portefeuille AMC — Obstacles rencontrés & leçons

Ce document recense les pièges et fausses pistes rencontrés en réconciliant le P&L FIFO
(`backend/app/core/fifo/`) contre la vérité NAV sur CH1352587724 (juillet 2026). Objectif :
ne pas repasser par les mêmes détours sur le prochain AMC.

## Checklist rapide avant de commencer

- [ ] Tester avec `C:\Users\admin\GitHub\structura\.venv\Scripts\python.exe`, **jamais** le python système par défaut (dépendances manquantes = échecs silencieux, voir §5)
- [ ] Appeler les vraies fonctions du pipeline (`run_fifo_recon`, `load_study_data`...), ne jamais réimplémenter une version simplifiée pour tester (voir §6)
- [ ] Croiser `Def.txt` (poids/positions) contre une source indépendante (factsheet officiel de l'émetteur) avant de faire confiance aux champs `weight` (voir §3)
- [ ] Vérifier les vraies dates de split via `yfinance.Ticker(x).actions`, jamais une heuristique de ratio de prix (voir §4)
- [ ] Borner toute correction de split par le `as_of` de l'étude, jamais par la date du jour réelle (voir §4)
- [ ] Demander la mécanique exacte des frais (fréquence, formule HWM, coûts de transaction) plutôt que de la supposer (voir §7)
- [ ] Se méfier des fonds très volatils : impossible de repérer un événement de frais à l'œil sur la courbe NAV (voir §7)
- [ ] La question qui compte pour `qty_mode` n'est pas "la term sheet est-elle en unités de compte ?" (presque toujours oui) mais "le **carnet d'ordres lui-même** trade-t-il en unités de compte ?" (voir §1 et §9)
- [ ] Une position ouverte **négative** en mode `strict` est un signal d'alarme fiable — reconstruction incomplète (mismatch d'unités le plus souvent), pas à couvrir silencieusement par une injection synthétique sans creuser (voir §9)
- [ ] Une bonne réconciliation contre une vérité indépendante (NAV) n'est pas une preuve de justesse en soi — vérifier que la reconstruction est saine avant de faire confiance au résultat (voir §9)

---

## 1. Le mode "unité de compte" (cert_units) — fausse piste majeure

**Symptôme initial** : le P&L semblait faux, et l'hypothèse "cet AMC est en unité de compte,
pas en actions" semblait expliquer l'écart.

**Ce qui a été construit puis défait** : tout un mode `qty_mode="cert_units"` — injection T0 en
unités de compte, calcul de facteurs d'échelle, branchement des marks — pour finalement découvrir
que c'était inutile pour ce type de fonds.

**La vraie explication** : la formule du panier T0 en mode "actions" —

```
initial_qty = n_certs × (poids% × NAV) / cours_réel_action
```

— s'auto-corrige déjà pour l'unité de `qty_per_cert` de la termsheet, car ce terme **s'annule
algébriquement**. Peu importe que la termsheet exprime les quantités en actions ou en unités de
compte, le résultat final ne dépend que du poids%, de la NAV et du cours réel — trois valeurs déjà
fiables. "Cert_units" n'est nécessaire que si le **carnet lui-même** (pas juste la termsheet)
enregistre des unités non-actions — jamais observé à ce jour.

**Leçon** : avant de construire un mode entier pour une convention d'unité suspectée, vérifier
algébriquement si la formule existante ne s'auto-corrige pas déjà. Le mode cert_units reste
disponible dans le module FIFO autonome (`api/fifo.py`) au cas où un futur fonds en aurait
vraiment besoin, mais il a été retiré de l'étude AMC.

---

## 2. Désactiver une correction "parce qu'on est en UC" — erreur en cascade

En croyant le carnet en unité de compte, la correction de split carnet
(`_fix_carnet_unadjusted_prices`, aujourd'hui `fix_carnet_splits`) avait été désactivée pour ce
mode. Résultat : un split réel (KLA) n'était plus corrigé, et le P&L a explosé de façon
incohérente (réalisé -2.60M / latent +4.23M, alors que le total ne bougeait presque pas — signature
d'un problème de reclassement, pas de magnitude).

**Leçon** : le carnet d'ordres est **toujours** en vrais prix d'actions, même quand la termsheet /
Def.txt sont en unité de compte. La correction de split doit rester active inconditionnellement.

---

## 3. Le champ `weight` de Def.txt est peu fiable

**Découverte** : Klarna affichait 33.78% de poids dans Def.txt, alors que le factsheet officiel
LUKB montre que la plus grosse ligne du fonds entier ne dépasse pas 8%.

**Vérification qui a tranché** : recalculer `position × cours_marché_réel / AUM_total` reproduit
**exactement** les pourcentages du factsheet officiel (testé sur 4 titres, correspondance parfaite),
alors que le champ `weight` brut de Def.txt ne correspond à rien. Le champ `position` (quantité),
lui, s'est révélé fiable à chaque vérification.

**Piège annexe** : un premier diagnostic ("le champ weight est buggé") s'est avéré faux — l'écart
Klarna venait en réalité d'un **rebalancement entre deux dates de snapshot** (Def.txt daté du
18.06, factsheet daté du 03.07, rebalancement le 29.06 entre les deux). Mais même en comparant
Def.txt et le factsheet à la **même date exacte**, `weight` restait faux pour plusieurs titres —
confirmant que c'est bien un champ précalculé cassé côté export, indépendamment du problème de
date.

**Correction appliquée** : `load_study_data()` recalcule maintenant `weight`/`value_prod` depuis
`position × mark` au lieu de faire confiance au fichier.

**Leçon** : ne jamais faire confiance aveuglément à un champ précalculé dans un export tiers.
Toujours croiser contre une source indépendante avant de conclure. Et vérifier l'alignement des
dates avant de crier au bug.

---

## 4. Correction de split — heuristique de prix vs calendrier réel

**Ancienne méthode** (`_fix_carnet_unadjusted_prices`) : comparer le prix carnet au prix yfinance
et déduire un facteur si le ratio est proche d'un entier ≥ 2. Fonctionnait pour KLA (cas simple :
achat seul, pas de vente) mais **ratait complètement** SMCI (double ISIN), ServiceNow et Carvana
(achats + ventes mélangés pré/post-split) — ces trois cas étaient explicitement exclus du code.

**Nouvelle méthode** (`fix_carnet_splits`) : utiliser le vrai calendrier d'opérations sur titre de
yfinance (`Ticker(x).actions["Stock Splits"]`) plutôt que deviner un ratio. Deux mécanismes :
1. **Réémission double-ISIN** (ex. SMCI) : détecter les noms partagés par 2+ ISIN avec des plages
   de dates disjointes, aliaser l'ancien vers le nouveau.
2. **Split par ordre** : pour chaque ordre, multiplier tous les ratios de split réels survenus
   strictement après sa date et jusqu'à la date de référence.

**Bug découvert en cours de route** : le correctif utilisait `datetime.date.today()` (date réelle
du jour d'exécution du script) comme borne, au lieu du `as_of` de l'étude (dernière date du
carnet). Un split survenu **après** le `as_of` de l'étude (CrowdStrike, 02.07.2026, alors que l'étude
s'arrête au 15.06.2026) était appliqué à tort, alors que les marks de l'étude — eux — ne le
reflètent pas encore. Résultat : incohérence entre carnet corrigé et marks, faux P&L latent négatif
sur CrowdStrike.

**Leçon** : toute correction historique doit être bornée par la date de référence de l'analyse, pas
par "maintenant". Une étude "as of" une date doit ignorer tout ce qui s'est passé après.

**Découverte annexe** : un scan systématique des 95 ISIN du carnet contre leur historique complet
de splits (jusqu'aux années 1980) a permis de vérifier qu'aucun autre split n'avait été manqué —
utile pour avoir confiance dans le résultat plutôt que de se demander en permanence "et s'il y en
avait un autre".

---

## 5. Environnement de test ≠ environnement réel — piège coûteux

Le vrai serveur tourne avec `C:\Users\admin\GitHub\structura\.venv\Scripts\python.exe`. Les scripts
de test ad hoc utilisaient par défaut un autre python système, **sans `pyarrow`**.

**Conséquence** : `get_fx_series()` réussit à télécharger les données FX depuis yfinance, mais
plante silencieusement en essayant d'écrire le cache parquet (`pyarrow` manquant) — et
l'exception, mal isolée dans le même bloc `try/except`, fait croire à la fonction que le ticker FX
n'existe pas. Résultat : conversion JPY→USD retournée comme `1.0` (pas de conversion), et SoftBank
Corp affichait un gain latent fictif de **+$549,908** (le mark JPY brut traité comme si c'était déjà
du USD).

Plusieurs heures ont été perdues à enquêter sur ce "bug" avant de réaliser qu'il n'existait que
dans l'environnement de test, pas dans l'app réelle.

**Leçon** : toujours tester avec le même interpréteur que le serveur réel. Un échec silencieux dans
une fonction de conversion FX/prix peut ressembler exactement à un vrai bug métier.

---

## 6. Scripts de test simplifiés qui divergent du vrai pipeline

Pour déboguer plus vite, plusieurs scripts ont réimplémenté une version simplifiée du pipeline
FIFO (au lieu d'appeler `run_fifo_recon()` directement) — notamment en passant `isin_aliases={}`
au lieu de calculer le vrai alias Swissquote (`CH0010675863 → CH1548235246`). Résultat : le script
de test montrait deux positions Swissquote distinctes (une pour le lot T0, une pour le carnet) qui
ne se rencontrent jamais en FIFO — un bug qui n'existe que dans le test, pas dans le vrai code.

**Leçon** : pour déboguer un pipeline à plusieurs étapes couplées (alias, correction de split,
injection T0, marks), appeler directement la fonction de production plutôt que la
réimplémenter "en plus simple" pour tester — la divergence entre les deux est une source de bugs
fantômes.

---

## 7. Frais — ne jamais deviner la mécanique

Trois composantes de frais devaient être modélisées pour rapprocher le P&L FIFO de la NAV, et
chacune avait un piège :

- **Frais de gestion** (0.75% p.a.) : accrual quotidien simple sur l'AUM — direct, pas de piège.
- **Frais de performance** (10%) : la première hypothèse ("prélevé une fois par an, au 31
  décembre") était **fausse**. La vraie mécanique : prélevé **quotidiennement**, mais uniquement
  les jours où la NAV atteint un **nouveau plus haut historique** (High Water Mark). Le calcul
  correct : `fee_per_unit = gain_net_au-dessus_du_HWM × taux/(100-taux)`, sommé sur chaque jour de
  nouveau plus-haut, multiplié par les unités en circulation ce jour-là. La différence entre
  l'hypothèse annuelle et la vraie mécanique journalière a fait varier l'estimation de frais de
  performance de ~$103K à ~$199K — presque du simple au double.
- **Coût de transaction** (0.10% par rebalancement) : une composante à laquelle on n'aurait pas
  pensé sans que l'utilisateur ne la mentionne explicitement — absente du carnet (les prix
  d'exécution ne l'incluent pas), c'est un coût structurel séparé prélevé par l'émetteur.

**Tentative infructueuse** : essayer de repérer visuellement le prélèvement de performance fee
dans la courbe de NAV quotidienne (recherche de baisses ponctuelles). Ce fonds bouge de plus de 1%
sur 25% des jours (composition très volatile : crypto, momentum) — impossible de distinguer un
prélèvement de frais du bruit de marché normal. Le calcul théorique (day-by-day sur toute la série)
a été nécessaire, pas une inspection visuelle.

**Leçon** : ne jamais supposer la fréquence/formule d'un frais de performance — la demander
précisément. Une petite différence mécanique (annuel vs quotidien, avec ou sans HWM) change le
résultat du simple au double. Pour les fonds très volatils, ne pas chercher à repérer les
événements de frais à l'œil dans la NAV — les calculer analytiquement sur toute la série.

---

## 8. Bug trouvé mais pas encore corrigé — décomposition prix/FX du lot T0

`build_initial_orders()` construit le lot T0 avec `fx=1.0` et `price_ccy=prod_ccy`, alors que son
`price_local` (`yf_price`) est en réalité **déjà converti en USD** par `build_marks()` en interne.
Le P&L total (`price_prod`) reste correct — mais la décomposition prix/FX affichée pour tout
round-trip impliquant ce lot T0 est fausse (une partie de l'appréciation réelle d'une devise locale
est comptée comme si c'était un effet-prix). Repéré via un "Part FX" de 27% anormalement élevé sur
Swissquote (CHF).

**Statut** : identifié, expliqué, **pas corrigé** — n'affecte pas le P&L total donc non prioritaire
par rapport à la réconciliation NAV, mais à corriger avant de publier un rapport qui affiche la
ventilation prix/FX en détail.

---

## Résultat final de cette réconciliation (référence historique — voir §9 pour la suite)

| Étape | Écart vs vérité NAV |
|---|---|
| Avant tout correctif (mais avec 3 synthétiques en échec — ventes SMCI ignorées) | +8.5% *(trompeur — reconstruction incomplète)* |
| Après les 6 corrections de split (SMCI, ServiceNow, Carvana, KLA, Swissquote, Arista) | +17.4% *(reconstruction complète mais frais non modélisés)* |
| + frais de performance (hypothèse annuelle, fausse) | +9.5% |
| + frais de performance (vraie mécanique HWM journalière) + coût de transaction | -3.2% *(⚠️ invalidé — voir §9)* |

---

## 9. Le -3.2% ci-dessus n'était pas la bonne réconciliation (2026-07-16)

Le rapport envoyé au client s'appuyait sur ce -3.2%. Une ré-investigation le 2026-07-16
(déclenchée par un utilisateur qui a remarqué que le P&L n'était plus le même sur une étude
relancée) a montré que la correction de split pour ServiceNow et Carvana était en réalité
**incomplète** à l'époque de ce chiffre : elle produisait des positions ouvertes **négatives**
(-854 actions ServiceNow, -1530 Carvana — impossible pour un fonds long-only), masquées par des
injections synthétiques dont le prix était lui-même dérivé de la même source ambiguë. Une fois la
correction réellement complète (mode `t0_synthetic` + `fix_carnet_splits` sans exclusion), ces
positions redeviennent positives et plausibles (+42 / +118), et le nouveau total FIFO passe de
+1.60M à +1.94M — un écart de +23% vs la NAV implicite, pas -3.2%.

**Pourquoi le -3.2% semblait pourtant "propre"** : coïncidence. Un vrai bug de mismatch d'unités
masqué par une injection synthétique peut, par hasard, produire un chiffre qui *ressemble* à une
bonne réconciliation — la proximité avec la NAV n'est **pas** en soi une preuve de justesse.

**Preuve indépendante** (pas seulement yfinance) : recherche web confirmant les deux splits via
SEC filings et communiqués officiels — ServiceNow 5:1 (record 16/12/2025, trading ajusté dès
18/12/2025) et Carvana 5:1 (effectif 07/05/2026, trading ajusté dès 08/05/2026) — dates et ratios
strictement identiques à ce que le calendrier yfinance donnait déjà.

**Signal de cohérence supplémentaire** : chaque correction de split réelle appliquée en plus
(KLA seul → KLA+ServiceNow+Carvana) a fait *augmenter* l'écart vs NAV (10% → 23% avec KLA seul
déjà noté à l'époque ; confirmé à nouveau ici) plutôt que le réduire. Un écart qui grandit à
mesure qu'on corrige des bugs réels va dans le sens d'un écart structurel (marks au marché actuel
vs NAV lissée par l'émetteur), pas d'un bug qui resterait à trouver — mais ce n'est pas une
preuve formelle, seulement un faisceau d'indices convergents.

**Leçon la plus importante de toute cette session** : un chiffre qui recoupe bien une vérité
indépendante (ici la NAV) n'est pas automatiquement le bon chiffre — il faut vérifier que la
reconstruction elle-même est saine (positions ouvertes non-négatives, pas d'injection synthétique
en échec) avant de faire confiance à la proximité du résultat final. Voir aussi
`docs/STUDY_COMPARISON_ENGINE.md` : l'outil de comparaison d'études prévu est né directement de
ce cas — il aurait rendu ce diagnostic immédiat au lieu de nécessiter une investigation manuelle.
