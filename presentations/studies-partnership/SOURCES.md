# Sources et conventions du cas pédagogique

La présentation décrit les fonctions existantes de Studies et une proposition de partenariat. Elle ne revendique aucun client, rendement réel ou gain de productivité mesuré.

## Données

Source : `artifacts/studies/LO_ALL_BLOCKS_2020_2025/RESULTATS_ATTENDUS/CONTROLE_OUTIL/resultat.json`, méthode Studies 2.4, scénario fictif long only multidevise 2020–2025.

Le fichier `assets/data.js` contient uniquement les 1 566 NAV quotidiennes, les 20 contributions par titre et une empreinte du fichier source. Pas de connexion à l’application ou à un compte client.

- **Performance nette cumulée : +38,07 %**. NAV initiale 100, finale 138,065178 environ ; résultat non annualisé, après frais dans ce scénario.
- **Drawdown maximal : −31,70 %**. Calcul sur la NAV quotidienne : NAV / plus-haut courant − 1. Il ne s’agit pas d’une perte annuelle ni d’une prévision.
- **1 540 ordres analysés**. Nombre d’ordres du périmètre ; distinct des 1 341 rapprochements FIFO.
- **Contributions :** réalisé + latent, effet de change inclus, hors dividendes et frais du fonds. Le graphique sélectionne les trois meilleures et les deux moins bonnes contributions sur les 20 titres. Ce n’est pas une décomposition complète du rendement net du fonds.

Toutes les observations quotidiennes sont utilisées dans les courbes, sans lissage ni reconstruction illustrative. Les axes de temps présentent les débuts d’année ; le point final est au 31 décembre 2025.

## Aperçus du rapport

`assets/report-summary.png` et `assets/report-risk.png` proviennent des pages de synthèse et de risque du PDF de recette du scénario fictif, généré après les corrections de méthode. Ils montrent notamment les scores descriptifs Manager Skill 53 et risque 56. Ces scores ne sont pas une probabilité de compétence.

## Limites à conserver

Le Buy & Hold du module reste brut avec dividendes réinvestis, tandis que le fonds fictif est net et conserve les dividendes en cash. L’écart n’est pas utilisé comme preuve commerciale de la valeur de gestion dans ce support.

Brinson demeure une attribution statique indicative sur proxies. La réplicabilité factorielle est rétrospective et ne démontre pas un portefeuille investissable. Le pilote proposé doit qualifier les données et les instruments du dossier réel.

Le contenu reprend `docs/projects/studies/PRESENTATION_MERCREDI_CONTENU_2026-09-23.md`. Les réserves techniques détaillées sont dans `docs/projects/studies/STUDIES_EXISTING_FIXES_2026-09-21.md`.
