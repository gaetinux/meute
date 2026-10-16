# Conception — migration de meute de Rust à Python

- Date : 2026-10-16
- Spécification fonctionnelle : `docs/superpowers/specs/2026-10-15-meute-design.md`
- Feuille de route : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`

## 1. Décision et objectif

meute passe de Rust à Python. L'auteur maîtrise Python et non Rust ; il doit pouvoir comprendre et relire le code, même si Claude l'écrit.

**Critère de réussite** : à la fin de la migration, l'auteur lit la spécification, le guide de développement et le plan 1 Python, et peut superviser des sous-agents qui écrivent du code qu'il comprend.

### 1.1 Ce qui ne change pas

- La spécification fonctionnelle (§ 1–3, 5–13, 15–16 sur le fond), les spikes S1–S5 et le découpage en six plans.
- La méthode : TDD strict, ne jamais toucher un test pour le faire passer, vérification complète avant « terminé », hooks `.claude/`, une branche et une PR par plan, exécution par sous-agents superpowers.

### 1.2 Ce qui change en plus de la langue de programmation

- **Interface en anglais** (CLI, TUI, erreurs, statusline), au lieu du français. Pas de traduction pour l'instant ; `gettext` pourra être ajouté plus tard.
- **Documentation** : README en anglais. Spécification, plans et guide de développement restent en français.
- **Messages de commit et titres de PR en anglais.**
- Le code, les identifiants et les commentaires restent en anglais.

## 2. Préservation du code Rust (fait)

- Le travail du plan 2 en Rust (11 commits non mergés et le TUI ratatui inachevé) est commité sur `feat/plan-2-tmux-sessions-bash`, tagué `rust-plan-2-wip` et poussé. La branche n'est pas mergée.
- `main` est tagué `rust-plan-1`.
- La migration se fait sur `chore/python-migration`, créée depuis `main`.
- Les deux tags servent de **référence de comportement** : les tests Rust et le rapport de mutants du plan 1 pour le nouveau plan 1, le code du plan 2 pour le futur plan 2.

## 3. Architecture Python

### 3.1 Un paquet, plusieurs packages

Un seul paquet `meute`, en disposition `src/meute/`, géré par uv (`uv.lock` commité). Python 3.13, fixé par `.python-version` et `requires-python = ">=3.13"`. Distribution : `uv tool install meute` ; un binaire unique via PyApp plus tard si besoin. Pas de PyInstaller onefile, qui décompresse à chaque lancement.

| Package | Rôle | Peut importer |
|---|---|---|
| `meute.core` | Modèle, règles, SQLite et migrations (fichiers SQL numérotés, sans ORM), saisie rapide, lecture de la configuration (`tomllib`), chemins XDG, modèles de vue | stdlib uniquement |
| `meute.ingest` | `ingest hook` et `ingest statusline` : le chemin chaud | `meute.core`, stdlib |
| `meute.tmux` | Pilotage de tmux via `subprocess` | stdlib uniquement |
| `meute.git` | Découverte des dépôts et worktrees | stdlib uniquement |
| `meute.claude` | Ligne de commande Claude, fichiers `--settings` et `--mcp-config`, interprétation des hooks et de la statusline | `meute.core` |
| `meute.tui` | Écrans Textual | `meute.core`, `textual` |
| `meute.mcp` | Serveur MCP (SDK officiel `mcp`, asynchrone) | `meute.core`, `mcp` |
| `meute.cli` | Typer, assemblage des packages, `config_edit` (`tomlkit`, pour `meute config set` qui préserve les commentaires) | tous |
| `meute._entry` | Point d'entrée : dispatche sur `sys.argv` | `meute.ingest`, `meute.cli` (imports paresseux) |

### 3.2 Règles de dépendances (vérifiées par import-linter)

- `meute.core`, `meute.tmux` et `meute.git` sont indépendants les uns des autres. L'assemblage, par exemple la réconciliation des sessions avec les panneaux, se fait dans `meute.cli`.
- `meute.tui`, `meute.mcp` et `meute.claude` sont indépendants les uns des autres.
- Seul `meute.cli` importe `typer` et `tomlkit`, seul `meute.tui` importe `textual`, seul `meute.mcp` importe `mcp`.
- `meute.core`, `meute.tmux` et `meute.git` n'importent que la stdlib.
- `meute.ingest` et `meute._entry` n'importent ni `typer`, ni `textual`, ni `mcp`, ni `meute.cli` (en dehors de l'import paresseux de `_entry`).

**Pourquoi un cœur limité à la stdlib** : `ingest` réutilise le vrai modèle sans dupliquer de règle, le cœur reste rapide à importer et lisible sans connaître de bibliothèque tierce. Le prix : validation écrite à la main dans les dataclasses (pas de pydantic), chemins XDG codés à la main, écriture du TOML hors du cœur. La règle peut être relâchée plus tard ; import-linter rend ce choix explicite et le test `importtime` en montre le coût.

### 3.3 Démarrage rapide de `ingest` (spécification § 7.3 : moins de 50 ms)

Le script `meute = "meute._entry:main"` regarde `sys.argv[1]`. Pour `ingest`, il importe `meute.ingest` ; sinon il importe `meute.cli`, qui charge Typer (environ 100 ms à lui seul). La commande reste `meute ingest hook <event>`, comme le prévoit la spécification.

Deux garde-fous permanents :

- les contrats import-linter du § 3.2 ;
- un test qui lance `python -X importtime -m meute ingest hook …` dans un sous-processus et échoue si un module importé n'appartient ni à la stdlib ni à `meute.*`. Un test chronométré serait trop instable en CI.

Repli si le spike S6 échoue : `ingest` écrit dans un fichier tampon, intégré en base par le TUI (§ 6).

### 3.4 Code synchrone

Le code est synchrone par défaut. L'asynchrone n'apparaît que là où Textual ou le SDK MCP l'imposent, c'est-à-dire dans `meute.tui` et `meute.mcp`.

### 3.5 Erreurs

Des exceptions typées remplacent `thiserror` et `anyhow` : une hiérarchie `MeuteError` dans `meute.core`, des sous-classes par cas, avec des données attachées, par exemple `VersionConflict` qui porte l'état courant de la tâche (spécification § 9.2). La CLI les traduit en messages et en codes de sortie. Le chemin `ingest` attrape tout, écrit dans `ingest.log` et sort avec le code 0 (spécification § 7.3).

## 4. Typage et lints

| Règle Rust | Équivalent Python | Outil |
|---|---|---|
| Vérification des types | `typeCheckingMode = "strict"` | basedpyright |
| Pas de `_ =>` sur nos enums | `reportMatchNotExhaustive = "error"`, pas de `case _:` sur nos types, sauf `case _: assert_never(x)` | basedpyright, test de garde |
| Enums porteuses de données | Union de dataclasses gelées : `TaskStatus = Todo \| InProgress \| Blocked \| Review \| Done`, avec `Blocked(reason: str)` ; `enum.Enum` pour les enums simples (`Priority`) | basedpyright |
| `TaskId(i64)` | `TaskId = NewType("TaskId", int)` | basedpyright |
| Données immuables | `@dataclass(frozen=True, slots=True, kw_only=True)` | — |
| Pas de `Any` | `reportAny`, `reportExplicitAny`, `ANN401` ; `typing.cast` interdit (`TID251`) | basedpyright, ruff |
| `unwrap`/`expect` interdits | Pas d'`assert` hors des tests (`S101`) ; pas de `except:` nu ni de `except Exception` qui avale tout (`E722`, `BLE001`, `S110`) | ruff |
| `todo!`, `dbg!` | `FIX`, `T100`, `ERA` | ruff |
| Pas de `print` dans les bibliothèques | `T20` sur `meute.core`, `meute.tmux`, `meute.git` et `meute.claude` | ruff |
| `unsafe` interdit | `S` (bandit) : pas d'`eval`/`exec`, de `pickle`, ni de `subprocess(shell=True)` | ruff |
| `missing_docs` sur le cœur | `D` (convention Google) sur `meute.core` | ruff |
| `#[expect(lint, reason)]` | Une exception ne vise qu'une règle précise (`PGH003`, `PGH004`, `reportIgnoreCommentWithoutRule`) ; `reportUnnecessaryTypeIgnoreComment` signale les exceptions inutiles ; une raison est obligatoire (`# noqa: XXX — raison`), vérifiée par un test de garde | ruff, basedpyright, test |
| `rustfmt` | `ruff format` | ruff |
| `cargo deny` | `pip-audit`, plus un contrôle des licences | uvx |
| `cargo machete` | `deptry` | uvx |

