# Scripting assisté par IA — plan d'action

## Le problème n'est pas de générer, c'est de ne pas se tromper en silence

Une IA à qui l'on demande un autocall produit trois familles de résultats :

| | Cas | Détecté par | Gravité |
|---|---|---|---|
| **A** | Ne parse pas | Le parser, immédiatement | Nulle — bruyant |
| **B** | Parse, mais ne décrit pas le produit demandé | **Rien aujourd'hui** | **Maximale** |
| **C** | Parse et décrit le bon produit | — | — |

Le cas B est le seul qui compte. Exemples réels de ce qu'une IA écrit couramment :

- `STOP` oublié → l'autocall ne rappelle jamais, il price, il est faux ;
- `WOF` au lieu de `WOF_MIN` sur une barrière knock-in → barrière européenne au
  lieu d'américaine, plusieurs points de nominal d'écart, aucun symptôme ;
- `PAY 1 + COUPON` au rappel alors que le nominal est déjà payé ailleurs →
  double remboursement ;
- coupon mémoire sans `SET MEMO = INDEX` → mémoire qui ne mémorise rien.

Aucun de ces scripts ne lève quoi que ce soit. Ils sortent un prix.

C'est exactement le fil rouge des audits de ce dépôt — *« le résultat crédible et
faux »* — et `test_garde_fous.py` existe pour ça. **Le plan est donc bâti autour
d'une passe de validation, pas autour de la qualité du prompt.** Un bon prompt
réduit A ; seules des vérifications structurelles attrapent B.

---

## Architecture proposée — 5 couches

```
   IHM  (mode « Assistant IA » dans l'éditeur PayScript)
    │  description en français + choix du moteur
    ▼
   POST /api/script/generate                          ← backend UNIQUEMENT
    │
    ├─ 1. Prompt      référence de langage + exemples ciblés + contexte connu
    ├─ 2. Fournisseur Ollama | OpenAI | Anthropic  (httpx, pas de SDK)
    ├─ 3. Assainir    retire les balises markdown, la prose autour
    ├─ 4. Parser      parse_script() → si échec, boucle de réparation (≤ 2)
    ├─ 5. Contrôles   structurels + pricing de contrôle + profil de probabilités
    ▼
   Retour : script + écho d'intention en français + fiche de contrôle
            → l'utilisateur relit et ADOPTE. Jamais d'application automatique.
```

---

## Couche 0 — La référence de langage (le socle, à faire en premier)

**Constat** : la grammaire PayScript n'existe qu'en Python, dans `parser.py`.
L'application n'a aucune documentation du langage — `DocumentationView` est une
bibliothèque de documents (KID, term sheets), pas une référence.

Si le prompt embarque une copie figée de la grammaire, elle **dérive
silencieusement** dès qu'on touche au langage : le prompt promet une syntaxe que
le parser refuse, et l'IA produit des scripts systématiquement cassés.

**Proposition** : un fichier unique `docs/PAYSCRIPT_REFERENCE.md` qui sert à la
fois de :

