# Conception — lancement depuis le tableau (plan 4c)

- Spécification fonctionnelle : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 5.4 (réconciliation), § 6.4 (lancement rapide) et § 6.5 (arrêt et reprise).
- Le plan 4c est rédigé après le merge de la PR #11 (plan 4b) ; ce document fixe la conception validée avec l'auteur le 2026-10-21.

## Intention

Lancer, relancer et récupérer des sessions sans quitter le tableau : `n` refait ce que l'on fait d'habitude dans un dépôt, `N` permet de tout choisir, `r` reprend une conversation Claude terminée, et les panneaux que la base ne connaît pas peuvent être adoptés ou fermés au lieu d'être seulement listés.

## Périmètre (décision de l'auteur, 2026-10-21)

- **Dans le plan 4c** : `n` « dernier type utilisé », le formulaire `N` sans worktree, la reprise `r` (`claude --resume`), les actions sur les panneaux orphelins (adopter, fermer).
- **Reporté au plan 6** : le champ worktree du formulaire (aucun / nouveau / existant) et la recommandation de worktree (§ 6.4) ; la liste « recent sessions to resume ».
- **Reporté (plan 6 ou petit plan 4d)** : la vue Sessions alimentée par tmux seul quand la base est indisponible (§ 16) ; les reports de la 4b (largeur en cellules, `paste-buffer -r`, `quota_lines` et `details_lines` qui ne servent plus qu'aux tests).

## `n` : dernier type utilisé, par dépôt

Décision de l'auteur : le « dernier type » est celui du dépôt.

- Sur un dépôt : le type (`claude` ou `bash`) de la session la plus récente de ce dépôt (plus grand `created_at`, toutes sessions, terminées comprises). Un dépôt sans session lance Claude (§ 6.4).
- Sur une session : on prend son dépôt et la règle ci-dessus ; une session sans dépôt relance son propre type. Le dossier est celui de la session, comme aujourd'hui.
- Rien de nouveau n'est stocké : une fonction pure de `meute.core` décide à partir des sessions déjà chargées par le tableau.
- `c` lance toujours Claude ; Bash reste accessible par `N`.
- L'aide `?` indique ce que fait `n` ; le pied reste `↑↓ select · Enter show · c/n new · x stop · ? keys` (décision 3 du plan, plus sobre que la conception, voir « Écarts »).

## `N` : formulaire de lancement

Décision de l'auteur : un bloc empilé au-dessus du pied du tableau, comme la saisie de la 4b ; la liste reste visible au-dessus.

```
── New session ──────────────────────────────
Type      ◂ Claude ▸
Repo      ◂ meute ▸
Folder    ~/git/meute
Title     
Task      ◂ #12 Fix the bug ▸
Mode      ◂ auto ▸
⚠ another live session works in this folder
Enter launch · Tab next · ←→ choose · Esc cancel
```

- **Ouverture** : `N`, dans l'onglet Sessions, sur la sélection courante (session ou dépôt ; sur une autre ligne, aucun dépôt).
- **Valeurs préremplies** :
  - Type : ce que lancerait `n` ;
  - Repo : le dépôt sélectionné, ou celui de la session sélectionnée ;
  - Folder : le dossier de la session sélectionnée, sinon celui du dépôt ;
  - Title : vide ;
  - Task : la tâche de la session sélectionnée, sinon `none` ;
  - Mode : `claude.permission_mode` de la configuration, à défaut `auto` (§ 6.2).
- **Champs** :

  | Champ | Genre | Valeurs |
  |---|---|---|
  | Type | choix | `Claude`, `Bash` |
  | Repo | choix | dépôts connus, le présélectionné en tête puis par nom ; `none` en dernier |
  | Folder | texte | changer de Repo le remplace par le dossier de ce dépôt (`none` le laisse) |
  | Title | texte | facultatif ; vide = le titre par défaut d'aujourd'hui |
  | Task | choix, Claude seulement | `none`, puis les tâches ouvertes du projet du dépôt, par urgence |
  | Mode | choix, Claude seulement | les modes que la configuration accepte (`config_validate`), `auto` en tête ; les modes risqués en orange, comme dans la fiche |

  Pour Bash, Task et Mode sont masqués (§ 6.3). Une tâche hors du projet se lance par `L` dans l'onglet Tâches.
- **Touches** : `Tab` / `↓` champ suivant, `Shift-Tab` / `↑` champ précédent, `←` / `→` changent un choix, les caractères (et `Backspace`) éditent un champ texte, `Entrée` lance, `Échap` annule. Tant qu'il est ouvert, le formulaire prend toutes les touches ; un clic ailleurs ne lui vole pas le focus (correctif de la 4b).
- **Avertissement** : si une autre session vivante a le même dossier (chemins résolus), la ligne `⚠ another live session works in this folder` s'affiche ; elle n'empêche rien. La recommandation de worktree vient au plan 6.
- **Validation** : un dossier vide ou inexistant affiche l'erreur sous les champs et bloque le lancement.
- **Lancement** : en cas d'échec, le formulaire reste ouvert avec la saisie et l'erreur (comme `M-t`) ; en cas de succès, il se ferme et la nouvelle session est affichée dans la zone principale.
- **Lancement avec une tâche** (décision de l'auteur, 2026-10-21, voir « Écarts ») : comme `L`, Claude démarre dans le dossier du formulaire, avec son titre et son mode, lié à la tâche ; une fois `SessionStart` reçu, le texte de la tâche est collé sans être envoyé. Le lancement tourne dans `BoardWorkers` ; pendant ce temps le formulaire reste ouvert et ignore toutes les touches (un second `Entrée` ne lance rien). Sans tâche, le lancement reste immédiat.
- **Taille** : 8 à 9 lignes ; il tient en mode étroit.
- **Textes** : tout ce qui vient de la base ou du disque (titres, noms de dépôt, dossiers) passe par `printable` / `one_line`, et la largeur est celle du tableau (`fit`).

## `r` : reprise d'une session Claude terminée

Décision de l'auteur : la touche `r`, sans confirmation (rien n'est détruit).

- `r` n'agit que sur une session Claude terminée (`Exited` ou `Unreachable`) dont le `native_id` est connu. Sinon le pied explique : `"<titre>" cannot be resumed: Claude never confirmed its id`, `only Claude sessions resume`, ou `"<titre>" is still running`.
- **Panneau** : si la session a gardé son panneau mort, `respawn-pane` (sans `-k`, voir « Écarts ») y relance la commande (même place à l'écran) ; sinon un nouveau panneau est ouvert dans `meute-bg`, comme un lancement.
- **Commande** : celle d'un lancement Claude normal (`MEUTE_SESSION=<même id>`, `--settings`, `--permission-mode` d'origine, `-n <titre>`), avec `--resume <native_id>` à la place de `--session-id`. Le mode d'origine est le dernier `permission_mode` connu de la session, à défaut celui de la configuration.
- **Base** : la session redevient vivante (`unknown`, puis `SessionStart` prend le relais), `exit_code` et `ended_at` sont effacés ; l'`id` interne, le dépôt, la tâche, le projet et le titre sont conservés (§ 6.5). La réconciliation ne ressuscite toujours rien d'elle-même : seule l'action `r` le fait.
- **Concurrence** : un second `r` pendant que la reprise tourne ne fait rien (comme `x`).
- **Erreurs** : un dossier disparu ou un lancement qui échoue laissent l'état de la session inchangé et affichent l'erreur dans le pied.
- `Entrée` sur une session terminée sans panneau affiche désormais `"<titre>" has ended: r resumes · c starts a new session` (Claude) ; le texte d'une session Bash reste celui d'aujourd'hui.

### Spike S10, au début du plan

Avec le vrai Claude, seulement avec l'accord explicite de l'auteur, sur un serveur tmux jetable :

- `claude --resume <id>` lancé avec nos options garde-t-il le même `session_id` ?
- Le hook `SessionStart` arrive-t-il (avec `source=resume`) et porte-t-il `MEUTE_SESSION` ?
- `--settings`, `-n` et `--permission-mode` sont-ils acceptés avec `--resume` ?

Si l'identifiant change, meute enregistre le nouveau `native_id` reçu par `SessionStart` (`apply_hook` l'accepte déjà grâce à `rebinds`). Le résultat est consigné dans `docs/superpowers/spikes/`.

