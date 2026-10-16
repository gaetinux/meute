# meute — Migration de Rust à Python — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Objectif :** remplacer l'outillage Rust par un squelette Python vérifié (uv, ruff, basedpyright, import-linter, pytest, hooks `.claude/`, CI) après avoir mesuré que `meute ingest` tient en 50 ms (spike S6), puis réécrire la documentation de méthode, la spécification, la feuille de route et le nouveau plan 1.

**Architecture :** un seul paquet `meute` (`src/meute/`), découpé en packages dont les dépendances sont vérifiées par import-linter et par des tests de garde AST. Le point d'entrée `meute._entry` dispatche `ingest` avant tout import lourd ; un test `importtime` le garantit. Aucun code métier dans ce plan : les packages sont vides, sauf le dispatch, un `ingest` muet et une CLI Typer réduite à `--version`.

**Stack technique :** Python 3.13, uv, ruff 0.17, basedpyright 1.40, import-linter 2.15, pytest 9.1, pytest-xdist 3.8, typer 0.27, deptry 0.25, pip-audit 2.10 (versions à la date du plan ; `uv add` prend la dernière). Outils externes : tmux (déjà installé), hyperfine (spike S6).

**Spécification :** `docs/superpowers/specs/2026-10-16-migration-python-design.md` (la conception de la migration). Spécification fonctionnelle : `docs/superpowers/specs/2026-10-15-meute-design.md`.

## Contraintes globales