ruff utilise `select = ["ALL"]`, avec une courte liste d'exclusions commentées une par une dans `pyproject.toml`.

Les **tests de garde** (`tests/test_guards.py`) parcourent l'AST de `src/` pour les règles qu'aucun outil ne couvre : `case _:` hors `assert_never`, raison sur chaque commentaire d'exception, modules importés par `ingest`.

**basedpyright plutôt que pyright** : c'est un fork de pyright qui suit chaque version du moteur officiel, s'installe par PyPI sans Node et ajoute `reportAny`. En octobre 2026, ses versions sortent régulièrement (1.40.2 le 4 octobre), mais il repose sur une petite équipe. Décision réversible : en cas d'abandon, on passe à `pyright` et le test de garde interdit les annotations `Any` dans `src/`.

### 4.1 Vérification complète

```bash
uv run ruff format --check && uv run ruff check \
  && uv run basedpyright && uv run lint-imports \
  && uv run pytest \
  && uvx pip-audit && uvx deptry src
```

La commande exacte (en particulier le contrôle des licences) est arrêtée pendant la tâche du squelette, puis recopiée à l'identique dans `CLAUDE.md`, le guide et la CI.

## 5. Tests et boucle rapide

### 5.1 Outils

| Besoin | Outil | Règle |
|---|---|---|
| Tests unitaires et d'intégration | pytest, `pytest-xdist` (`-n auto`) | Sortie concise : `-q --tb=short` |
| Propriétés (saisie rapide, analyse des hooks) | hypothesis | Un profil `ci` plus exigeant que le profil local |
| Instantanés texte (sorties de la CLI) | syrupy (`.ambr`) | Jamais `--snapshot-update` à l'aveugle : le diff des `.ambr` est relu ligne par ligne |
| Mutations | mutmut, en fin de plan | Rapport joint à la PR ; chaque mutation manquée donne un test ou une justification |
| tmux | Serveurs jetables `tmux -L meute-test-<uuid>`, fixture qui fait toujours `kill-server` | Jamais les serveurs réels |

