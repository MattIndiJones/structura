# Reprise du launcher et du workspace Admin — 24/10/2026

Travail local sur `codex/hybrid-saas-foundation`, sans commit ni push.

## Cause

Le bouton « Entrer dans Structura » lançait le serveur, qui quittait pendant
`admin_workbench.preflight`, avant toute migration. Le journal privé indiquait :
« Base Admin occupée sans identité attestée ; provisionnement explicite requis
avant toute migration. » Le launcher affichait seulement la sortie du serveur.

Le workspace permanent avait été initialisé avant C02. Il conservait son compte
Admin et ses référentiels, mais aucune table `admin_workbench_identity`. Ce cas
était explicitement laissé à reprendre dans la livraison C02. La protection ne
doit pas être supprimée : reconnaître seulement un compte nommé `admin`
permettrait d'adopter une base étrangère.

## Correctif

L'outil `scripts/adopt_admin_workbench.py` propose un inventaire en lecture seule,
puis une application explicitement liée à l'identifiant du manifeste, à l'empreinte
SHA-256 de la base inventoriée et à un motif de provisionnement.

Cette procédure est volontairement limitée au bootstrap historique à un seul
compte Admin actif, à son organisation canonique et à son secret privé de bootstrap
encore concordant. Elle contrôle le schéma, l'intégrité SQLite, l'absence
d'identité métier ou d'identité déjà attestée, le verrou du service et son port.
Elle refuse les journaux SQLite non résorbés et les comptes modifiés ou multiples,
qui demandent une expertise distincte. Le manifeste est relu sans cache.

Sous verrou système et transaction SQLite, la procédure conserve une sauvegarde
des octets originaux, en vérifie l'empreinte et inscrit ensemble l'identité et
l'audit `ADMIN_WORKBENCH_ADOPTED`. Un échec de l'audit annule l'identité. Elle ne
modifie ni mot de passe, ni rôle, ni statut du compte, ni dossier métier. Les
migrations normales s'exécutent ensuite par le chemin habituel de démarrage.
Aucune adoption automatique n'a été ajoutée au launcher ou au preflight.

Deux fixtures de sécurité C02 fixent désormais aussi `_DB_PATH` sur leur base
isolée : elles ne doivent pas passer ou échouer à cause du marqueur de retrait
de `backend/data` au lieu d'exercer le contrôle d'identité visé.

## Utilisation de l'outil

Depuis la racine, installation arrêtée :

```powershell
.venv/Scripts/python.exe scripts/adopt_admin_workbench.py .runtime/hybrid-saas/admin-workbench/installation.json
```

Après vérification de l'identité et de l'empreinte retournées :

```powershell
.venv/Scripts/python.exe scripts/adopt_admin_workbench.py .runtime/hybrid-saas/admin-workbench/installation.json --apply --installation-id <identite-verifiee> --expected-sha256 <empreinte-inventoriee> --reason "Motif explicite du provisionnement"
```

L'application a été effectuée sur le workspace du raccourci dans cette
intervention, après validation isolée. Il n'est pas nécessaire de la refaire.
Une nouvelle tentative sur une base déjà attestée est refusée sans modification.
Les JWT antérieurs à C02 nécessitent une nouvelle connexion ; l'accès développeur
du launcher ouvre une session actuelle.

## Validation et preuves

Résultats détaillés dans [la preuve du correctif](remediation-lot-0-2026-10-20/LAUNCHER_RECOVERY_VALIDATION.json).
Les journaux, JUnit, inventaires et sauvegardes privées restent sous
`.runtime/diagnostic-acceptance/launcher-2026-10-24` et dans le répertoire
`admin-workbench/backups`. Aucun secret ou contenu privé n'est joint aux preuves
documentaires.

La recette démarre réellement l'Admin et le portail par `Launcher.launch`,
vérifie la session développeur Admin et les lectures métier, puis réutilise les
services au second lancement. Les services créés pour les contrôles sont arrêtés
avec vérification des identités, de leur sortie et de la libération des ports.
Aucun agent IA n'est lancé.

Cette reprise couvre le bootstrap historique précis identifié sur ce poste.
Elle ne qualifie pas l'adoption d'autres anciennes installations, des mots de
passe déjà remplacés, des workspaces multi-utilisateurs ou un déploiement distant.
La suite backend complète et la recette visuelle de la fenêtre Tkinter ne sont
pas relancées ; aucun fichier Vue n'a été modifié.