- Branche `chore/python-migration` (déjà créée depuis `main`, la conception y est commitée). Un commit par tâche, jamais de push sur `main`, PR assignée à `gaetinux` à la fin.
- **Messages de commit en anglais**, terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, **sans ligne `Claude-Session` ni lien de session**.
- Code, identifiants et commentaires en anglais ; **textes affichés à l'utilisateur de meute en anglais**. Messages des hooks `.claude/` (destinés aux agents du dépôt) en français, copiés mot pour mot depuis ce plan.
- TDD strict pour tout code conservé (Tasks 3 et 4) : test écrit, échec constaté pour la bonne raison (sortie citée dans le rapport), code minimal, refactorisation au vert. Le prototype du spike (Task 1) est jetable et n'est pas soumis au TDD.
- On ne modifie, ne supprime ni ne désactive jamais un test existant pour le faire passer. Seule exception : la Task 2 supprime les tests Rust avec le reste du code Rust (ils restent consultables sous `rust-plan-1` et `rust-plan-2-wip`).
- Dépendances ajoutées uniquement avec `uv add` / `uv add --dev`, jamais en éditant `pyproject.toml` à la main ; documentation de la version installée consultée (context7 ou la doc officielle) avant usage. `uv.lock` commité.
- Python `>=3.13`, fichier `.python-version` à `3.13`.
- Fichiers de moins de 300 lignes.
- **Fin de chaque tâche qui produit du code conservé (3, 4, 5)** : lancer le skill `simplify` sur le diff de la tâche, puis la vérification complète. Lancer aussi `security-review` à la Task 4 (les hooks exécutent des commandes à partir d'un chemin reçu en JSON) et à la Task 9 sur toute la branche.
- **Vérification complète** à partir de la Task 3 : `bash scripts/verify.sh` (créé à la Task 3, source unique utilisée par `CLAUDE.md`, le guide et la CI).

## Prérequis sur la machine de l'auteur

Absents au moment de la rédaction ; à installer avant la Task 1 (l'exécutant demande à l'auteur s'il ne peut pas le faire lui-même) :

- `uv` : `curl -LsSf https://astral.sh/uv/install.sh | sh`
- `hyperfine` : `cargo install --locked hyperfine` (la chaîne Rust est encore installée), ou `sudo apt install hyperfine`.

## Hors périmètre

- Tout code métier (configuration, base, tâches) : nouveau plan 1, rédigé à la Task 8.
- `mutmut`, `hypothesis`, `syrupy`, `textual`, `tomlkit`, `mcp` : ajoutés par le plan qui s'en sert.
- La réécriture du plan 2 pour Python : après le merge du plan 1.

## Points de vigilance

1. **Chemins reçus par les hooks** : un fichier dont le nom contient des espaces ou des caractères spéciaux (`a b.py`, `$x.py`) est traité sans injection ni découpage. Test à la Task 4.
2. **Fichier hors du dépôt** : un `.py` édité hors de `CLAUDE_PROJECT_DIR` (par exemple dans `/tmp`) ou supprimé entre-temps est ignoré par `py-check.sh` (code 0, rien sur stderr). Test à la Task 4.
3. **`uv` introuvable** : `py-check.sh` ne bloque pas l'édition (code 0, avertissement sur stderr) ; `verify.sh` refuse l'arrêt (code 2), sauf si `stop_hook_active`. Test à la Task 4.
4. **`meute ingest` sur une entrée invalide** : stdin vide, JSON invalide, sous-commande absente ou inconnue (`meute ingest`, `meute ingest foo`) → code 0 et stdout vide (spécification § 7.3). Test à la Task 3.
5. **Hook `Stop` pendant la suppression du Rust** : des fichiers `.rs` supprimés mais non commités déclenchent `cargo clippy` sans `Cargo.toml`, donc un blocage. La Task 2 supprime et commite dans la même étape, sans s'arrêter entre les deux.

---

### Task 1 : spike S6 — temps de démarrage de `meute ingest`

Prototype **jetable**, hors du TDD. Conception § 6.

**Fichiers :**
- Créer (temporaire, supprimé à l'étape 6) : `spikes/s6/pyproject.toml`, `spikes/s6/src/meute_s6/_entry.py`, `spikes/s6/src/meute_s6/ingest.py`, `spikes/s6/src/meute_s6/core/__init__.py` et 12 modules `spikes/s6/src/meute_s6/core/m01.py` … `m12.py`, `spikes/s6/hook.json`, `spikes/s6/statusline.json`, `spikes/s6/bench.sh`
- Créer (conservé) : `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`

- [ ] **Étape 1 : prototype.** `uv init --package --name meute-s6 spikes/s6`, script `meute-s6 = "meute_s6._entry:main"`.
  - `_entry.main()` : si `sys.argv[1] == "ingest"`, `from meute_s6 import ingest` puis `ingest.run(sys.argv[2:])` ; sinon import paresseux d'un module qui importe `typer` (dépendance du prototype, pour vérifier qu'elle n'est pas chargée).
  - `core/__init__.py` importe les 12 modules ; chacun fait environ 50 lignes : un `Enum`, deux dataclasses `frozen=True, slots=True`, deux fonctions, et importe une partie de `dataclasses`, `enum`, `datetime`, `zoneinfo`, `json`, `sqlite3`, `pathlib`, `re`, `typing`.
  - `ingest.run(args)` : importe `meute_s6.core` ; lit stdin et le décode en JSON ; ouvre `$MEUTE_S6_DB` avec `sqlite3.connect(..., timeout=0.2)`, `PRAGMA journal_mode=WAL`, lit `PRAGMA user_version` ; crée la table `session_events(id INTEGER PRIMARY KEY, at TEXT, kind TEXT, payload TEXT)` si besoin ; insère une ligne ; commit ; retourne 0. Pour `statusline`, insère aussi une ligne puis affiche une ligne de texte construite à partir du JSON.
  - `hook.json` : un vrai `PostToolUse` tiré de `docs/superpowers/spikes/2026-10-15-spikes-s1-s5.md` (§ S2) ; `statusline.json` : le JSON du § S3 du même rapport.
- [ ] **Étape 2 : script de mesure** `bench.sh`. Base dans un dossier temporaire sous `$HOME` (ext4, jamais `/mnt/c`). Pour chaque variante, `hyperfine -N --warmup 5 --runs 100 --input <json> --export-json <variante>.json '<commande>'`, puis `python -X importtime` sur la même commande (les 15 modules les plus coûteux, en cumulé) :
  1. `python3 -I -c pass` ;
  2. `uv tool install --force spikes/s6`, puis `meute-s6 ingest hook PostToolUse` ;
  3. `uv tool install --force --compile-bytecode spikes/s6`, même commande ;
  4. variante 3 avec `meute-s6 ingest statusline` et `statusline.json`.
  Vérifier aussi, avec `python -X importtime`, que `typer` n'apparaît pas dans les variantes 2 à 4.
- [ ] **Étape 3 : mesurer.** `bash spikes/s6/bench.sh`. Relever médiane, p95 et maximum de chaque variante (dans les JSON de hyperfine : `median`, et le 95ᵉ centile calculé sur `times`).
- [ ] **Étape 4 : rapport** dans `docs/superpowers/spikes/2026-10-16-spike-s6-demarrage-python.md`, sur le modèle de `2026-10-15-spikes-s1-s5.md` : date, versions (Python, uv, hyperfine, noyau WSL2), méthode, tableau des quatre variantes (médiane, p95, max, en ms), extrait d'`importtime`, décision selon le seuil ci-dessous, et recommandation sur `--compile-bytecode`.
- [ ] **Étape 5 : point d'arrêt.** Sur la médiane de la meilleure variante parmi 2 et 3 :
  - **≤ 35 ms** ou **35 à 50 ms** : continuer (le rapport cite la tranche) ;
  - **> 50 ms** (ou variante 4 > 50 ms) : **arrêter le plan**, commiter le rapport seul, et présenter les chiffres à l'auteur avec les pistes de la conception § 6. Ne pas passer à la Task 2 sans sa décision.
- [ ] **Étape 6 : nettoyer et commiter.** `uv tool uninstall meute-s6`, `rm -rf spikes/`. `git status` ne montre que le rapport.
  `git commit -m "docs(spike): S6, Python start-up time of meute ingest"`

### Task 2 : suppression du code Rust

**Fichiers :**
- Supprimer : `crates/`, `Cargo.toml`, `Cargo.lock`, `deny.toml`, `clippy.toml`, `rustfmt.toml`, `rust-toolchain.toml`, `.cargo/`, `.claude/hooks/tests/fixtures/` (fixture Rust)
- Modifier : `.gitignore`
- Conservés jusqu'à la Task 4 : `.claude/hooks/rust-check.sh`, `.claude/hooks/verify.sh`, `.claude/hooks/tests/run.sh` (inertes sans fichier `.rs`) ; `.github/workflows/ci.yml` jusqu'à la Task 5.

- [ ] **Étape 1 : supprimer et commiter d'un seul tenant** (point de vigilance 5) : `git rm -rq crates Cargo.toml Cargo.lock deny.toml clippy.toml rustfmt.toml rust-toolchain.toml .cargo .claude/hooks/tests/fixtures`, puis `rm -rf target`. Ne pas toucher à `mutants.out*/` ni à `concept.md` (ignorés, propriété de l'auteur).
- [ ] **Étape 2 : `.gitignore`** devient :
  ```
  /concept.md
  # Rust leftovers kept locally by the author
  mutants.out*/
  .venv/
  __pycache__/
  .pytest_cache/
  .ruff_cache/
  /mutants/
  ```
- [ ] **Étape 3 : vérifier.** `git ls-files | grep -E '\.rs$|Cargo|\.cargo'` ne renvoie rien ; `git status --porcelain -- '*.rs'` est vide après le commit.
  `git commit -m "chore: remove the Rust implementation (kept under the rust-plan-1 and rust-plan-2-wip tags)"`

### Task 3 : squelette Python, point d'entrée et garde-fous

**Fichiers :**
- Créer : `pyproject.toml`, `uv.lock`, `.python-version`, `scripts/verify.sh`
- Créer : `src/meute/__init__.py`, `src/meute/__main__.py`, `src/meute/_entry.py`, `src/meute/py.typed`
- Créer (un `__init__.py` avec une docstring d'une ligne chacun) : `src/meute/core/`, `src/meute/tmux/`, `src/meute/git/`, `src/meute/claude/`, `src/meute/tui/`, `src/meute/mcp/`
- Créer : `src/meute/ingest/__init__.py`, `src/meute/cli/__init__.py`
- Test : `tests/test_entry.py`, `tests/test_importtime.py`, `tests/guards.py`, `tests/test_guards_unit.py`, `tests/test_guards.py`

**Interfaces :**
- Produit :
  - `meute._entry.main(argv: Sequence[str] | None = None) -> int` : `argv` vaut `sys.argv[1:]` par défaut. Si `argv[0] == "ingest"`, importe `meute.ingest` et retourne `meute.ingest.run(argv[1:])` ; sinon importe `meute.cli` et retourne `meute.cli.run(argv)`. Les deux imports sont **dans la fonction**.
  - Script `meute = "meute._entry:console"`, où `console() -> NoReturn` fait `sys.exit(main())`. `__main__.py` appelle `console()`.
  - `meute.ingest.run(args: Sequence[str]) -> int` : lit stdin entièrement, ne fait rien d'autre, n'écrit rien sur stdout, retourne toujours `0` ; toute exception est attrapée (`except Exception`, avec `# noqa: BLE001 — spec § 7.3: ingest never fails`).
  - `meute.cli.app: typer.Typer` (nom `meute`) avec l'option `--version` qui affiche `meute <version>` (version lue par `importlib.metadata.version("meute")`) ; `meute.cli.run(argv: Sequence[str]) -> int` appelle `app(args=list(argv), prog_name="meute")` et retourne le code de `SystemExit`.
  - `tests/guards.py` : `wildcard_cases(source: str) -> list[int]`, `suppressions_without_reason(source: str) -> list[int]`, `non_stdlib_imports(source: str) -> list[str]`, `STDLIB_ONLY_PACKAGES: tuple[str, ...] = ("core", "tmux", "git", "ingest")`.

- [ ] **Étape 1 : projet uv.** `uv init --package --name meute --python 3.13 --vcs none .` (vérifier qu'il ne réécrit pas `.gitignore` ; s'il crée `README.md`, le garder tel quel jusqu'à la Task 6, puisque `pyproject.toml` le référence). Version `0.1.0`, `requires-python = ">=3.13"`, licence `MIT OR Apache-2.0`. `uv add typer`, `uv add --dev ruff basedpyright import-linter pytest pytest-xdist deptry pip-audit`.
- [ ] **Étape 2 : configuration dans `pyproject.toml`.**
  - `[tool.ruff]` : `target-version = "py313"`, `line-length = 100`, `src = ["src", "tests"]`. `[tool.ruff.lint]` : `select = ["ALL"]`, `ignore = ["COM812", "ISC001", "CPY"]` (les deux premiers entrent en conflit avec le formateur, `CPY` exige un en-tête de copyright ; un commentaire par ligne). `[tool.ruff.lint.pydocstyle] convention = "google"`. `[tool.ruff.lint.flake8-tidy-imports.banned-api]` : `"typing.cast".msg = "use isinstance or a TypeGuard"`. `per-file-ignores` : `"tests/**" = ["S101", "D", "PLR2004", "INP001", "S603"]` (assert, docstrings, valeurs magiques, pas de `__init__.py`, sous-processus de test) ; `"src/meute/{tmux,git,claude,tui,mcp,cli,ingest}/**" = ["D"]` et `"src/meute/{_entry,__main__}.py" = ["D"]` (docstrings exigées dans `meute.core` seulement) ; `"src/meute/{cli,ingest}/**" = ["T20"]`.
  - `[tool.basedpyright]` : `pythonVersion = "3.13"`, `include = ["src", "tests"]`, `typeCheckingMode = "strict"`, `enableTypeIgnoreComments = false`, et à `"error"` : `reportAny`, `reportExplicitAny`, `reportIgnoreCommentWithoutRule`, `reportUnnecessaryTypeIgnoreComment`, `reportMatchNotExhaustive`.
  - `[tool.importlinter]` : `root_package = "meute"`, `include_external_packages = true`. Contrats : (1) `independence` entre `meute.core`, `meute.tmux`, `meute.git` ; (2) `independence` entre `meute.tui`, `meute.mcp`, `meute.claude` ; (3) `forbidden` : `meute.core`, `meute.tmux`, `meute.git`, `meute.ingest`, `meute.claude` ne peuvent importer ni `typer`, ni `textual`, ni `mcp`, ni `tomlkit`, ni `meute.cli`, ni `meute.tui`, ni `meute.mcp` ; (4) `forbidden` : `meute.ingest` ne peut importer que la stdlib et `meute.core` — exprimé en interdisant `meute.tmux`, `meute.git`, `meute.claude` ; (5) `forbidden` : seul `meute.cli` importe `typer` — `meute.tui`, `meute.mcp` ne peuvent importer `typer`. Le cas de `meute._entry` (imports paresseux) est couvert par le test `importtime`, pas par un contrat. Si import-linter refuse un paquet externe qui n'est pas installé (`textual`, `mcp`, `tomlkit`), le retirer du contrat avec un commentaire : `test_stdlib_only_packages` (étape 9) couvre déjà `core`, `tmux`, `git` et `ingest`, et le plan qui ajoute la dépendance la remet dans le contrat.
  - `[tool.pytest.ini_options]` : `testpaths = ["tests"]`, `addopts = "-q --tb=short -n auto --strict-markers -p no:cacheprovider"`, `xfail_strict = true`.
  - `[tool.deptry]` : rien, sauf si `deptry src` signale un faux positif (justifier en commentaire).
- [ ] **Étape 3 : tests qui échouent — point d'entrée** (`tests/test_entry.py`, sous-processus `sys.executable -m meute …`, avec `input=`, `capture_output=True`, `text=True`) :
  - `test_version_prints_name_and_version` : `--version` → code 0, stdout == `f"meute {importlib.metadata.version('meute')}\n"` ;
  - `test_ingest_hook_is_silent_and_succeeds` : `ingest hook PostToolUse` avec un JSON valide → code 0, stdout `""` ;
  - `test_ingest_never_fails` (paramétré) : `(["ingest"], "")`, `(["ingest", "foo"], "not json")`, `(["ingest", "hook"], "{")`, `(["ingest", "statusline"], "")` → code 0, stdout `""` (point de vigilance 4) ;
  - `test_unknown_command_fails` : `nope` → code ≠ 0 (Typer).
- [ ] **Étape 4 : constater l'échec** (`uv run pytest tests/test_entry.py`) : `No module named meute.__main__` ou équivalent.
- [ ] **Étape 5 : implémenter** `_entry`, `__main__`, `ingest/__init__.py`, `cli/__init__.py` selon les Interfaces. Les tests passent.
- [ ] **Étape 6 : tests qui échouent — `importtime`** (`tests/test_importtime.py`). Utilitaire `imported_roots(args: list[str], stdin: str) -> set[str]` : lance `sys.executable -X importtime -m meute *args`, analyse stderr (lignes `import time: … | <nom>`), retourne la racine de chaque module (`nom.strip().split(".")[0]`).
  - `test_ingest_path_imports_only_stdlib_and_meute` : pour `["ingest", "hook", "PostToolUse"]`, `imported_roots(...) - set(sys.stdlib_module_names) - {"meute", "_virtualenv"}` == `set()` (`_virtualenv` est le module d'amorçage des environnements créés par uv ; commentaire obligatoire) ;
  - `test_ingest_path_never_loads_the_cli` : aucun module `meute.cli` dans la sortie brute ;
  - `test_cli_path_loads_typer` (témoin, prouve que le test sait détecter un import) : pour `["--version"]`, `"typer" in imported_roots(...)`.
  Constater l'échec du témoin en faisant temporairement importer `meute.cli` au niveau module de `_entry` : `test_ingest_path_never_loads_the_cli` doit échouer. Revenir à l'import paresseux ; tout passe.
- [ ] **Étape 7 : tests qui échouent — gardes unitaires** (`tests/test_guards_unit.py`, sur des extraits de code) :
  - `wildcard_cases` : `"match x:\n    case A():\n        pass\n    case _:\n        pass\n"` → `[4]` ; `case _:` dont le corps est uniquement `assert_never(x)` → `[]` ;
  - `suppressions_without_reason` (commentaires lus avec `tokenize`) : `x = 1  # noqa: E501` → `[1]` ; `x = 1  # noqa: E501 — long URL` → `[]` ; `# noqa` sans code → `[1]` ; `# pyright: ignore[reportAny]` → `[1]` ; `# pyright: ignore[reportAny] — json.loads` → `[]`. Raison : texte non vide après ` — ` ;
  - `non_stdlib_imports` : `"import os\nimport typer\nfrom meute.core import x\nfrom . import y\n"` → `["typer"]`.
- [ ] **Étape 8 : constater l'échec** (`ModuleNotFoundError: guards` ou `AttributeError`), **implémenter** `tests/guards.py` avec `ast` et `tokenize`, puis faire passer.
- [ ] **Étape 9 : gardes appliquées au dépôt** (`tests/test_guards.py`) : `test_no_wildcard_case_in_src`, `test_every_suppression_has_a_reason` (sur `src/` et `tests/`), `test_stdlib_only_packages` (chaque fichier de `src/meute/<p>/` pour `p` dans `STDLIB_ONLY_PACKAGES`, plus `src/meute/_entry.py`). Elles passent d'emblée sur un dépôt vide : le constater, puis vérifier qu'elles mordent en ajoutant temporairement `import typer` dans `src/meute/core/__init__.py` (échec attendu de `test_stdlib_only_packages`, puis retrait).
- [ ] **Étape 10 : `scripts/verify.sh`** (`set -euo pipefail`), dans cet ordre :
  ```bash
  uv run --frozen ruff format --check
  uv run --frozen ruff check
  uv run --frozen basedpyright
  uv run --frozen lint-imports
  uv run --frozen pytest
  uv run --frozen deptry src
  req="$(mktemp)"; trap 'rm -f "$req"' EXIT
  uv export --frozen --no-emit-project --format requirements-txt -o "$req" >/dev/null
  uv run --frozen pip-audit --strict --disable-pip --require-hashes -r "$req"
  uv run --frozen --with pip-licenses pip-licenses --partial-match \
    --allow-only "MIT;BSD;Apache;ISC;Python Software Foundation;PSF;MPL-2.0"
  ```
  Si une option n'existe pas dans la version installée (vérifier avec `--help`), adapter et le dire dans le rapport de la tâche. Le contrôle des licences ne doit refuser aucune dépendance actuelle ; une licence hors liste est ajoutée avec un commentaire qui la justifie.
- [ ] **Étape 11 : `simplify`, puis vérification complète.** `bash scripts/verify.sh` au vert.
  `git commit -m "build: Python skeleton with uv, strict typing, import contracts and guard tests"`

### Task 4 : hooks Claude Code pour Python

**Fichiers :**
- Créer : `.claude/hooks/py-check.sh`
- Modifier : `.claude/hooks/verify.sh`, `.claude/settings.json`, `.claude/hooks/tests/run.sh`
- Supprimer : `.claude/hooks/rust-check.sh`
- Créer (fixture) : `.claude/hooks/tests/fixtures/pyproject.toml`, `.claude/hooks/tests/fixtures/src/fixture/__init__.py`, `.claude/hooks/tests/fixtures/tests/test_ok.py`

**Interfaces :**
- `py-check.sh` (PostToolUse sur `Edit|Write|MultiEdit`) : lit `tool_input.file_path` comme aujourd'hui (via `python3`). Ignore (code 0, rien sur stderr) si le chemin ne finit pas par `.py`, n'existe pas, ou n'est pas sous `$CLAUDE_PROJECT_DIR` (comparaison des chemins résolus). Si `uv` est introuvable : stderr `uv introuvable : vérification Python ignorée`, code 0. Sinon, depuis `$CLAUDE_PROJECT_DIR` : `uv run --frozen ruff format -q -- "$file"`, puis `uv run --frozen ruff check --fix -q -- "$file"` et `uv run --frozen basedpyright -- "$file"`. En cas d'échec de l'une des deux dernières : stderr `vérification Python en échec :` suivi des 60 premières lignes de sortie, code 2.
- `verify.sh` (Stop / SubagentStop) : se déclenche si `git status --porcelain -- '*.py' 'pyproject.toml' 'uv.lock'` n'est pas vide. Lance `uv run --frozen ruff check && uv run --frozen basedpyright && uv run --frozen lint-imports && uv run --frozen pytest`. Messages inchangés : `vérification en échec, corrige avant de terminer :` (code 2) et, si `stop_hook_active`, `vérification toujours en échec — signale-le explicitement dans ton rapport` (code 0). Si `uv` est introuvable : même traitement qu'un échec, avec la sortie `uv introuvable`.
- Fixture : paquet `fixture` avec ses propres `[tool.ruff]`, `[tool.basedpyright]` (strict), `[tool.importlinter]` (un contrat `forbidden` : `fixture` ne peut importer `typer`) et un groupe `dev` qui épingle ruff, basedpyright, import-linter et pytest **aux versions du `uv.lock` racine**. `run.sh` fait `uv lock -q && uv sync -q` dans la copie de la fixture avant les cas, et `reset_tree` exclut `.venv` et `uv.lock` du `git clean`.

- [ ] **Étape 1 : tests qui échouent** dans `run.sh` (même structure qu'aujourd'hui : copie de la fixture dans un dossier temporaire, faux binaire témoin, `report`). Le faux binaire témoin s'appelle désormais `uv`. Cas :
  - `non_python_ignored` : `README.md` → code 0, stdout et stderr vides ;
  - `python_ok` : `src/fixture/__init__.py` valide → code 0 ;
  - `python_is_formatted` : `x=1` écrit dans `src/fixture/__init__.py` → code 0 et le fichier contient `x = 1` ;
  - `python_type_error_blocks` : `def f() -> int:\n    return "a"\n` → code 2, stderr contient `vérification Python en échec` et `is not assignable` ;
  - `odd_file_name_is_safe` : fichier `src/fixture/a b $x.py` contenant une erreur de type → code 2 et le fichier `$x` n'a pas été créé ni interprété (point de vigilance 1) ;
  - `outside_project_ignored` : `/tmp/…/outside.py` invalide, et un chemin `.py` inexistant → code 0, stderr vide (point de vigilance 2) ;
  - `missing_uv_does_not_block_edit` / `missing_uv_blocks_stop` : `PATH` réduit à un dossier contenant des liens vers `bash`, `git`, `python3`, `cat`, `head`, `tail`, `realpath`, `dirname` → `py-check.sh` code 0 avec `uv introuvable` ; `verify.sh` (avec un `.py` modifié) code 2 (point de vigilance 3) ;
  - `verify_clean_tree` : arbre propre → code 0 et le faux `uv` n'a pas été appelé ;
  - `verify_failing_blocks` : `tests/test_fail.py` avec `def test_fail():\n    assert 1 == 2\n` → code 2 et `corrige avant de terminer` ;
  - `verify_loop_guard` : même arbre, `stop_hook_active` vrai → code 0 et `signale-le explicitement`.
- [ ] **Étape 2 : constater l'échec** (`bash .claude/hooks/tests/run.sh`) : `py-check.sh` absent, `verify.sh` encore Rust.
- [ ] **Étape 3 : implémenter** `py-check.sh` et `verify.sh` ; `chmod +x` ; dans `settings.json`, remplacer `rust-check.sh` par `py-check.sh` ; `git rm .claude/hooks/rust-check.sh`. Toujours passer le chemin entre guillemets et après `--`.
- [ ] **Étape 4 : vérifier.** `bash .claude/hooks/tests/run.sh` : tous les cas `OK`, code 0.
- [ ] **Étape 5 : `simplify`, puis `security-review`** (injection par le chemin, `PATH`, sortie des commandes). Corriger en TDD ce qu'elles relèvent.
- [ ] **Étape 6 : vérification complète, puis commit.** `bash scripts/verify.sh`.
  `git commit -m "build(hooks): Python format, lint and type checks in Claude Code hooks"`

### Task 5 : CI

**Fichiers :**
- Modifier : `.github/workflows/ci.yml`

- [ ] **Étape 1 : réécrire `ci.yml`.** Déclencheurs inchangés (`pull_request`, `push` sur `main`). Un seul job `check` sur `ubuntu-latest` : `actions/checkout`, `astral-sh/setup-uv` (dernière version majeure, avec `enable-cache: true`), `uv python install`, `uv sync --locked`, `sudo apt-get update && sudo apt-get install -y tmux`, `bash scripts/verify.sh`, `bash .claude/hooks/tests/run.sh`. Les jobs `msrv`, `deny` et `machete` disparaissent.
- [ ] **Étape 2 : vérifier localement** la syntaxe (`uv run --with check-jsonschema check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/ci.yml`).
- [ ] **Étape 3 : commit.** La vérification sur GitHub se fait à la Task 9, à l'ouverture de la PR.
  `git commit -m "ci: run the Python verification and hook tests"`

### Task 6 : documentation de méthode et README

**Fichiers :**
- Modifier : `CLAUDE.md`, `docs/dev/developpement-assiste-par-ia.md`
- Créer : `README.md`

- [ ] **Étape 1 : `CLAUDE.md`.** Même structure (TDD, vérification complète, guide détaillé, langue, Git). Remplacer « écrit en Rust » par « écrit en Python » ; la vérification complète devient `bash scripts/verify.sh` ; `#[ignore]` devient `pytest.mark.skip`/`xfail` ; résumé du guide § 1–9 mis à jour (`syrupy` relu ligne par ligne, jamais `--snapshot-update` à l'aveugle ; union de dataclasses gelées, pas de `case _:`, `NewType` ; pas d'`assert` hors tests, pas de `cast`, pas d'`Any` ; exceptions par règle précise avec ` — raison` ; `hypothesis`, `syrupy`, `mutmut` ; hooks ; packages et règles d'imports ; `uv add` uniquement ; `/simplify` à la fin de chaque tâche de code et `/security-review` quand le code touche aux sous-processus, fichiers, SQL ou entrées externes). Langue : « Code, identifiants et commentaires en anglais ; interface utilisateur en anglais ; spécification, plans et guide en français ; messages de commit et titres de PR en anglais. »
- [ ] **Étape 2 : guide.** Réécrire l'introduction (« Rust permet » → le rôle de basedpyright, ruff et des tests de garde), § 2 et § 3 à partir de la conception § 4 (tableau compris, et la décision réversible sur basedpyright), § 4 à partir de la conception § 5.1–5.2, § 5 à partir de la conception § 5.3 (hooks `py-check.sh` et `verify.sh`, sorties concises), § 6 (fichiers courts, `CLAUDE.md` par package, données immuables, code synchrone sauf `meute.tui` et `meute.mcp`, cœur limité à la stdlib et pourquoi), § 7 (`uv add`, doc à jour, `uv.lock` commité, `pip-audit`, licences, `deptry`), § 8 (commits en anglais), § 9 (`bash scripts/verify.sh` et son contenu).
- [ ] **Étape 3 : `README.md`, en anglais.** Une phrase sur meute (reprise de la spécification § 1, traduite) ; statut : « Pre-alpha, being rewritten in Python » ; installation depuis les sources (`uv tool install` avec ou sans `--compile-bytecode` selon le rapport S6) ; développement (`uv sync`, `bash scripts/verify.sh`, lien vers le guide en précisant qu'il est en français) ; licence MIT ou Apache-2.0.
- [ ] **Étape 4 : vérifier.** `grep -rniE 'cargo|clippy|rust|insta|proptest|nextest' CLAUDE.md docs/dev/developpement-assiste-par-ia.md README.md` ne renvoie que des mentions historiques volontaires (tags `rust-plan-*`). Chaque commande citée correspond à `scripts/verify.sh` et aux hooks.
  `git commit -m "docs: development method and README for the Python codebase"`

### Task 7 : spécification fonctionnelle

**Fichiers :**
- Modifier : `docs/superpowers/specs/2026-10-15-meute-design.md`

- [ ] **Étape 1 : mentions de Rust.** § 1 (« application Rust » → « application Python »), § 3.1 et § 7.2 (« portage Rust du script actuel » → « portage Python »).
- [ ] **Étape 2 : § 4.2–4.3.** § 4.2 : préciser que `meute` est le script installé par `uv tool` et que `_entry` dispatche `ingest` avant tout import lourd. § 4.3 renommé « Paquet Python » : tableau et règles de la conception § 3.1–3.4, bibliothèques (Typer, Textual, `sqlite3`, migrations en fichiers SQL numérotés, `tomllib`/`tomlkit`, `datetime`/`zoneinfo`, `uuid`, SDK `mcp`, plus tard un client HTTP synchrone pour les forges).
- [ ] **Étape 3 : modèles.** Blocs ```rust des § 6.1 et § 9.1 réécrits en ```python : mêmes noms de types et de variantes, unions de dataclasses gelées pour les variantes porteuses de données (`Blocked(reason: str)`), `enum.Enum` pour les autres.
- [ ] **Étape 4 : § 13, 14, 16, 17.** § 13 : `toml_edit` → `tomlkit`. § 14 : ligne S6 avec le résultat et un lien vers le rapport. § 16, dernier point : exceptions typées (conception § 3.5), pas d'`assert` hors des tests. § 17 : outils de la conception § 5.1–5.2 (pytest, hypothesis, syrupy, les trois niveaux du TUI Textual, tmux jetable) et `bash scripts/verify.sh`.
- [ ] **Étape 5 : langue de l'interface.** Chercher `grep -niE 'français|french|« '` et décider ligne par ligne : les textes d'interface cités (« modifiée entre-temps », « Tâches indisponibles : raison », etc.) sont traduits en anglais, avec une note en tête de spécification : « L'interface est en anglais ; la spécification reste en français. »
- [ ] **Étape 6 : vérifier.** `grep -niE 'rust|cargo|crate|clap|ratatui|rusqlite|serde|jiff|thiserror|anyhow|tokio|rmcp|reqwest|toml_edit|insta|proptest' docs/superpowers/specs/2026-10-15-meute-design.md` ne renvoie que des mentions historiques volontaires.
  `git commit -m "docs(spec): Python architecture, English interface and spike S6"`

### Task 8 : feuille de route et nouveau plan 1

**Fichiers :**
- Modifier : `docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md`
- Créer : `docs/superpowers/plans/<date du jour>-meute-plan-1-python-socle-taches.md`

- [ ] **Étape 1 : feuille de route.** Ajouter en tête un paragraphe « Migration vers Python » (date, raison en une phrase, lien vers la conception, tags `rust-plan-1` et `rust-plan-2-wip`). Plan 1 : livrable inchangé, marqué « à refaire en Python ». Plan 2 : « plan Rust rédigé et largement implémenté sous `rust-plan-2-wip`, à réécrire pour Python après le plan 1 ». Règles communes : `cargo-mutants` → `mutmut`, ajout de `/simplify` et `/security-review`. Reports : ceux du « Plan 2, première tâche » et « Avant les plans 2 à 6 » sont marqués « intégrés au plan 1 Python » ; celui du plan 3 (ouverture concurrente) est conservé tel quel.
- [ ] **Étape 2 : nouveau plan 1**, rédigé avec le skill `superpowers:writing-plans`, en français, à partir de la spécification réécrite (Task 7), de la conception de la migration et du guide (Task 6) :
  - périmètre : spécification § 9.1–9.3, 13 (configuration, base, migrations), 16 et 17, sans les Tasks 1 et 2 du plan 1 Rust (outillage et hooks, faits ici) ;
  - reports intégrés dès les premières tâches : `StatusKind` sans données pour le filtre de statut, filtre `done` qui implique les tâches terminées dans le cœur, forme `{"kind": …, "value": …}` de `Due` alignée sur le JSON de `Task`, aucune validation de statut jetable dans la CLI, utilitaires de test communs dans `tests/conftest.py` ;
  - **référence de comportement** : les tests de `crates/meute-core` et `crates/meute` sous `rust-plan-2-wip` (hors sessions, dépôts et réconciliation) et le rapport `docs/dev/mutants/2026-plan-1.md`. Chaque tâche cite les tests Rust qu'elle remplace (`git show rust-plan-2-wip:<chemin>`) ; les textes affichés sont fixés **en anglais** dans le plan ;
  - fin du plan : `mutmut`, `/simplify`, `/security-review`, PR.
- [ ] **Étape 3 : relecture par l'auteur.** Présenter le plan 1 à l'auteur et intégrer ses remarques avant de passer à la Task 9.
  `git commit -m "docs: roadmap after the Python migration and Python plan 1"`

### Task 9 : revue finale et PR

- [ ] **Étape 1 : `security-review`** sur toute la branche (`git diff main...HEAD`) ; corriger en TDD ce qui est relevé.
- [ ] **Étape 2 : vérification complète** (`bash scripts/verify.sh` et `bash .claude/hooks/tests/run.sh`), sortie citée.
- [ ] **Étape 3 : PR.** `git push -u origin chore/python-migration`, puis `gh pr create --assignee gaetinux --title "Migrate meute from Rust to Python"`. Corps : résumé, résultat du spike S6 (médiane et décision), liste des tâches, exceptions aux règles (`noqa` et `pyright: ignore` ajoutés, avec leurs raisons), rappel des tags `rust-plan-1` et `rust-plan-2-wip`. Le corps se termine par `🤖 Generated with [Claude Code](https://claude.com/claude-code)`, **sans lien de session**.
- [ ] **Étape 4 : CI verte** sur la PR (`gh pr checks --watch`). En cas d'échec, corriger en TDD, sans toucher aux tests.
