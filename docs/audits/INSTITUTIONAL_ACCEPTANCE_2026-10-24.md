# Recette institutionnelle 100 M EUR — 24 octobre 2026

**Suivi :** les trois défauts majeurs IA-01/02/03 sont corrigés et rejoués dans la
[mission de correction](INSTITUTIONAL_MAJOR_FIXES_2026-10-24.md). Les observations
ci-dessous restent celles de l'audit initial.

Mission exécutée sur deux installations fictives isolées. Les données privées de
`backend/data/structura.db` n'ont pas été utilisées. Aucun code applicatif modifié par cette mission,
aucun commit ni push.

Les douze achats du portefeuille, 36 offres et six banques fictives ont été
exercés dans l'UI pour les cotations, allocations, revues et bookings ; les
structures/calculs initiaux et confirmations externes fictives ont été préparés
par API. Les montants investis totalisent 86 M EUR de nominal, 84 927 750 EUR de
souscriptions et 172 000 EUR de frais dans le ledger indépendant. Le minimum de
cash simulé est 14 900 250 EUR. Ce ledger externe ne qualifie pas une trésorerie
native de Structura.

169 tests backend ciblés passent, ainsi que 26 oracles quantitatifs et 12
rapprochements de montants de payoff. Quatre sondes d'observation hors grille
échouent. Une sonde OTC, dans l'autre organisation, accepte un Deal sans accord
effectif ; les douze contrôles CCR historiques emploient la date système. Les
réserves de cash, groupe, chemin officiel américain et portail investisseur
restent distinctes des bugs prouvés.

**Le mandat institutionnel autonome n'est pas qualifié.** Les RFQ à prix fixe et
le lifecycle de notes à observations ponctuelles sont exploitables sous les
restrictions détaillées dans le dossier local. Le contrôle OTC et le reporting
financier autonome ne sont pas exploitables dans ce périmètre.

Le [rapport exécutif](../../output/structura-institutional-audit-2026-10-24-1955/EXECUTIVE_REPORT_FR.md),
le [rapport détaillé](../../output/structura-institutional-audit-2026-10-24-1955/DETAILED_REPORT_FR.md)
et le [catalogue de preuves](../../output/structura-institutional-audit-2026-10-24-1955/README_FR.md)
conservent tous les résultats, refus et limites de couverture. L'arrêt des
processus et des ports est vérifié dans DELIVERY_VERIFICATION.json.

Sept fichiers du checkout ont évolué pendant l'audit hors de cette mission.
Leurs empreintes sont conservées dans `evidence/checkout-drift.json`. Les
sources des principaux constats restent identiques ; les tests datés ne
constituent pas une validation globale du dernier checkout.
