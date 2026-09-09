# Vidéo de démonstration STRUCTURA

Outillage **isolé** de production de `structura-ai-demo.mp4`. Rien ici n'est
importé par l'application : `demo-video/` peut être supprimé sans conséquence.

## Régénérer la vidéo

Prérequis : le serveur STRUCTURA doit tourner sur `http://localhost:8000`
(`backend/run.py`), Ollama doit être démarré avec `qwen2.5-coder:14b` installé,
et `ffmpeg` doit être sur le PATH.

```bash
cd demo-video
npm install && npx playwright install chromium   # première fois seulement
node record-cards.mjs      # scènes 1, 2, 8 — cartons animés
node make-captions.mjs     # sous-titres en PNG transparents
node record.mjs            # scènes 3 à 7 — tournage dans l'application réelle
node assemble.mjs          # montage ffmpeg -> structura-ai-demo.mp4
```

Compter une dizaine de minutes, dont ~3 min pour la seule génération du script
par le modèle.

## Ce que fait chaque étape

| Fichier | Rôle |
|---|---|
| `cards/*.html` | Scènes graphiques (intro, architecture, clôture). Chaque page joue sa propre conduite et pose `window.__done`. |
| `record-cards.mjs` | Enregistre ces pages en 1920×1080. |
| `make-captions.mjs` | Rend les sous-titres en PNG transparents, avec les polices de la marque. |
| `lib/studio.mjs` | Curseur synthétique, déplacements lisibles, cadres de mise en évidence, repères de montage. |
| `scout.mjs` | Repérage : ne filme rien, capture les écrans et liste les libellés cliquables. À relancer si l'interface change. |
| `record.mjs` | La prise dans l'application réelle. Écrit `build/raw/app.webm` et `build/marks.json`. |
| `assemble.mjs` | Découpe selon les repères, incruste les sous-titres, concatène, encode. |

## Règle de production

Tout ce qui est montré à partir de la scène 3 est l'application réelle, pilotée
en direct. Le script, le prix, les Greeks et l'échéancier sont produits par le
moteur pendant la prise.

La **seule** liberté prise au montage est de raccourcir les attentes : le modèle
met environ 166 s à écrire le script, le montage garde le clic et le résultat,
pas l'attente. Le résultat affiché est bien celui que ce clic a produit.

Si l'interface change et qu'un sélecteur ne répond plus, relancer `scout.mjs`
avant de corriger `record.mjs` — les sélecteurs y sont écrits d'après des faits,
pas d'après des suppositions.

## Ce qui n'est jamais filmé

Les écrans Clients, Booking, RFQ et AMC portent des données réelles. Ils sont
hors du parcours filmé, et doivent le rester.

Le *Mode Démo* de l'application (`frontend/src/stores/demoMode.js`) n'est pas
utilisé ici : il masque les prix et floute le script (`••••••`), ce qui est
l'inverse du besoin d'une vidéo de démonstration. Il reste l'outil correct pour
une capture d'écran où les chiffres doivent disparaître.
