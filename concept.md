# Synthèse complète du projet — Gestionnaire de sessions IA et de tâches en Rust

Voici la synthèse de conception regroupant les décisions prises ensemble, le périmètre de la V1, l'architecture envisagée, les règles de fonctionnement, la sécurité et les points qui restent à trancher. Elle est organisée pour pouvoir servir de référence lorsque nous reprendrons la conception ou commencerons à rédiger la spécification technique.

## Gestionnaire de sessions IA et de tâches

Nom définitif à choisir · Application Rust · CLI + TUI

Périmètre

MVP équilibré

Agents de la V1

Claude Code + Bash

Stockage

SQLite locale

Service de fond

Rust + systemd --user

## 1. Vision du produit

L'objectif est de construire un environnement de travail quotidien dans le terminal, capable de centraliser :

- la gestion des tâches et des projets ;
- la découverte et l'accès aux dépôts Git ;
- le lancement de plusieurs sessions Claude Code en parallèle ;
- les terminaux Bash classiques pour les interventions manuelles ;
- l'isolation du travail grâce aux Git worktrees ;
- la supervision des sessions, de leur activité et des demandes d'intervention ;
- les notifications, confirmations et historiques ;
- l'intégration avec Claude Code via MCP ;
- une CLI utilisable sans ouvrir l'interface interactive.

L'application ne doit donc être ni un simple lanceur d'agents, ni un simple gestionnaire de tâches. Elle doit constituer un poste de pilotage persistant pour le travail technique, dans lequel les tâches, les dépôts et les sessions sont reliés sans être obligatoirement dépendants les uns des autres.

### Principes fondamentaux

1. Terminal-first : fonctionnement local et via SSH, sans interface graphique obligatoire.
2. Local-first : données conservées sur la machine, sans serveur central imposé.
3. Persistance : fermer le TUI ne doit pas arrêter les sessions.
4. Autonomie encadrée : Claude peut gérer une partie du suivi des tâches, mais les opérations sensibles restent sous contrôle humain.
5. Sécurité par défaut : pas de commandes exécutées aveuglément, pas de fusion automatique, pas de relance automatique des sessions interrompues.
6. Réutilisation des mécanismes natifs : par exemple `claude --resume` pour reprendre une conversation Claude Code.
7. Cœur métier partagé : CLI, TUI et MCP doivent appliquer les mêmes règles.
8. Extensibilité : l'architecture doit permettre d'intégrer d'autres agents sans réécrire l'application.

## 2. Périmètre retenu pour la V1

Tu as choisi un MVP équilibré, suffisamment complet pour devenir un véritable outil de travail quotidien.

| Fonctionnalité                          | Périmètre V1 |
| --------------------------------------- | ------------ |
| Tâches et projets                       | Oui          |
| Découverte automatique des dépôts Git   | Oui          |
| Sessions Claude Code persistantes       | Oui          |
| Terminaux Bash persistants              | Oui          |
| Supervision multi-sessions              | Oui          |
| Git worktrees                           | Oui          |
| Notifications et confirmations          | Oui          |
| CLI                                     | Oui          |
| TUI                                     | Oui          |
| Service utilisateur systemd             | Oui          |
| Base SQLite                             | Oui          |
| MCP essentiel pour Claude Code          | Oui          |
| Politique Git configurable              | Oui          |
| Configuration TOML et assistant initial | Oui          |
| Codex                                   | Plus tard    |
| Packaging Nix                           | Plus tard    |

Le nom définitif de l'application, les commandes exactes et certains choix techniques internes restent à déterminer.

## 3. Architecture générale

### Interfaces

TUI · CLI · Serveur MCP

Socket Unix local

### Service Rust en arrière-plan

Logique métier · Sessions · Notifications · Confirmations · Git

SQLite

Tâches, projets, événements, historique

Adaptateurs

Claude Code, Bash, futurs agents

### 3.1 Les composants

