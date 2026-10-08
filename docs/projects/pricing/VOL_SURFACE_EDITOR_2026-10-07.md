# Smiles par classe d’actif et éditeur de surface — 07/10/2026

## État et périmètre

Implémenté localement sur `codex/payscript-basket-startdate`, sans commit ni push
pour cette livraison. La surface saisie atteint Local Vol et LSV ; Heston et
SABR proposent un ajustement automatique de leurs paramètres constants.
L’affichage « Écart au constant » est hors périmètre, à la demande de Philippe.

**Recette quantitative complémentaire :** la [reprise de l'étude intégrée](../../audits/RECETTE_SMILE_INTEGRE_2026-10-07.md)
vérifie désormais les profils réellement générés par le frontend, les ajustements
du service, le chemin API/PayScript et la grille LV/LSV de production. Vingt cas
d'autocalls quatre ans à 20 % et 30 % ATM, mono / worst-of, ainsi que douze
repricings après édition de la surface réconcilient les flux. Les petites alertes
statistiques de vanilles ne sont pas reproduites avec davantage de trajectoires.
Les surfaces restent des hypothèses synthétiques ; il ne s'agit pas d'une
calibration aux options SG/STMicro. SABR conserve un résidu important à 30 % :
jusqu'à 143 bps vanille et 403 bps digital dans le contrôle indépendant. Les prix
affinés utilisent 208 pas/an ; l'application reste à 52 et le contrôle renforcé
Local Vol mesure encore 6–8 bps entre ces deux grilles.

Les profils sont des **hypothèses indicatives**, sans cotations d’options.
Une volatilité réalisée chargée depuis Yahoo reste une estimation historique,
reprise comme hypothèse de niveau, et ne devient pas une vol implicite observée.

## Initialisation et niveaux

Le catalogue identifie les actions, notamment les groupes Actions, Banques et
Luxe, et les indices actions. Les instruments inconnus, FX, matières premières
et indices de volatilité n’acquièrent pas automatiquement un profil actions.
Le choix manuel d’un profil reste possible. Les hypothèses des dossiers déjà
conservés sont restaurées ; elles ne sont pas remplacées par un nouveau défaut.

| Profil | ATM de départ sans autre estimation | Asymétrie SSVI ρ | Intensité η |
|---|---:|---:|---:|
| Actions | 30 % | −75 % | 0,85 |
| Indices actions | 20 % | −80 % | 1,05 |

L’échelle de forme vaut 0,04. Les maturités initiales sont 3 mois, 6 mois,
1, 2, 3, 5, 7 et 10 ans, avec extension au ténor contractuel au-delà de 10 ans.
Le niveau ATM initial est plat ; le smile s’atténue avec la maturité.
Les strikes affichés sont 60, 80, 100, 120 et 140 % **du forward**.

Le niveau choisi agit continûment via θ(t) et φ(θ), sans seuil de régime.
Sur le profil Actions à 30 %, la vol 1 an à 80 % du forward vaut environ
35,70 %. Sur le profil Indices à 20 %, elle vaut 26,07 %. Ces valeurs sont
des exemples des profils livrés, pas des observations de marché.

Le champ σ représente l’ATM **1 an**. Modifier ce champ multiplie les niveaux
ATM de toute la surface dans le même rapport, en conservant sa structure
manuelle. Une modification incompatible avec les contraintes est refusée.

## Édition et contrôles

Une courbe peut être tirée verticalement pour déplacer une maturité ou toutes
les maturités, selon le sélecteur. La poignée ATM modifie le niveau de la maturité
active. La poignée 80 % ajuste ρ ; les autres poignées d’aile ajustent η.
La forme étant commune à la surface, une modification d’aile peut affecter
plusieurs maturités : ces cellules sont toutes actualisées à l’écran.

Courbes, matrice et champs partagent les mêmes données. L’édition des cellules
reconstruit la même surface cohérente, avec une tolérance maximale de 0,10 point
de vol pour une cible d’aile. Une cible hors de cette famille est refusée.
Annulation et réinitialisation du profil sont disponibles.

Les variances ATM totales sont strictement croissantes et interpolées
linéairement depuis l’origine. Au-delà du dernier pilier, l’ATM de ce pilier est
prolongé. Les conditions suffisantes SSVI de calendrier et de butterfly sont
contrôlées sur l’horizon déclaré, pour tous les strikes. Le moteur étend et
revérifie cet horizon si le produit l’exige. Une surface incohérente provoque
une erreur explicite, sans repli automatique sur une vol constante.

## Consommation et conservation

- Constant utilise σ ATM 1 an ; la matrice reste disponible pour les modèles à smile.
- Local Vol utilise les dérivées analytiques de la nouvelle surface. La grille
  spot comporte 300 points entre 0,01 et 10 fois le niveau normalisé ; le carry
  utilise les mêmes courbes de taux et de dividendes que la simulation.
- LSV utilise cette même cible Dupire et sa composante de variance Heston.
- Heston et SABR recalibrent leurs paramètres après une modification de surface,
  de taux plat, de dividende ou d’horizon. Le Pricer et le calcul RFQ attendent
  cet ajustement avant de construire la requête. Les résultats devenus obsolètes
  sont refusés ; une erreur conserve les paramètres antérieurs et bloque ce calcul.
- Une saisie explicite des paramètres Heston/SABR passe en mode manuel. Ce mode
  est conservé dans les RFQ, Product et snapshots de valorisation. Le bouton de
  recalibration permet de revenir au mode automatique.

`vol_surface.atm_nodes` utilise toujours les **fractions moteur**, y compris dans
les snapshots d’édition. Les champs σ/q et paramètres de modèle continuent de
suivre les conversions d’affichage existantes. La surface est conservée au
booking et transmise au pricing résiduel. Elle reste une hypothèse de marché
aux ténors restants, sans vieillissement ni acquisition automatique de cotations.

Les chocs de σ redimensionnent la cible. Les anciens chocs de `skew/curvature`
sont explicitement refusés pour une cible SSVI Local Vol/LSV : leur translation
vers ρ/η reste à concevoir. Les autres scénarios de modèle conservent leur
fonctionnement. Le Vega existant reste un bump du moteur ; il ne constitue pas
une recalibration complète à une nouvelle surface de marché.

## Limites de calibration et de précision

L’ajustement paramétrique reste indicatif : Heston par Fourier, SABR par le
simulateur spot de production avec 3 000 paires antithétiques, 104 pas/an et
graine fixe. L’objectif SABR utilise la jambe OTM et la parité ; il ne remplace
pas une validation indépendante des prix et de la martingale.
Les taux/dividendes de l’ajustement sont **plats**, même si le pricing dispose
de courbes. L’horizon d’ajustement est limité à 10 ans, signalé à l’écran.
Une déformation de la surface ne peut donc pas garantir une reproduction exacte
par un modèle à paramètres constants.

L’interface affiche l’erreur vanille maximale de l’ajustement, en bps du spot
normalisé, et un éventuel arrêt sans convergence. Dans le cas Actions 30 %,
4 ans, r=3 %, q=2 % testé pendant cette livraison : environ **34,9 bps Heston**
et **163,5 bps SABR**. L’erreur Heston affichée pour LSV concerne sa composante
de variance, pas la qualité finale de reproduction de la cible par le LSV.

Le défaut de simulation de l’application reste **52 pas/an**. La validation du
benchmark précédent à 208 pas/an n’est pas une certification de tous les prix
issus de cet éditeur, notamment après une déformation manuelle ou pour les
barrières américaines. Les grands niveaux de vol peuvent dépasser les bornes
de la famille proposée et nécessiter une forme moins intense.

## Vérification réalisée

- Tests backend ciblés : 24 cas initiaux (surface, contrôle commun et dix
  modèles mono/multi historiques sans nouvelle surface), puis 19 cas après les
  corrections de conservation et de scénarios. **35 cas distincts exécutés**.
  Le test de consommation exige que le prix bouge avec le smile ; la cible plate
  reproduit le GBM avec les mêmes aléas. Aucune suite backend complète.
- Build frontend final réussi : **254 tests dans 32 fichiers**, puis Vite.
- Recette navigateur sur une **copie isolée** de la base : profils automatiques
  SG 30 % et Euro Stoxx 50 20 %, déplacement ATM, déplacement global des courbes,
  déplacement de poignée 80 %, valeurs synchronisées, annulation, refus de
  variance décroissante, recalibration Heston, saisie de ξ en mode manuel,
  masquage démo et matrice aux largeurs 760 et 480 px. Console sans erreur.
- À 480 px la matrice défile dans son conteneur ; un débordement horizontal
  global de l’application de 54 px reste observable, hors correction de ce lot.
- La recette visuelle ne constitue pas un nouveau comparatif exhaustif des
  cinq prix d’autocall ni un nouveau parcours complet de booking RFQ.

Capture : `output/smile-ui-20261007/editor-index.png`. Les serveurs isolés de
recette ont été identifiés par PID, heure et commande puis arrêtés. La base
réelle n’a pas été modifiée pendant cette recette.