### 5.2 Le TUI en trois niveaux

Les snapshots Textual sont des SVG, illisibles en diff. La logique d'affichage est donc gardée hors des widgets :

1. **Modèle de vue pur** (`meute.core.views`) : des fonctions qui produisent les lignes à afficher, testées en texte avec syrupy.
2. **Comportement** : `App.run_test(size=…)` et `Pilot`. On envoie des touches, puis on vérifie l'état des widgets (sélection, confirmation d'arrêt, message d'erreur).
3. **Rendu** : `pytest-textual-snapshot` à 100 et 60 colonnes, pour la mise en page seulement, relu dans le rapport HTML.

### 5.3 Hooks Claude Code et CI

- **`PostToolUse`** sur un fichier `.py` : `ruff format` sur le fichier, `ruff check --fix` sur le fichier, puis basedpyright sur le fichier. Il sort avec le code 2 et les erreurs sur stderr.
- **`Stop` / `SubagentStop`** : si un fichier `.py`, `pyproject.toml` ou `uv.lock` a changé, il exige que `ruff check`, basedpyright, `lint-imports` et `pytest` passent. Le garde-fou `stop_hook_active` est conservé.
- Les tests des hooks (`.claude/hooks/tests/`) sont réécrits pour les nouveaux hooks.
- **CI** : `astral-sh/setup-uv`, `uv sync --locked`, installation de tmux, vérification complète, tests des hooks. `mold`, `.cargo/` et le job MSRV disparaissent.

## 6. Spike S6 : démarrage de Python

**Question** : `meute ingest hook <event>`, installé via `uv tool`, tient-il en moins de 50 ms sur la machine de l'auteur (WSL2), base SQLite comprise ?

**Prototype jetable**, dans `spikes/s6/`, supprimé après le rapport :

- `_entry.main` dispatche sur `argv` ;
- lecture du JSON du hook sur stdin ;
- ouverture de la base en WAL avec `busy_timeout=200`, puis lecture de `PRAGMA user_version` (le contrôle de migration de chaque appel) ;
- import d'un `core` factice de taille réaliste (une douzaine de modules de dataclasses et d'enums) ;
- insertion d'une ligne dans `session_events`, sortie avec le code 0.