- TUI : interface interactive, tableau de bord et supervision.
- CLI : opérations rapides et automatisables, sans TUI.
- Service Rust : responsable du cycle de vie opérationnel des sessions, des confirmations et des notifications.
- SQLite : source de vérité pour les données métier et l'historique.
- MCP : outils métier exposés aux agents, notamment Claude Code.
- Adaptateurs de sessions : intégration spécifique à chaque type de terminal ou agent.
- Intégration Git : découverte des dépôts, worktrees, branches et détection des conflits identifiables.

Les interfaces ne doivent pas contenir chacune leur propre logique métier : elles appellent les mêmes opérations du cœur de l'application.

### 3.2 Communication entre composants

Le TUI, la CLI et le serveur MCP communiquent avec le service par un socket Unix local, non exposé sur le réseau.

Les permissions du système de fichiers doivent limiter son accès. Le protocole devra également gérer les délais d'attente, les déconnexions, les versions incompatibles et les commandes dont le résultat devient incertain après une perte de connexion.

Si le service est indisponible, la CLI et le TUI affichent une erreur explicite. Ils ne doivent pas supposer que les sessions sont encore actives simplement parce qu'elles sont enregistrées dans SQLite.

### 3.3 Service utilisateur

Le service sera exécuté par `systemd --user`, avec :

- démarrage automatique ;
- redémarrage contrôlé en cas de crash ;
- temporisation progressive entre les tentatives de redémarrage ;
- journaux dans journald ;
- récupération du socket ;
- réconciliation de l'état des sessions ;
- documentation de `linger`, notamment pour le fonctionnement après déconnexion SSH.

Un redémarrage de la machine ne garantit pas la survie des processus Claude ou Bash. La base persiste, mais les processus doivent être vérifiés séparément.

### 3.4 Installations autonomes

Chaque installation possède sa propre configuration, sa base SQLite et ses sessions. Aucune synchronisation entre machines n'est prévue par défaut.

Pour travailler sur un serveur distant, l'application pourra être installée directement sur ce serveur et utilisée via SSH. Les dépôts, credentials, agents et worktrees resteront sur la machine distante.

## 4. Modèle métier : quatre notions distinctes

Le modèle repose sur quatre entités principales : les projets métier, les dépôts Git, les tâches et les sessions.

Elles peuvent être associées entre elles, mais aucune ne doit rendre les autres obligatoires.

### 4.1 Projets métier

Un projet est un espace de travail durable avec :

- un nom ;
- une description ;
- des tâches associées ;
- un ou plusieurs dépôts Git associés ;
- des consignes persistantes pour Claude.

Les consignes peuvent décrire les objectifs du projet, les conventions de code, les contraintes techniques, l'architecture et les vérifications attendues.

Un projet métier n'est pas un dépôt Git. Par exemple, un même projet peut réunir plusieurs dépôts, tandis qu'un dépôt peut être utilisé ponctuellement sans appartenir à un projet enregistré.

### 4.2 Dépôts Git

L'application découvre automatiquement les dépôts dans les racines configurées, par exemple :

- `~/dev`
- `~/Documents/git`
- `~/homelab`

Les dépôts découverts sont utilisables directement pour lancer des sessions. Il n'est pas nécessaire de créer un projet métier pour chacun d'eux.

Fonctions attendues :

- plusieurs racines configurables ;
- rafraîchissement contrôlé de la découverte ;
- détection des dépôts imbriqués et des worktrees sans doublons ;
- affichage du chemin, de la branche et de l'état Git ;
- validation des chemins avant les opérations.

La découverte des dépôts et l'inscription d'un projet métier restent deux opérations distinctes.

### 4.3 Tâches

Une tâche peut être créée dans l'Inbox sans projet, puis enrichie plus tard.

Champs fonctionnels envisagés :

- titre ;
- description ;
- statut ;
- priorité ;
- date d'échéance facultative ;
- projet facultatif ;
- dépôt facultatif ;
- notes de progression ;
- historique des modifications ;
- numéro de version pour le contrôle de concurrence.

#### Statuts retenus

À faire

Tâche enregistrée, travail non commencé

Planifiée

Travail prévu pour plus tard

En cours

Travail actif

Bloquée

Dépendance ou obstacle à résoudre