## Panneaux orphelins

Un orphelin est un panneau qui porte un `@meute_id` inconnu de la base (§ 5.4).

- **Relevé** : le relevé tmux lit `pane_dead` avec les huit champs inchangés ; la commande et le dossier de chaque orphelin sont lus à part (`display-message -p -t <pane>`, décision 4 du plan). Le relevé renvoie des `Orphan(meute_id, pane_id, command, cwd, dead)` en plus des identifiants (`Snapshot.orphan_panes`, voir « Écarts ») ; `meute session list --json` garde la liste d'identifiants.
- **Affichage** : la section « Orphans » devient sélectionnable, une ligne par panneau : `? claude  ~/git/meute  orphan` (`dead` pour un panneau mort).
- **Touches** sur un orphelin :

  | Touche | Effet |
  |---|---|
  | `Entrée` | affiche le panneau dans la zone principale (refusé pour un panneau mort) |
  | `a` | adopte (sur un orphelin sélectionné ; ailleurs `a` reste le filtre « attention ») |
  | `x` | ferme, avec la confirmation `y` de l'arrêt |

  Le pied devient `Enter show · a adopt · x close`. Les autres touches de session (`c`, `n`, `N`, `r`) n'agissent pas sur un orphelin.
- **Adopter** crée la session en base :
  - `id` : le `@meute_id` ; refusé s'il n'a pas 36 caractères (`not a meute id: only x closes it`) ;
  - type : `claude` si la commande du panneau est `claude`, sinon `bash` ;
  - dossier : celui du panneau ; dépôt : le dépôt connu dont le chemin contient le dossier (le plus long), sinon aucun ;
  - titre : le nom du dossier ;
  - état : `running` pour Bash ; `unknown` pour Claude jusqu'au hook suivant, qui donnera aussi le `native_id` (le panneau porte déjà `MEUTE_SESSION=<id>`, et `apply_hook` accepte un `native_id` tant qu'aucun n'est connu) ;
  - un panneau mort ne s'adopte pas, ni un panneau dont le dossier n'est pas un chemin absolu (`unknown folder: only x closes it` : tmux peut renvoyer un dossier vide) ; un `id` déjà en base (adopté entre-temps ailleurs) ne fait rien, la session apparaît au relevé suivant.
