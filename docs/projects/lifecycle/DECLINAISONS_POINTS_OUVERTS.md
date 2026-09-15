# Déclinaisons — trois points ouverts

> Document de cadrage. Rien de ce qui suit n'est implémenté à la date de
> rédaction. Le mécanisme des déclinaisons (avenant / roll, filiation,
> marquage des écarts, comparateur) est en place et livré au commit `8bb331a`.

- Date : 2026-08-29
- Périmètre : ce qui manque autour des déclinaisons, pas dedans.
- Ordre de traitement recommandé : **3, puis 1, puis 2** — voir la conclusion.

---

## 1. Figer une variante devenue proposition client

### État actuel

Une variante est **vivante**. Elle se reprice à chaque ouverture, avec les
données de marché du jour. Le niveau montré au client lundi n'est plus celui
qu'affiche l'écran mercredi : le spot a bougé, la vol aussi, et la variante
suit.

Rien ne distingue une variante à l'étude d'une variante déjà envoyée.

### Pourquoi ça compte

Dès qu'un niveau part chez un client, il devient un engagement commercial
daté. Trois conséquences :

- **rien ne prouve ce qui a été proposé**, ni à quel niveau de marché ;
- si le client accepte trois jours plus tard, **aucune référence** ne permet
  de mesurer l'écart entre le niveau proposé et le niveau exécutable — donc
  de décider si on l'absorbe ou si on reprice ;
- deux propositions successives sur le même deal **ne se distinguent pas** :
  la seconde écrase la première.

### Ce qu'il faudrait

Un état `proposée` qui gèle un instantané : prix, données de marché, modèle,
date d'envoi. La variante continue de vivre à côté ; l'instantané ne bouge
plus.

C'est exactement le rôle que joue déjà `rfq_provenance_json` sur un deal
booké — un cliché qui survit à ce qui change après lui.

### Question à trancher avant de coder

Le gel est-il **manuel** (un bouton « marquer comme proposée ») ou
**automatique** au premier export/envoi ? Le manuel laisse passer des oublis ;
l'automatique fige des brouillons exportés pour relecture interne.

---

## 2. Traçabilité à six mois

### État actuel

Une variante porte son **delta** — ce qui change par rapport au parent.
Suffisant pour repricer, insuffisant pour expliquer.

### Ce qui manque

Le **contexte de décision**. Aujourd'hui on voit qu'une barrière d'autocall
est passée de 100 % à 50 %. On ne voit pas :

- ce que valait l'origine ce jour-là, ni sous quelles hypothèses ;
- **les variantes étudiées puis écartées** — or c'est souvent là que se trouve
  la justification ;
- qui a décidé, et quand.

### Pourquoi ça compte

Une restructuration déplace de la valeur entre le client et la banque. Six
mois plus tard, la question « pourquoi avoir sorti ce client d'une note à
46 % pour le remettre sur une autre » doit avoir une réponse **documentée**,
pas reconstruite.

Et la ligne en base a bougé depuis : elle décrit l'état d'aujourd'hui, pas
celui de la décision.

### Ce qu'il faudrait

Un journal d'étude attaché à la filiation : variantes comparées, prix,
hypothèses, date, auteur.

Le comparateur produit **déjà** tous ces éléments. Il ne les archive
simplement pas.

---

## 3. Le coût de débouclage, absent du comparateur

C'est le seul des trois qui **fausse une décision**. Les deux autres font
perdre de l'information.

### État actuel

Sur un roll, le comparateur calcule le nombre d'unités de note neuve achetées
avec le produit du débouclage :

```
k = P₀ / P_neuve
```

où `P₀` est le **prix modèle** de l'origine — le mid
(`backend/app/api/variants.py`, `p0 = origine["price"]`).

### Le problème

On ne déboucle pas au mid. On déboucle au **bid** de l'émetteur, sur une note
illiquide, souvent très en dessous de la barrière — là où l'écart bid-mid est
le plus large. S'y ajoute le coût de débouclage de la couverture.

### L'asymétrie, qui est le vrai piège

Un **avenant** ne traverse aucun spread : le contrat continue, il n'y a rien à
vendre. Un **roll** le traverse une fois à la sortie, et paye une marge à
l'entrée sur la note neuve.

Le comparateur met donc les deux côte à côte **comme s'ils coûtaient la même
chose**. Tout roll paraît structurellement meilleur qu'il ne l'est.

### Ordre de grandeur — deal Marex (IT0006764150)

Origine à 46,16 %, roll à 87 %. Avec une hypothèse de bid 2 points sous le
modèle :

| | mid (comportement actuel) | bid − 2 pts |
|---|---|---|
| plafond de récupération | 53,1 % | 50,8 % |
| performance requise pour le pair d'origine | 188,5 % | 197,0 % |

Deux points de spread coûtent **2,3 points de nominal d'origine** sur le
plafond, et déplacent le seuil de récupération de **8,5 points de
performance**. Ce n'est pas un écart de présentation : c'est ce qui peut
faire basculer la décision entre avenant et roll.

### Ce qu'il faudrait

Une saisie du prix de débouclage — bid observé, ou décote en points sur le
modèle — appliquée au numérateur de `k`, et **affichée en clair** dans le
comparateur à côté du prix modèle.

### Question à trancher avant de coder

Hypothèse saisie à la main, ou donnée de marché récupérée ? La saisie est
immédiate et honnête (on sait que c'est une hypothèse). La récupération
suppose une source de bid secondaire fiable, qui n'existe pas aujourd'hui
dans l'application.

Dans les deux cas, la règle de vérification du projet s'applique : **écrire un
test qui exige que le prix bouge**. Une décote saisissable et sans effet sur le
plafond serait exactement le défaut déjà rencontré avec la courbe de dividende.

---

## Conclusion

| # | Point | Nature du risque | Priorité |
|---|---|---|---|
| 3 | Coût de débouclage | **Fausse une décision** — biais systématique en faveur du roll | Haute |
| 1 | Figer une proposition | Perte de preuve commerciale | Moyenne |
| 2 | Traçabilité | Perte de justification | Moyenne |

Le point 3 est le seul qui produit une recommandation erronée. Les points 1 et
2 se ressemblent — tous deux relèvent de l'archivage d'un instantané — et
gagneraient à être traités ensemble, le second réutilisant le mécanisme de gel
du premier.