Terminée

Travail déclaré terminé

#### Priorités retenues

- Urgente
- Haute
- Normale
- Basse

L'application pourra suggérer des changements de priorité en fonction des échéances, blocages ou incohérences. Elle ne modifiera pas automatiquement les priorités : la décision finale appartient à l'utilisateur.

#### Modes de création

Trois parcours doivent être disponibles :

1. création rapide avec le titre seul ;
2. formulaire détaillé ;
3. description en langage naturel, avec confirmation des ambiguïtés avant l'enregistrement.

Ils doivent tous utiliser la même logique métier.

La gestion des tâches récurrentes est exclue de la V1, mais le modèle doit pouvoir évoluer.

### 4.4 Sessions

Chaque session possède un identifiant interne indépendant de l'agent. L'adaptateur conserve en plus les identifiants natifs nécessaires pour retrouver ou reprendre la session.

Une session peut être liée à une tâche, un projet et un dépôt, mais ces associations sont facultatives. Une session Bash pour inspecter un serveur peut donc exister sans aucune tâche.

Le modèle commun devra conserver :

- identifiant interne ;
- type de session et adaptateur ;
- identifiant natif de l'agent, si applicable ;
- nom ou libellé ;
- associations aux projets, tâches et dépôts ;
- répertoire de travail ;
- branche et worktree éventuels ;
- état ;
- dernière activité connue ;
- demandes d'intervention ;
- données nécessaires à la reprise ;
- historique des événements.

L'application doit distinguer les états observés des états inférés. Une session silencieuse n'est pas nécessairement bloquée.

## 5. Gestionnaire de sessions extensible

Tu as retenu un cœur commun avec des adaptateurs spécialisés.

### 5.1 Cœur commun

Il gère les identifiants internes, le cycle de vie, la persistance, les événements, les associations aux tâches et projets, les notifications et l'intégration avec la CLI, le TUI et le MCP.

### 5.2 Adaptateur Claude Code

Fonctions attendues :

- lancer Claude Code dans le répertoire choisi ;
- transmettre le contexte pertinent ;
- conserver l'identifiant natif de session ;
- détecter les états et demandes d'intervention lorsque c'est techniquement possible ;
- reprendre une session avec les mécanismes natifs de Claude Code, notamment `claude --resume <session-id>` lorsque disponible ;
- distinguer la reprise d'une conversation de l'attachement à un processus encore actif.

La reprise exacte devra être validée avec la version réelle de Claude Code. L'application ne doit pas remplacer ni contourner les permissions natives de l'agent.

### 5.3 Adaptateur Bash

Il permet de démarrer un terminal interactif pour effectuer des opérations manuelles :

- administration d'un serveur ;
- inspection des logs ;
- commandes de développement ;
- opérations Git ;
- diagnostics ponctuels.

Il fonctionne sans projet ni tâche et doit rester accessible après la fermeture du TUI, tant que le processus et le backend de terminal existent.

Contrairement à Claude Code, Bash n'a pas de reprise conversationnelle. Sa continuité dépend de la conservation du processus et de son terminal.

### 5.4 Agents futurs

Codex et d'autres agents pourront être ajoutés ultérieurement. Ils ne font pas partie du périmètre fonctionnel de la V1.

Chaque adaptateur doit déclarer les capacités qu'il prend en charge : démarrage, rattachement, reprise native, détection des demandes, arrêt contrôlé, etc. L'interface ne doit jamais promettre une fonctionnalité que l'adaptateur ne sait pas fournir.

## 6. Cycle de vie et supervision des sessions

### 6.1 Le TUI ne possède pas les sessions

Le TUI est un poste de pilotage. Sa fermeture ne doit pas arrêter les processus.

Les sessions sont gérées par le service de fond et retrouvées lors de la prochaine ouverture. L'arrêt d'une session reste une action explicite, distincte de la fermeture du TUI.

### 6.2 Fin, arrêt et reprise