- **Fermer** suit la séquence de l'arrêt (`C-c` deux fois pour Claude, une fois pour Bash, puis `kill-pane` après 5 s), sans rien écrire en base. Un panneau déjà disparu ne fait rien.

## Architecture

- **`meute.core`** (pur, stdlib) :
  - `last_agent(sessions, repo_id) -> AgentKind` et l'action de `n` ;
  - `launch_form.py` : l'état figé du formulaire et ses transitions (`move`, `choose`, `type_text`, `validate`, `to_action`) ;
  - `resume_target(entry) -> Session | str` (la session à reprendre, ou le texte du refus) ;
  - `Orphan` et `adoption(orphan, repos) -> NewSession | str` (la session à créer, ou le texte du refus).
- **Actions du tableau** : `LaunchBash` et `LaunchClaude` gardent leur nom et gagnent des champs facultatifs (`title` ; `task_id` et `permission_mode` pour Claude), décision 1 du plan ; `ResumeSession(session_id)`, `ShowPane(pane_id)`, `AdoptOrphan(orphan)`, `CloseOrphan(meute_id, agent)`.
- **`meute.tmux`** : relevé enrichi ; `respawn_pane` ; la fermeture réutilise la séquence d'arrêt.
- **`meute.cli`** : `resume_claude` (même construction de commande que `launch_claude`) ; l'adoption écrit en base et refuse un `id` existant ; reprise et fermeture tournent dans `BoardWorkers`, comme l'arrêt et `L`.
- **`meute.tui`** : le bloc du formulaire dans l'onglet Sessions (même mécanique de capture des touches que `task_input`) ; les lignes orphelines sélectionnables dans `sessions_cursor`.

## Erreurs

- Les refus (pas de `native_id`, orphelin non adoptable, panneau mort) sont des textes du pied, jamais des exceptions.
- Les erreurs de lancement, de reprise et de tmux passent par le mécanisme d'erreur du backend (`MeuteError` affichée dans le pied) ; le formulaire garde alors sa saisie.
- Une session ou un panneau qui disparaît entre l'affichage et l'action donne une erreur lisible, sans état écrit à moitié (transaction).

## Tests

