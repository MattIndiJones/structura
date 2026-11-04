# Rechargement du marché : séances de bourse

État local au 03/11/2026. Complément au
[correctif du comparateur du 01/11](COMPARATOR_DETAILS_PRICING_2026-11-01.md).

## Cause constatée

Le rechargement global et individuel du marché dans le Pricer ne demandaient pas
`session_aware=true`. La politique générique de continuité rejetait les fermetures
prolongées comme des lacunes non bornées (`UNBOUNDED_HISTORY_GAP`).

Lecture du cache BNP.PA de ce poste : historique ajusté de 355 observations,
avec deux intervalles de cinq jours, jusqu'au 29/12/2025 et au 07/04/2026.
Ces intervalles correspondent aux fermetures de Noël et de Pâques du calendrier
XPAR. Le diagnostic reproduit le message sans réseau ni modification du cache.

## Correction

Les deux chargements du Pricer demandent maintenant la qualification des séances
déjà utilisée par le comparateur. L'estimateur RMS, l'annualisation 252, les
252 derniers rendements et le calcul de corrélation sur échantillon commun sont
conservés. Les vraies clôtures absentes sur séance ouverte restent bloquantes ;
aucun remplissage, cours précédent ou Following n'est injecté.

La séance courante n'entre dans l'échantillon attendu qu'après la clôture de sa
place, selon l'horloge métier et son fuseau. Une barre intrajournalière déjà
stockée est exclue avant cette clôture, sans être qualifiée de barre hors séance.
Les dates concernées figurent dans `session_qualification.pending_sessions`.
Cette sélection temporelle ne certifie pas la finalité des barres fournisseur.

Si les métadonnées stockées et le suffixe ne donnent pas de calendrier connu,
le service demande la place de cotation à Yahoo. La provenance est exposée dans
`sources`. Un titre sans suffixe comme AAPL peut ainsi être rattaché au Nasdaq ;
aucune place n'est inférée de la devise. Une place non identifiée reste un refus.
Les fixings officiels, les contrats bookés et la politique globale de fraîcheur
ne sont pas modifiés.

## Vérification et activation

- Sur le cache réel BNP.PA, sans réseau : 252 rendements, volatilité réalisée
  de 27,61045 %, date effective 02/11/2026, zéro substitution ; la séance du
  03/11 en cours est exclue. Ce chiffre décrit ce cache à cet instant.
- 59 tests backend ciblés distincts réussis : qualification, route HTTP,
  calendrier Nasdaq sourcé, trous réels, séance en cours et cache/provenance.
  Une fixture existante de booking a été complétée avec les deux champs
  `transaction_format=NOTE` et `instrument_family=NOTE` : son refus 422 pour
  classification absente était déjà documenté dans le rapport du 01/11.
- 961 tests frontend réussis et build Vite réussi, dont les deux nouveaux cas
  de rechargement individuel/global. Frontend compilé régénéré.

Les tests utilisent des données synthétiques, des fournisseurs simulés et des
bases isolées. Le diagnostic réel relit seulement les fichiers de marché locaux.
Aucun serveur existant arrêté, aucun compte, deal ou cache réel modifié par le
diagnostic. Aucune suite backend complète lancée, aucun commit ni push.

Redémarrer le backend par le lanceur, puis actualiser le navigateur avec Ctrl+F5
avant de recharger le marché pour appliquer aussi la sélection des séances
terminées et la résolution des places de cotation.