- Une session terminée normalement reste consultable avec son résultat et son historique.
- Une session interrompue ou en erreur reste visible.
- Une session interrompue n'est jamais relancée automatiquement.
- Une reprise est une action explicite et utilise le mécanisme approprié à l'adaptateur.
- Les sessions ne sont ni supprimées ni archivées automatiquement à leur fin.

### 6.3 Réconciliation après crash ou redémarrage

La stratégie choisie est la réconciliation avec récupération explicite :

1. comparer les sessions enregistrées aux processus réellement présents ;
2. rattacher les processus toujours actifs lorsque c'est possible ;
3. marquer les sessions dont le processus a disparu comme interrompues ;
4. indiquer un état inconnu si l'application ne peut pas établir la situation ;
5. proposer une reprise explicite, sans redémarrage automatique.

SQLite conserve l'historique, mais ne constitue pas une preuve de vie d'un processus.

### 6.4 Vue globale des sessions

Tu as choisi une liste globale, avec filtres combinables par :

- projet ;
- dépôt ;
- tâche ;
- agent ou type de terminal ;
- état.

Aucun projet n'est obligatoire. Les sessions Bash indépendantes apparaissent au même titre que les sessions Claude Code.

La vue doit être compacte et comporter un panneau de détails.

La liste affiche notamment le type d'agent, le nom, les associations, l'état, la dernière activité et les interventions nécessaires.

Le détail affiche notamment la branche, le worktree, l'état Git, un aperçu du terminal et les actions adaptées : ouvrir, se rattacher, reprendre, associer à une tâche, arrêter ou consulter le résultat.

L'interface doit rester utilisable dans un terminal SSH de largeur réduite.

## 7. Lancement des sessions et transmission du contexte

### 7.1 Lancement rapide et assistant facultatif

Le lancement est rapide par défaut. Un assistant facultatif permet de personnaliser :

- l'agent ou le type de terminal ;
- la tâche ;
- le projet ;
- le dépôt ;
- le répertoire de travail ;
- le worktree.

Les informations déjà connues sont préremplies. Bash peut être lancé directement sans projet ni tâche.

### 7.2 Choix du répertoire et des worktrees

Lorsqu'une session est lancée depuis un dépôt Git, l'application propose de choisir, selon le contexte :

- le répertoire principal du dépôt ;
- un nouveau worktree avec sa propre branche ;
- un worktree existant approprié.

Si une autre session travaille déjà dans le même dépôt, l'application recommande l'isolation, sans l'imposer systématiquement.

Les worktrees ne sont jamais supprimés automatiquement lorsqu'ils contiennent des changements non commités. Le nettoyage reste explicite ou soumis à des contrôles et confirmations.

### 7.3 Trois niveaux de consignes

Tu as choisi trois niveaux de consignes, composés au lancement :

1. Globales : préférences et attentes générales de travail.
2. Propres au projet : objectifs, conventions, contraintes et vérifications.
3. Propres à la tâche : objectif, critères d'acceptation, description, notes et contraintes ponctuelles.

Le contexte du dépôt est également pris en compte : répertoire de travail, branche, état Git et instructions natives telles que `CLAUDE.md`.

Une règle explicite de résolution des contradictions doit être définie. Les instructions natives du dépôt doivent être prises en compte et ne doivent pas être remplacées silencieusement. Les conflits importants doivent être signalés.

Le contexte est transmis comme de l'information à consulter, jamais comme une commande shell à exécuter aveuglément.

### 7.4 Transmission sans modifier le dépôt

Le contexte du projet, de la tâche et du dépôt est transmis au lancement de Claude sans modifier automatiquement les fichiers du dépôt.

Un export facultatif vers un fichier peut être proposé à la demande. Il ne modifie jamais automatiquement le dépôt.

Une tâche sans projet reste parfaitement utilisable. Seules les informations pertinentes doivent être envoyées à l'agent.

## 8. Autonomie de Claude sur les tâches

Claude pourra interagir avec les tâches via les outils autorisés :

- lire les tâches et projets nécessaires ;
- créer des tâches ;
- ajouter des notes de progression ;
- actualiser l'avancement ;
- modifier le statut ;
- gérer les associations autorisées.