- documentation humaine (nouvel onglet dans `DocumentationView` — le manque
  existe déjà, indépendamment de l'IA) ;
- corps du prompt système envoyé au modèle.

**Et surtout, un test anti-dérive** : il extrait du parser le vocabulaire
réellement accepté (`WOF`, `WOF_MIN`, `BOF_MAX`, `BASKET`, `INDIC`, `S_MIN[i]`,
`S_PREV[i]`, `REALVOL`, `FIX_AVG`, `INDEX`, `ACCUM`, `PARAM`, `PARAM()`,
`CONSTAT`, `CONSTAT()`, `SET`, `PAY`, `STOP`, `IF/ELSE`, `AT`, `AT MATURITY`,
qualificatifs `.first`/`.last`/`[N]`…) et vérifie que **chaque mot est documenté
dans la référence, et que la référence n'invente rien**. C'est la décision
structurante du projet : sans ce test, l'assistant se dégrade à chaque évolution
du langage sans que personne ne le voie.

La référence doit aussi porter les **pièges de modélisation**, pas seulement la
syntaxe :

- `WOF` = niveau courant (barrière européenne, observée à la date) ;
  `WOF_MIN` = minimum courant depuis l'origine (barrière américaine, knock-in) ;
- `INDEX` = compteur d'observations, base 1, figé pendant `AT MATURITY` ;
- convention `M_` = paramètre surveillé par la watchlist (direction déduite de
  l'usage) ;
- un `PAY` est un flux **en fraction du nominal** ;
- `STOP` termine le contrat pour cette trajectoire ;
- tout produit doit avoir un `AT MATURITY` qui le solde.

---

## Couche 1 — Les trois fournisseurs

Un protocole minimal côté backend, `backend/app/services/llm/` :

```
LlmProvider.complete(system, user, *, temperature, max_tokens) -> str
```

Trois adaptateurs, tous en `httpx` (déjà une dépendance) — **aucun SDK** :

| Moteur | Endpoint | Clé | Remarque |
|---|---|---|---|
| **Ollama** | `POST localhost:11434/api/chat` | aucune | local, gratuit, hors ligne |
| **ChatGPT** | `POST api.openai.com/v1/chat/completions` | `OPENAI_API_KEY` | |
| **Claude** | `POST api.anthropic.com/v1/messages` | `ANTHROPIC_API_KEY` | en-tête `anthropic-version` |

Éviter les SDK n'est pas de l'idéologie : trois SDK, c'est trois arbres de
dépendances et trois cycles de versions pour trois appels HTTP identiques.

**Les clés reprennent exactement le motif déjà en place pour le secret JWT**
(`api/auth.py`) : variable d'environnement d'abord, fichier dans `data/` ensuite,
refus explicite d'une valeur d'exemple. Jamais en base, **jamais dans le bundle
frontend**.

> Point non négociable : l'appel part du **backend**. Un appel navigateur →
> OpenAI expédierait la clé à chaque utilisateur de l'application.

---

## Couche 2 — Le prompt

**Message système** = rôle (structureur senior) + `PAYSCRIPT_REFERENCE.md` +
règles dures + contrat de sortie.

**Exemples (few-shot)** : les 16 scripts de `payscriptTemplates.js`, qui sont
déjà « la » bibliothèque de référence (partagée avec le module RFQ).

> **Décision d'architecture** : ce fichier est côté frontend, l'appel LLM est
> côté backend. Le déplacer vers `backend/app/core/payscript/templates.py` et
> faire consommer le frontend depuis là (import ou endpoint). Dupliquer une
> « source unique de vérité » est précisément la façon dont elle cesse d'en être
> une — et le module RFQ en dépend aussi.

**Ne pas envoyer les 16.** Sélection par correspondance de mots-clés sur la
demande française (autocall / phoenix / shark / twin win / capital garanti /
reverse convertible…), **3 à 4 exemples**, en incluant toujours un script avec
`STOP` et un avec coupon mémoire. Au-delà, on dilue le signal et on paie des
jetons pour rien.

**Message utilisateur** = la description française **+ le contexte que
l'application connaît déjà** : nombre de sous-jacents, maturité, fréquence
d'observation issue des CONSTAT, devise. Sans ça, l'IA invente des dates.

**Contrat de sortie** — délimiteurs stricts, pas de JSON (les modèles cassent le
JSON dès qu'il contient du code et des sauts de ligne) :

```
===SCRIPT===
<uniquement du PayScript, aucune balise markdown>
===EXPLICATION===
<en français : payoff, dates, barrières, ce qui se passe dans chaque cas>
```

`temperature = 0.1`. Ce n'est pas de l'écriture créative.

---

## Couche 3 — La passe de validation (le cœur)

Enchaînement côté serveur, entièrement automatique :

**1. Assainissement.** Retirer les ` ```payscript `, la prose avant/après.
Les modèles en produisent systématiquement malgré la consigne.

**2. Parsing.** `parse_script()`. En cas d'échec → **boucle de réparation** :
on renvoie au modèle le script fautif *et le message d'erreur exact du parser*
(les 26 messages existants portent le numéro de ligne et sont en français).
**Maximum 2 tentatives**, puis on rend la main avec l'erreur. C'est ici que la
qualité des messages d'erreur du parser se rentabilise.

**3. Contrôles structurels** — calculés sur le script **compilé**, pas sur le
texte. C'est le filet anti-cas-B :

| Contrôle | Déclencheur |
|---|---|
| `has_stop` présent | la demande mentionne rappel / autocall / remboursement anticipé |
| nombre de dates `AT` | cohérent avec fréquence × maturité demandées |
| `AT MATURITY` présent | toujours — un produit doit se solder |
| tout `PARAM` déclaré est utilisé | toujours (sinon : paramètre fantôme) |
| **`WOF` vs `WOF_MIN`** | la demande mentionne une barrière → **afficher explicitement laquelle a été retenue** |
| `SET MEMO` présent | la demande mentionne un coupon à mémoire |
| nombre de sous-jacents référencés | cohérent avec le panier configuré |

Ces contrôles ne bloquent pas : ils **s'affichent**. Un point orange sur
« barrière européenne retenue » alors que le structureur voulait de l'américain,
c'est trente secondes gagnées et un produit mal coté évité.

**4. Pricing de contrôle.** `run_mc` avec un N réduit sur le sous-jacent par
défaut. Trois questions : ça price sans exception ? le prix est-il fini ? est-il
dans une bande plausible (~20–200 % du nominal) ? Un script qui sort 340 % ou
3 % dit quelque chose.

**5. Profil de probabilités.** `run_mc_proba` → taux d'autocall, taux de KI,
durée de vie espérée. Affiché à côté du script : le structureur voit d'un coup
d'œil si le produit se comporte comme ce qu'il a demandé.

---

## Couche 4 — L'IHM

Dans `PayScriptEditor.vue`, un troisième mode à côté de Normal / Expert :
**« Assistant IA »**.

- **Script libre** : un modèle vide ajouté à la liste des 16 — demandé
  explicitement, trivial à faire, à ne pas oublier.
- **Panneau de saisie** : zone de texte française + sélecteur de moteur
  (Ollama / ChatGPT / Claude) + modèle + bouton *Générer*.
- **Panneau de revue**, côte à côte :
  - à gauche le script produit ;
  - à droite l'**écho d'intention** (ce que l'IA dit avoir construit, en
    français), la fiche de contrôle, le prix de contrôle et le profil de
    probabilités.
- **Jamais d'application automatique.** L'utilisateur relit puis clique
  *Adopter dans l'éditeur*. Un script qui atterrit silencieusement dans
  l'éditeur, c'est un produit faux qui part en cotation.
- **Affinage conversationnel** : conserver l'échange, pour que *« non, la
  barrière doit être observée en continu »* raffine au lieu de repartir de zéro.

### L'écho d'intention — ma principale recommandation de conception

Demander au modèle **deux sorties** : le script, et une reformulation française
de ce qu'il a construit. Le structureur compare alors **son français au français
de l'IA** — infiniment plus rapide et plus sûr que de relire du PayScript
généré, surtout pour attraper le cas B.

Coût : quelques lignes de prompt et un panneau. C'est le meilleur rapport
sécurité/effort de tout le projet.

---

## Couche 5 — Traçabilité

Ajouter à la table `scripts` : `ai_provider`, `ai_model`, `ai_prompt`,
`ai_generated_at`, `ai_validated_by`. Sur un desk, il faut pouvoir répondre à
« qui a écrit ce script ». Et **interdire qu'un script non validé humainement
parte en RFQ ou en booking** — le workflow maker-checker existe déjà, il suffit
de raccrocher le drapeau.

---

## Phasage

| Phase | Contenu | Charge | Valeur seule |
|---|---|---|---|
| **0** | `PAYSCRIPT_REFERENCE.md` + test anti-dérive + templates déplacés au backend | ½ j | **Oui** — l'app gagne enfin une doc du langage |
| **1** | Couche fournisseurs + clés + `/api/script/generate` (assainir, parser, réparer) | 1 j | Ollama d'abord : sans clé, gratuit, hors ligne |
| **2** | Passe de validation + écho d'intention | 1 j | C'est là qu'est la sécurité |
| **3** | IHM : mode assistant, script vide, panneau de revue, adoption | 1 j | |
| **4** | Traçabilité + jeu d'évaluation | ½ j | |

**Total ≈ 4 jours.** Les phases 0 à 2 sont utilisables sans IHM (via l'API), et
la phase 0 a de la valeur même si le projet s'arrête là.

### Jeu d'évaluation (phase 4)

Une quinzaine de descriptions françaises → propriétés structurelles attendues
(« doit avoir un STOP », « doit comparer WOF_MIN », « 12 dates d'observation »).
Exécuté contre Ollama en local, il mesure le taux de réussite du prompt et
**empêche qu'une retouche du prompt dégrade silencieusement** l'assistant. C'est
le pendant, côté IA, du test anti-dérive de la phase 0.

---

## Points à arbitrer

1. **Confidentialité.** Envoyer une description de produit à OpenAI ou Anthropic,
   c'est expédier une idée de structuration à un tiers. Ollama en local l'évite
   entièrement. **Recommandation : Ollama par défaut**, cloud en option explicite
   avec un avertissement visible. Sur un desk, ce n'est pas un détail de forme.
2. **Quel modèle local.** Il faut du suivi d'instruction et du code :
   Qwen2.5-Coder 14B ou 32B, ou Llama 3.3 70B si la machine suit. À départager
   avec le jeu d'évaluation de la phase 4 — c'est précisément à ça qu'il sert.
3. **Périmètre de la génération.** Le script seul, ou aussi les paramètres
   (`PARAM`, CONSTAT, sous-jacents) ? Recommandation : **le script seul en
   phase 1**. Laisser l'IA fixer un coupon, c'est lui laisser fixer un prix.

---

## Ce que ce plan ne fait pas

- Il ne laisse pas l'IA **pricer** ni fixer un niveau de coupon : elle écrit une
  structure, le moteur la price.
- Il ne remplace pas la relecture humaine, il la rend rapide.
- Il ne touche ni au moteur Monte-Carlo, ni au parser, ni au langage. La
  référence de langage documente l'existant ; elle ne le change pas.
