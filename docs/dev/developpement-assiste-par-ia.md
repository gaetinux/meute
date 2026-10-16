# Développement assisté par IA sur meute

meute est développé à 100 % avec Claude Code. Ce document décrit les règles et les outils qui rendent ce mode de travail fiable. Il fait référence pour les humains comme pour les agents. Le fichier `CLAUDE.md` à la racine en reprend l'essentiel et renvoie ici pour le détail.

**Le principe.** Plus les vérificateurs automatiques attrapent d'erreurs, moins il reste de choses à relire. Python est dynamique : ce rôle revient à basedpyright en mode `strict`, à ruff avec `select = ["ALL"]`, à import-linter et à des tests de garde. Chaque règle ci-dessous transforme une erreur typique d'agent en échec de type, de lint ou de test.

## 1. TDD systématique

Tout développement se fait en TDD strict :

1. écrire le test ;
2. le lancer et le voir **échouer pour la bonne raison** (pas une simple faute de frappe) ;
3. écrire le code minimal qui le fait passer ;
4. refactoriser, avec les tests au vert.

Règles associées :

- Aucun code de production n'est écrit sans un test qui l'exige.
- Un correctif de bug commence par un test qui reproduit le bug.
- **On ne modifie, ne supprime ni ne désactive (`pytest.mark.skip`, `pytest.mark.xfail`) jamais un test existant pour le faire passer.** Si un test semble faux, on s'arrête et on le signale explicitement, avec la raison, dans le message de commit et dans la PR. `xfail_strict = true` : un `xfail` qui passe fait échouer la suite.
- Les instantanés `syrupy` (§ 4) sont relus ligne par ligne par rapport à la spécification avant d'être acceptés. On n'utilise jamais `--snapshot-update` à l'aveugle.
- À la fin de chaque tâche de code : `/simplify`. Quand le code touche aux sous-processus, aux fichiers, à SQL ou à des entrées externes (hooks, MCP) : `/security-review` aussi.

## 2. Le typage comme spécification

- **États impossibles irreprésentables.** Une union de dataclasses gelées porte les données de chaque état : `TaskStatus = Todo | InProgress | Blocked | Review | Done`, avec `Blocked(reason: str)`, plutôt qu'un statut et une raison séparés. `enum.Enum` reste réservé aux énumérations simples (`Priority`).
- **Des types dédiés pour les identifiants** : `TaskId = NewType("TaskId", int)` plutôt qu'un `int` nu.
- **Pas de `case _:` sur nos propres types.** `reportMatchNotExhaustive = "error"` liste tous les `match` à compléter quand on ajoute une variante. Seule exception : `case _: assert_never(x)`. Un test de garde parcourt l'AST de `src/` et refuse tout autre `case _:`.
- **Données immuables** : `@dataclass(frozen=True, slots=True, kw_only=True)`.
- **Des docstrings (convention Google) sur tout élément public de `meute.core`** (règles `D` de ruff). Ce sont le contrat que lisent les agents qui travaillent dans les autres packages.

## 3. Lints contre les mauvaises habitudes des agents

La configuration est dans `pyproject.toml` (`[tool.ruff]`, `[tool.basedpyright]`). ruff utilise `select = ["ALL"]` ; seuls `COM812` et `ISC001` (conflit avec le formatteur) et `CPY` (en-tête de copyright) sont exclus, avec leur raison en commentaire.

| Règle | Outil | Ce qu'elle empêche |
|---|---|---|
| `typeCheckingMode = "strict"` | basedpyright | les types manquants ou approximatifs |
| `reportMatchNotExhaustive` | basedpyright | le `match` qui oublie une variante |
| `reportAny`, `reportExplicitAny`, `ANN401` | basedpyright, ruff | `Any`, implicite ou explicite |
| `TID251` sur `typing.cast` | ruff | le `cast` qui fait taire le vérificateur de types (utiliser `isinstance` ou un `TypeGuard`) |
| `S101` | ruff | l'`assert` hors des tests |
| `E722`, `BLE001`, `S110` | ruff | le `except:` nu et le `except Exception` qui avale tout |
| `S` (bandit) | ruff | `eval`/`exec`, `pickle`, `subprocess(shell=True)` |
| `FIX`, `T100`, `ERA` | ruff | le code laissé à moitié écrit, le code commenté |
| `T20` | ruff | `print` dans `meute.core`, `meute.tmux`, `meute.git`, `meute.claude`, `meute.tui` et `meute.mcp` (autorisé dans `meute.cli` et `meute.ingest`) |
| `D` (Google) | ruff | les éléments publics non documentés, dans `meute.core` seulement |
| `PGH003`, `PGH004`, `reportIgnoreCommentWithoutRule` | ruff, basedpyright | une suppression sans règle précise |
| `reportUnnecessaryTypeIgnoreComment` | basedpyright | une suppression devenue inutile |
| `enableTypeIgnoreComments = false` | basedpyright | `# type: ignore` (désactivé) |
| `ruff format` | ruff | les débats de style |