Les suppressions et actions sensibles nécessitent une confirmation explicite.

La fin, le crash ou l'interruption d'une session ne termine jamais automatiquement la tâche associée.

### Historique et concurrence

Chaque modification est historisée avec l'auteur — utilisateur, Claude, CLI, TUI ou MCP —, l'heure, la modification et l'identifiant de session si disponible.

Chaque tâche possède une version incrémentée. Les modifications transmettent la version attendue. Si elle est obsolète, l'opération est rejetée et l'état actuel est renvoyé. Aucun écrasement silencieux n'est autorisé.

Claude doit alors relire les données et décider explicitement comment poursuivre.

## 9. CLI et MCP

### 9.1 CLI

La CLI doit fonctionner sans démarrer le TUI.

Elle permettra notamment de gérer les tâches, projets, dépôts et sessions, ainsi que de diagnostiquer le service. Les noms de commandes, formats de sortie et codes de retour restent à définir.

### 9.2 MCP

Le MCP est une interface métier de première classe, et non un accès général à SQLite.

Les outils prévus concernent :

- la lecture des tâches et projets ;
- la création et la mise à jour des tâches ;
- la modification des statuts ;
- l'ajout de notes ;
- les associations autorisées ;
- la demande de lancement d'une session, dans le respect des règles de l'application.

Les suppressions, arrêts de sessions et opérations Git risquées sont protégés.

Une demande de lancement MCP ne doit pas contourner les permissions natives de Claude Code ni exécuter arbitrairement le texte d'une tâche.

Les réponses MCP doivent rester limitées aux données nécessaires à la requête.

### 9.3 Confirmations en attente

Tu as choisi que les confirmations sensibles restent en attente lorsque le TUI est fermé.

Le service conserve la demande. Elle reste visible dans le centre de notifications et l'opération n'est exécutée qu'après approbation explicite.

L'approbation concerne uniquement l'opération présentée. Si les conditions ont changé depuis la demande, celle-ci doit être revérifiée avant exécution.

## 10. Git, commits et conflits

### 10.1 Politique de commit

La politique Git est configurable globalement et par projet.

Trois modes sont envisagés :

1. aucun commit automatique — valeur par défaut ;
2. proposer un commit après inspection des changements ;
3. automatiser les commits sous des conditions de sécurité explicitement configurées.

Aucune fusion automatique n'est permise.

Les commits automatiques ne sont pas exécutés après une erreur, un crash ou une interruption. L'application doit éviter d'inclure des changements préexistants ou des modifications concurrentes qui ne proviennent pas de la session.

L'isolation par worktree facilite cette séparation, mais ne remplace pas les contrôles.

### 10.2 Conflits entre sessions

L'application privilégie les worktrees distincts lorsque c'est pertinent.

Elle signale les conflits Git qu'elle peut identifier, mais leur résolution reste manuelle. Elle ne prétend pas détecter tous les conflits logiques du code et ne fusionne pas automatiquement les branches.

## 11. Notifications et centre de notifications

Les notifications doivent rester disponibles même lorsque le TUI est fermé, grâce au service de fond.

Elles concernent principalement :

- les demandes d'intervention ;
- les questions et confirmations ;
- les erreurs et interruptions ;
- les fins de session.

Le centre interne conserve l'historique. Les notifications système viennent en complément, si l'environnement les prend en charge.

Deux états doivent être distincts :

- lu ou non lu ;
- résolu ou en attente.

Marquer une notification comme lue ne la supprime pas et ne résout pas la demande associée.

Une fin de session ne termine pas automatiquement la tâche liée.

## 12. Tableau de bord et ergonomie

Tu as choisi un tableau de bord donnant la priorité aux éléments qui demandent ton attention.

Ordre retenu :

1. demandes d'intervention, questions et confirmations ;
2. erreurs et interruptions ;
3. tâches urgentes ou bloquées ;
4. sessions actives ;
5. vue d'ensemble.

Les sections vides sont masquées pour conserver une interface compacte. Des raccourcis permettent d'accéder rapidement aux actions.

### Navigation

La navigation sera hybride :

