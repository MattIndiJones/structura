# Ligne de crédit par contrepartie — cadrage, sans implémentation

## Décision de départ

À la création ou à la sélection d'une réponse RFQ, afficher un contrôle de ligne par contrepartie. Il est **informatif** pour l'instant : un dépassement n'empêche ni la cotation, ni la sélection, ni le booking. Le message doit distinguer « ligne disponible », « dépassement », « ligne non renseignée » et « calcul indisponible » ; ces deux derniers états ne valent jamais un feu vert.

Le contrôle porte sur la **contrepartie juridique du deal**, pas nécessairement sur le fournisseur RFQ qui envoie la cotation. Le rapprochement fournisseur → contrepartie doit être explicite ; si la contrepartie n'est pas identifiée, le contrôle est indisponible. Les deals, RFQ et limites appartiennent à l'organisation cliente, non à leur créateur. Une installation dédiée et une plateforme partagée doivent appliquer le même cloisonnement par organisation.

## Ce qu'il faut définir avec le métier Risk

La colonne `Counterparty.limit_eur` existante est un plafond souple de **concentration en nominal converti en EUR**. Elle ne mesure pas encore l'exposition de crédit. Elle ne doit pas être réutilisée comme ligne de crédit sans une décision explicite sur la métrique.

Pour un produit structuré, le nominal seul surestime ou sous-estime souvent la perte potentielle en cas de défaut. Une première définition praticable serait : exposition courante = max(valeur de remplacement du portefeuille net, 0), puis exposition potentielle future par horizon et stress, moins collatéral éligible et garanties reconnues. Le sens du trade, la valeur pour l'organisation, les flux déjà réglés, le close-out netting et le CSA changent le résultat. Avant tout chiffre opérationnel, il faut arrêter :

- l'unité et la conversion FX, la date des cours et leur fraîcheur ;
- le périmètre juridique (entité, groupe, garanties, netting set, CSA) et l'agrégation multi-desk ;
- l'horizon du risque (jusqu'à maturité, prochaine date de rappel, période de liquidation) ;
- la méthode de potentiel futur : scénario stressé ou quantile, historique ou simulé, et la fréquence du recalcul ;
- le traitement des produits sans valorisation exploitable, des RFQ concurrentes, des opérations en attente de booking et des annulations ;
- l'autorité de la limite, sa devise, sa période de validité, les délégations et la piste d'audit des changements.

## Moment du contrôle proposé

Au stade AO, le prix et donc l'exposition changent selon le fournisseur retenu. Afficher une **estimation par réponse** avec les hypothèses et l'horodatage ; réserver éventuellement une capacité provisoire seulement après décision métier, pour éviter qu'une dizaine d'AO non traitées ne consomment artificiellement la ligne. Recalculer au choix de la réponse, puis juste avant booking avec les termes et la contrepartie juridique définitifs. Montrer l'utilisation actuelle, l'impact estimé de l'opération et la marge restante. En cas de dépassement, continuer le workflow en journalisant l'avertissement et l'identité de l'utilisateur ; l'éventuel blocage sera une décision ultérieure.

Les corrections ou annulations de deal doivent libérer/recalculer l'exposition ; les valorisations de marché et le FX peuvent la faire dépasser après booking, sans nouvelle RFQ. Un fournisseur sans contrepartie mappée ou une limite absente doit déclencher un état « à compléter », jamais une hypothèse de risque nul.

## Critères de validation avant développement

Risk valide la formule et des exemples chiffrés : trade favorable/défavorable, achat/vente, collateralized/unsecured, multi-deals avec et sans netting, changement de FX, trade appelé ou annulé, RFQ sans prix, fournisseur distinct de la contrepartie bookée. L'administrateur client peut ensuite fixer une ligne par contrepartie juridique, avec contrôle d'accès et historique. Aucun calcul ni contrôle de crédit n'est ajouté dans cette livraison.