**Mesures** avec `hyperfine -N --warmup 5 --input hook.json`, sur le système de fichiers ext4 de WSL (pas `/mnt/c`). Pour chaque variante : médiane, p95, maximum, et `python -X importtime`.

| # | Variante | Ce qu'elle montre |
|---|---|---|
| 1 | `python3 -I -c pass` | Le plancher de l'interpréteur |
| 2 | `uv tool install .` | L'installation par défaut |
| 3 | `uv tool install --compile-bytecode .` | L'effet de la précompilation des `.pyc`, qu'uv ne fait pas par défaut |
| 4 | Variante 3 pour `ingest statusline` (lecture, écriture, affichage) | L'autre chemin chaud |

**Décision**, sur la médiane de la meilleure variante raisonnable :

- **≤ 35 ms** : on continue.
- **35 à 50 ms** : on continue ; le test `importtime` reste un garde-fou strict.
- **> 50 ms** : arrêt de la migration et discussion avec l'auteur. Pistes : fichier tampon, `python -S`, contrôle de migration allégé, `ingest` minimal écrit à part.

**Livrable** : `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`, avec les chiffres bruts. Si `--compile-bytecode` change nettement le résultat, il devient obligatoire dans les instructions d'installation.

## 7. Déroulement de la migration

Deux PR :

1. **PR de migration**, sur `chore/python-migration`, avec les tâches ci-dessous.
2. **PR du plan 1 Python**, sur sa propre branche, après le merge de la première.

| # | Tâche | Point d'arrêt |
|---|---|---|
| 1 | Spike S6 : prototype, mesures, rapport, suppression du prototype | Médiane > 50 ms : arrêt et discussion |
| 2 | Suppression du Rust : `crates/`, `Cargo.toml`, `Cargo.lock`, `deny.toml`, `clippy.toml`, `rustfmt.toml`, `rust-toolchain.toml`, `.cargo/`, `.claude/hooks/rust-check.sh` ; nettoyage de `.gitignore` | — |
| 3 | Squelette Python, en TDD : `uv init --package`, dépendances de développement, configuration de ruff, basedpyright, import-linter, pytest et deptry, packages vides, `_entry`, test `importtime`, tests de garde | Vérification complète au vert |
| 4 | Hooks `.claude/` et leurs tests, en TDD | — |
| 5 | CI | CI verte sur la PR |
| 6 | `CLAUDE.md` (règles de langue comprises), guide § 2–7 et § 9, `CLAUDE.md` par package (par exemple `src/meute/tmux/CLAUDE.md`), README en anglais | — |
| 7 | Spécification principale : § 1 et 3.1 (mentions de Rust, statusline), § 4.2–4.3 (architecture Python), § 6.1 et 9.1 (blocs ```rust remplacés par des dataclasses), § 7.2, § 13 (`tomlkit`), § 14 (S6), § 16 (exceptions typées), § 17 (tests), langue de l'interface | — |
| 8 | Feuille de route et texte du nouveau plan 1 Python | Relu par l'auteur avant la PR |

Les tâches 1 à 8 sont exécutées dans cet ordre : on mesure avant de supprimer, et l'outillage est au vert avant la réécriture de la documentation.

### 7.1 Le nouveau plan 1 Python

- Même périmètre que le plan 1 Rust : socle, configuration, base SQLite et migrations, tâches et projets en CLI (spécification § 4.2, 4.3, 9.1–9.3, 13, 16, 17).
- Il intègre dès le départ les reports déjà faits en Rust sur `rust-plan-2-wip` : `StatusKind` sans données, filtre `done` dans le cœur, forme `{kind, value}` de `Due`, plus de validation de statut jetable dans la CLI, utilitaires de test regroupés (`tests/conftest.py`).
- Le report « ouverture concurrente de la base » reste un critère d'entrée du plan 3.
- Les tests Rust de `rust-plan-1` et le rapport de mutants (`docs/dev/mutants/`) sont cités comme référence de comportement, sans les traduire mécaniquement : chaque test Python est écrit en TDD.
- Le plan 2 sera réécrit pour Python après le merge du plan 1, avec `rust-plan-2-wip` comme référence.