- flèches directionnelles et `j`/`k` ;
- `Enter` pour ouvrir ;
- `Esc` pour revenir ;
- `/` pour rechercher ;
- raccourcis explicites pour les actions ;
- aide visible à l'écran.

Dans un terminal Claude ou Bash, les touches sont transmises à la session et ne sont pas interceptées par le TUI. Il doit être possible de revenir au tableau de bord sans arrêter la session.

### Écrans envisagés

- Tableau de bord
- Inbox
- Tâches
- Projets
- Dépôts
- Sessions
- Centre de notifications
- Configuration

La disposition exacte et les comportements sur petits terminaux restent à préciser.

## 13. Configuration, installation et distribution

### 13.1 Configuration TOML

Tu as choisi un assistant interactif de première configuration qui crée un fichier TOML modifiable ensuite.

Il demande notamment :

- les racines de découverte des dépôts ;
- le chemin des données locales ;
- le backend de sessions ;
- les préférences de notifications ;
- les préférences d'interface.

L'application doit détecter une configuration existante et éviter de l'écraser à l'insu de l'utilisateur.

La CLI doit permettre de consulter et de modifier la configuration sans relancer l'assistant.

Les valeurs par défaut doivent fonctionner en SSH, sans interface graphique.

### 13.2 Distribution

La première version sera distribuée sous forme d'un binaire Rust autonome dans le `PATH`.

Cela n'exclut pas les dépendances système nécessaires au backend de terminal, à `systemd --user` ou aux notifications. Elles devront être documentées.

Le packaging Nix est prévu ultérieurement, une fois l'application stabilisée.

## 14. Sécurité et confidentialité

Les règles de sécurité retenues sont :

- stockage local des données ;
- aucun serveur central obligatoire ;
- socket local non exposé sur le réseau ;
- permissions du système de fichiers pour protéger le socket ;
- minimisation du contexte transmis aux agents ;
- absence de secrets volontairement stockés dans les notes et consignes ;
- validation des chemins des dépôts et des actions sur les processus ;
- aucune exécution aveugle du contenu des tâches comme commandes shell ;
- confirmation explicite pour les actions sensibles ;
- historique des modifications ;
- contrôle de concurrence sur les mises à jour des tâches ;
- respect des permissions natives des agents.

Limite importante : l'application ne pourra pas empêcher Claude Code de lire des secrets auxquels son propre environnement lui donne déjà accès. La documentation devra expliquer clairement cette limite.

## 15. Récapitulatif des décisions validées

| Domaine                 | Décision                                                               |
| ----------------------- | ---------------------------------------------------------------------- |
| Interface               | CLI + TUI Rust, utilisable en SSH                                      |
| V1                      | MVP équilibré                                                          |
| Agents V1               | Claude Code et Bash                                                    |
| Agents futurs           | Adaptateurs possibles, Codex plus tard                                 |
| Architecture            | Cœur commun et adaptateurs spécialisés                                 |
| Service                 | Rust sous `systemd --user`                                             |
| Communication           | Socket Unix local                                                      |
| Données                 | SQLite locale, migrations et transactions                              |
| Installations           | Autonomes, sans synchronisation par défaut                             |
| Tâches                  | Inbox et vues globales, projet facultatif                              |
| Statuts                 | À faire, planifiée, en cours, bloquée, terminée                        |
| Priorités               | Urgente, haute, normale, basse                                         |
| Suggestions             | Non contraignantes, sans changement automatique                        |
| Contexte                | Consignes globales, projet et tâche, plus contexte du dépôt            |
| Fichiers du dépôt       | Pas de modification automatique ; export facultatif                    |
| Identifiants de session | Internes et indépendants de l'agent                                    |
| Reprise Claude          | Mécanismes natifs, notamment `claude --resume`                         |
| Fermeture du TUI        | Sessions conservées                                                    |
| Redémarrage             | Réconciliation et reprise explicite, jamais automatique                |
| Bash                    | Terminaux classiques persistants                                       |
| Worktrees               | Isolation si pertinente, choix au lancement                            |
| Nettoyage des worktrees | Pas de suppression automatique en présence de changements non commités |
| Commits                 | Politique globale et par projet, aucun automatique par défaut          |
| Fusion                  | Toujours manuelle                                                      |
| Conflits Git            | Détection des conflits identifiables, résolution manuelle              |
| Dashboard               | Interventions, erreurs, tâches urgentes/bloquées, sessions, aperçu     |
| Navigation              | Flèches + `j`/`k`, `Enter`, `Esc`, `/`                                 |
| MCP                     | Outils métier ciblés, écritures encadrées                              |
| Confirmations           | Persistantes et explicites, en attente si TUI fermé                    |
| Concurrence             | Versionnement optimiste des tâches                                     |
| Notifications           | Centre persistant + notifications système si disponibles               |
| Configuration           | TOML et assistant initial                                              |
| Distribution            | Binaire autonome, packaging Nix ultérieur                              |