- **Cœur** : fonctions pures, `hypothesis` pour les transitions du formulaire (aucune suite de touches ne sort d'un état valide), instantanés `syrupy` du bloc du formulaire et des lignes orphelines.
- **Backend** : serveur tmux jetable avec le faux `claude` ; reprise avec panneau mort (`respawn-pane`) et sans panneau ; panneau marqué à la main pour l'adoption et la fermeture.
- **TUI** : faux backend, instantanés `pytest-textual-snapshot` du formulaire à 60, 72 et 100 colonnes.
- Le vrai Claude n'est lancé que pour le spike S10, avec l'accord de l'auteur.

## Points d'attention pour la relecture

- Un `@meute_id` reçu de tmux est une entrée externe : validé avant toute écriture, et affiché par `printable`.
- Le chemin du panneau et la commande peuvent contenir n'importe quoi (`;` final, caractères de contrôle) : `literal_word` pour tmux, `printable` à l'affichage.
- Le formulaire ne doit jamais perdre la saisie sur une relecture du tableau ou un conflit.

## Écarts à la conception, relevés à la mise en œuvre (plan 4c)

Les décisions 1 à 8 du plan et les arbitrages du contrôleur ajustent ce document :

- **Décision 1 : pas d'action `Launch` unique.** `LaunchBash` et `LaunchClaude` restent, avec des champs facultatifs ; même effet, et les tests qui les construisent restent valables.
- **Décision 3 : pied inchangé.** `FOOTER` ne change pas ; seul l'aide `?` dit ce que fait `n`. Sur un orphelin, le pied devient `Enter show · a adopt · x close`, et une notice `orphan pane: Enter show · a adopt · x close` répond à `c`, `n`, `r`.
- **Décision 4 : détail des orphelins lu à part.** `PANE_FORMAT` ne change pas ; un `display-message -p -t <pane> "#{pane_current_command}\t#{pane_current_path}"` par panneau orphelin seulement. Un panneau absent répond avec des champs vides : l'orphelin est alors omis (R8).
- **Décision 5 : `meute session list --json`** garde `"orphans"` en liste d'identifiants, et la sortie texte `orphan: <id>` ne change pas. En conséquence, `Snapshot.orphans` reste un tuple d'identifiants et un nouveau `Snapshot.orphan_panes` porte les `Orphan` du tableau (R7).
- **Décision 7 : projet d'un dépôt** (tâches proposées par le formulaire) : le projet lié par `project_repos` (le plus petit identifiant), à défaut le projet qui porte le nom du dépôt, à défaut aucun (Task : `none` seulement).
- **Décision 8 : dossier saisi** : `~` développé, espaces de début et de fin retirés, chemin absolu (`folder must be absolute: <texte>`) puis existant (`folder not found: <texte>`) ; un dossier vide donne `folder is empty` (R15).
- **R3 : aide `?`.** La ligne de `KEYS_HELP` du plan dépassait 58 colonnes ; elle est coupée en deux lignes de mots identiques pour rester lisible à 60 colonnes.
- **R4 : `respawn-pane` sans `-k`.** Avec `-k`, deux reprises simultanées passent toutes deux le test « panneau mort » et la seconde tue le Claude de la première. Sans `-k`, tmux refuse lui-même un panneau vivant. Pas de `-c <cwd>` non plus (R5) : la commande fait déjà `cd -- "$1"`.
- **R12 : `a`** adopte quand la sélection est un orphelin, et reste le filtre « attention » ailleurs.
- **R14 : l'avertissement du formulaire** compte aussi le dossier de la session vivante sélectionnée : la nouvelle session le partagerait.
- **R1 : `N` sur un orphelin** se comporte comme sans sélection (aucun dépôt ni dossier préremplis).
- **Adoption** : l'`id` doit être canonique (36 caractères, minuscules), car la réconciliation compare le tag exactement ; `IntegrityError` seul est traité comme « déjà en base ».
- **Décision de l'auteur (2026-10-21) : une tâche choisie dans `N` se lance comme `L`.** Le formulaire envoie `LaunchClaude` avec `task_id` à un worker de `BoardWorkers` ; le backend passe alors par `launch_claude_on_task` (même attente de `SessionStart` et même collage par un fichier privé 0600 et un tampon tmux que `launch_on_task`, code partagé). Le formulaire reste ouvert et ignore les touches pendant le lancement, se ferme au succès (ou sur `prompt not pasted`, dit dans le pied), et garde saisie et erreur sur une `MeuteError`.
- **Adoption, relecture finale** : un orphelin dont le dossier n'est pas absolu (vide, relatif) est refusé (`unknown folder: only x closes it`), au lieu d'enregistrer un chemin relatif.
- **Arrêt de la session affichée** (demande de l'auteur, 2026-10-21) : `x` puis `y` sur la session de la zone principale (ou `meute session stop`) y affiche la session vivante suivante dans l'ordre du tableau, en revenant au début, au lieu de l'accueil ; l'accueil revient seulement quand aucune autre session ne vit. Fermer un orphelin affiché fait de même (première session vivante du tableau). Arrêter une session en arrière-plan ne change pas l'écran. Règle dans `next_live` (`core/attention.py`), ordre et affichage dans `cli/session_next.py`.
