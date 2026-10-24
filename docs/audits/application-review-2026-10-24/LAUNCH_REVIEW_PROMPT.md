# Prompt de lancement de la contre-revue de Structura

Copier le bloc ci-dessous dans le chat de l'IA. Si elle n'a pas accès au disque de cette machine, joindre le ZIP au même message : le chemin local seul ne lui donnera pas accès au fichier.

```text
Réalise une contre-revue indépendante de la validité métier et quantitative de Structura à partir de cette archive ZIP :

C:\Users\admin\GitHub\structura\output\structura-application-review-2026-10-24.zip

Si tu as accès à ce chemin, ouvre cette archive. Sinon, utilise le ZIP de même nom joint à mon message. Si aucune de ces deux sources n'est accessible, signale précisément le problème d'accès sans prétendre avoir lu les documents.

Extrais l'archive dans ton espace de travail, lis START_HERE.md, puis lis et applique intégralement annexes/REVIEW_PROMPT.md : ce fichier contient le prompt complet qui définit ta mission, la méthode, les catégories de constats et le livrable attendu.

Examine APPLICATION_REVIEW_2026-10-24.md avec les annexes, les extraits de code, les manifestes et les preuves historiques disponibles. Le rapport est une description à challenger ; il ne constitue pas un oracle. Distingue les vrais défauts, les défauts probables à reproduire, les limites assumées et cohérentes, les limites mal annoncées ou mal appliquées, les conventions métier et les preuves insuffisantes.

Produis le rapport complet en français demandé par annexes/REVIEW_PROMPT.md. Pour les conclusions qui nécessitent des sources absentes du ZIP, indique les fichiers précis et les validations manquantes. Ne présente aucun test proposé comme déjà exécuté.
```