## 16. Points techniques encore ouverts

Les choix suivants n'ont pas encore été définitivement arrêtés ou validés expérimentalement.

### 16.1 Backend de terminal

`tmux` a été évoqué comme solution possible, mais n'a pas été définitivement choisi.

Il faut comparer :

- l'utilisation de tmux pour conserver et rattacher les sessions ;
- un terminal géré directement par l'application ;
- les conséquences sur le service de fond, la persistance, l'expérience SSH et les dépendances système.

C'est probablement le choix technique le plus structurant encore ouvert.

### 16.2 Reprise native de Claude Code

Il faut vérifier le comportement de la version cible de Claude Code, l'identification fiable des sessions et la distinction entre :

- rattachement à un processus toujours actif ;
- reprise d'une conversation via `claude --resume` ;
- lancement d'une nouvelle session.

### 16.3 Détection des états

Il faut déterminer quels états sont réellement observables de façon fiable : en cours, en attente d'intervention, terminé ou en erreur. L'application devra représenter l'incertitude plutôt que prétendre tout détecter.

### 16.4 Notifications hors TUI

Il reste à préciser les mécanismes de notification disponibles selon l'environnement, notamment en SSH et sur les systèmes sans notifications graphiques.

### 16.5 MCP et confirmations

Il faut détailler la liste des outils MCP, les opérations considérées comme sensibles et le parcours d'approbation. Les confirmations devenues obsolètes doivent être revalidées avant exécution.

### 16.6 Données et suppressions

Le schéma SQLite précis, les relations, les migrations, la conservation de l'historique et le traitement des suppressions restent à définir.

### 16.7 CLI et protocole

Il faut établir les sous-commandes, formats de sortie, codes de retour, protocole du socket et règles d'idempotence.

### 16.8 Commits sûrs

Il reste à définir comment attribuer les changements à une session pour ne pas committer des modifications préexistantes ou concurrentes.

### 16.9 Tests et compatibilité

Il faudra établir les critères d'acceptation et les tests d'intégration portant notamment sur :

- la persistance des sessions ;
- les redémarrages du service ;
- les worktrees ;
- les confirmations ;
- le MCP ;
- la concurrence sur les tâches ;
- les environnements SSH ;
- les dépendances système prises en charge.

## 17. Méthode de travail pour la suite

Le projet est suffisamment cadré pour passer à une synthèse de conception formelle, mais quelques choix techniques doivent encore être résolus.

La suite proposée est :

1. Relire et corriger cette synthèse.
2. Finaliser les décisions fonctionnelles et le périmètre de la V1.
3. Étudier les choix techniques structurants, en commençant par le backend de terminal et la persistance.
4. Rédiger la spécification finale dans un document Markdown, par exemple `docs/superpowers/specs/YYYY-MM-DD-session-task-manager-design.md`.
5. Faire relire et approuver la spécification avant tout développement.
6. Établir ensuite un plan d'implémentation par étapes.
7. Commencer le développement après approbation du plan.

Ce document est une synthèse de conception, pas encore une spécification finale approuvée. Les décisions validées y sont distinguées des points ouverts afin d'éviter de considérer prématurément une hypothèse technique comme un choix définitif.