**Règle des exceptions.** Toute directive `noqa`, `ruff: noqa` ou `pyright:` doit viser une règle précise et donner une raison après ` — ` (par exemple `# noqa: S603 — arguments built from a fixed list`). Les directives qui abaissent le mode (`# pyright: basic`, `standard`, `off`) sont interdites, même avec une raison. `# type: ignore` est désactivé. Le test de garde `test_every_suppression_has_a_reason` (`tests/test_guards.py`, logique dans `tests/guards.py`) fait respecter tout cela. Chaque exception est mentionnée dans la PR.

**basedpyright plutôt que pyright** : fork de pyright qui suit chaque version du moteur officiel, s'installe par PyPI sans Node et ajoute `reportAny`. Il repose sur une petite équipe. Décision réversible : en cas d'abandon, on passe à `pyright` et un test de garde interdira les annotations `Any` dans `src/`.

## 4. Des tests qui testent vraiment

Le risque principal du TDD avec une IA, ce sont des tests qui passent sans rien vérifier. Les tests unitaires et d'intégration (`pytest`, `pytest-xdist` avec `-n auto`, sortie `-q --tb=short`) sont complétés par :

- **`hypothesis`** : tests de propriétés sur les analyseurs, par exemple la saisie rapide ou l'analyse des hooks. Des entrées aléatoires, des invariants (« ne lève jamais », « le titre n'est jamais vide quand le résultat est valide »).
- **`syrupy`** : instantanés (`.ambr`) pour les sorties textuelles de la CLI. La relecture se fait sur un diff lisible.
- **`mutmut`** : il introduit des mutations dans le code (condition inversée, valeur par défaut renvoyée…) et vérifie qu'un test échoue. Une mutation « manquée » révèle un test trop faible. Il est lancé **à la fin de chaque plan**, trop lent pour chaque tâche. Chaque mutation manquée donne lieu soit à un nouveau test (en TDD), soit à une justification écrite dans la PR.
- **Tests de garde** (`tests/test_guards.py`) pour ce qu'aucun outil ne couvre : pas de `case _:` hors `assert_never`, raison sur chaque suppression, packages `core`, `tmux`, `git` et `ingest` limités à la stdlib (et `meute` pour `ingest`), et `meute/core/__init__.py` sans aucun import (`test_core_init_has_no_imports`).
- **Test `importtime`** (`tests/test_importtime.py`) : il lance `python -X importtime -m meute ingest …` dans un sous-processus et échoue si un module importé n'est ni de la stdlib ni de `meute`, ou si `ingest` charge la CLI. C'est un garde strict et obligatoire : il protège le budget de 50 ms de `meute ingest` (spécification § 7.3 ; le spike S6 mesure une médiane d'environ 47 ms).
- **tmux** : serveurs jetables `tmux -L meute-test-<uuid>`, avec une fixture qui fait toujours `kill-server`. Jamais les serveurs réels.
- **TUI** en trois niveaux : modèle de vue pur (`meute.core.views`, testé en texte avec `syrupy`), comportement via `App.run_test` et `Pilot`, rendu via `pytest-textual-snapshot` (mise en page seulement).

## 5. Une boucle de rétroaction rapide et automatique

### Hooks Claude Code du dépôt (`.claude/settings.json`)

| Hook | Déclencheur | Action |
|---|---|---|
| `.claude/hooks/py-check.sh` | `PostToolUse` sur `Edit`, `Write` ou `MultiEdit` d'un fichier `.py` | Lance `ruff format`, `ruff check --fix` puis `basedpyright` sur le fichier. En cas d'erreur, il sort avec le code **2** et écrit les erreurs sur stderr : Claude les voit immédiatement |
| `.claude/hooks/verify.sh` | `Stop` et `SubagentStop` | Si des fichiers `*.py`, `pyproject.toml` ou `uv.lock` ont changé (`git status --porcelain`), il exige que `ruff check`, `basedpyright`, `lint-imports` et `pytest` passent. Sinon, il sort avec le code 2 : l'agent ne peut pas annoncer « terminé » |

Comportements à connaître :

- `py-check.sh` ne bloque jamais une édition quand `uv` est absent (simple avertissement sur stderr) et ignore les fichiers hors du projet (chemins résolus, liens symboliques suivis).
- `verify.sh` bloque l'arrêt quand les vérifications échouent **ou** quand `uv` est absent, sauf si `stop_hook_active` est vrai. Ce garde-fou évite les boucles infinies : l'agent peut alors s'arrêter, `verify.sh` écrit sur stderr que la vérification échoue toujours, et l'agent doit le signaler explicitement dans son rapport.
- Les tests des hooks sont dans `.claude/hooks/tests/` (`bash .claude/hooks/tests/run.sh`) et tournent en CI.

### Sorties

**Sorties concises** : `-q --tb=short` pour pytest, erreurs tronquées à 60 lignes dans les hooks. Moins de bruit, c'est plus de contexte utile.

## 6. Contexte et organisation du code

- **Fichiers courts** : visez moins de 300 lignes, avec un maximum indicatif de 400. Un module par responsabilité. Un agent raisonne mieux sur un fichier qu'il voit en entier.
- **`CLAUDE.md` par package** quand un package a des règles propres (par exemple `src/meute/tmux/CLAUDE.md` : « tests uniquement sur un serveur tmux jetable »). Claude Code le charge quand il travaille dans ce dossier.
- **Données immuables** : dataclasses gelées, pas d'état partagé modifiable.
- **Code synchrone par défaut.** L'asynchrone n'apparaît que dans `meute.tui` (Textual) et `meute.mcp` (SDK MCP), là où ces bibliothèques l'imposent.
- **Packages et règles d'imports** (contrats `import-linter` dans `pyproject.toml`, vérifiés par `lint-imports`) :
  - `meute.core`, `meute.tmux` et `meute.git` sont indépendants les uns des autres ; `meute.tui`, `meute.mcp` et `meute.claude` aussi. L'assemblage se fait dans `meute.cli`.
  - `core`, `tmux`, `git`, `ingest` et `claude` n'importent ni `typer`, ni `textual`, ni `mcp`, ni `tomlkit`, ni `meute.cli`, `meute.tui`, `meute.mcp`.
  - `meute.ingest` n'importe que la stdlib et `meute.core` (pas `tmux`, `git`, `claude`).
  - Seul `meute.cli` importe `typer` (interdit à `tui` et `mcp`).
- **Pourquoi un cœur limité à la stdlib** : `ingest` réutilise le vrai modèle sans dupliquer de règle, le cœur reste rapide à importer et lisible sans connaître de bibliothèque tierce. Le prix : validation écrite à la main dans les dataclasses (pas de pydantic), chemins XDG codés à la main, écriture du TOML hors du cœur.
- **Discipline d'imports (spike S6).** `meute/core/__init__.py` n'importe ni ne réexporte jamais rien (garde `test_core_init_has_no_imports`) : sinon, importer un sous-module du cœur chargerait tout le cœur. `ingest` n'importe que les sous-modules du cœur dont il a besoin. Le test `importtime` (§ 4) est strict et obligatoire.

## 7. Dépendances

- **Ajouter une dépendance uniquement avec `uv add`** (`uv add --dev` pour le développement), qui prend la dernière version publiée, puis consulter sa documentation **à jour** (plugin context7 ou documentation officielle). Ne jamais se fier à la mémoire du modèle : les agents inventent souvent des API d'anciennes versions.
- **`uv.lock` est commité**, et `uv lock --check` fait échouer la vérification s'il est périmé.
- **`pip-audit`** vérifie les avis de sécurité sur les dépendances figées du `uv.lock`.
- **`pip-licenses`** vérifie les licences (liste blanche dans `scripts/verify.sh`).
- **`deptry`** repère les dépendances déclarées mais inutilisées, manquantes ou transitives.

## 8. Workflow Git

- Une branche par plan ou par modification, jamais de commit ni de push sur `main`.
- Un commit par tâche, avec tous les tests au vert.
- Une PR assignée à `gaetinux`, qui la relit et la merge lui-même.
- Messages de commit et titres de PR en anglais.
- Les messages de commit se terminent par `Co-Authored-By: Claude …`, **sans ligne `Claude-Session` ni lien de session**.

## 9. Vérification complète

C'est la commande que lance la CI, et qu'un agent doit voir passer avant d'annoncer qu'une tâche est terminée :

```bash
bash scripts/verify.sh
```

Le script enchaîne, en s'arrêtant à la première erreur :

1. `uv lock --check` : le lockfile est à jour ;
2. `ruff format --check` puis `ruff check` ;
3. `basedpyright` ;
4. `lint-imports` ;
5. `pytest` (tests, tests de garde et `importtime`) ;
6. `deptry src` ;
7. `pip-audit --strict` sur l'export figé du `uv.lock` ;
8. `pip-licenses` avec la liste blanche de licences.

La CI exécute aussi `bash .claude/hooks/tests/run.sh`.
