# meute

Gestionnaire de sessions Claude Code en CLI/TUI, écrit en Python. Spécification : [docs/superpowers/specs/2026-10-15-meute-design.md](docs/superpowers/specs/2026-10-15-meute-design.md). Conception de la migration : [docs/superpowers/specs/2026-10-16-migration-python-design.md](docs/superpowers/specs/2026-10-16-migration-python-design.md). Feuille de route : [docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md](docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md).

## TDD systématique (obligatoire)

- Pour chaque comportement : écrire le test, le voir échouer pour la bonne raison, écrire le code minimal, refactoriser au vert.
- Un correctif de bug commence par un test qui reproduit le bug.
- **Ne jamais modifier, supprimer ni désactiver (`pytest.mark.skip`, `pytest.mark.xfail`) un test existant pour le faire passer.** Si un test semble faux, s'arrêter et le signaler.

## Vérification complète (avant d'annoncer « terminé »)

```bash
bash scripts/verify.sh
```

À la fin de chaque tâche de code : lancer `/simplify`. Quand le code touche aux sous-processus, aux fichiers, à SQL ou à des entrées externes (hooks, MCP) : lancer aussi `/security-review`.

## Guide détaillé

Voir [docs/dev/developpement-assiste-par-ia.md](docs/dev/developpement-assiste-par-ia.md) :

- § 1 TDD : test d'abord, `syrupy` relu ligne par ligne, jamais `--snapshot-update` à l'aveugle.
- § 2 Typage : union de dataclasses gelées, pas de `case _:` sur nos types, `NewType` pour les identifiants, docstrings sur tout le public de `meute.core`.
- § 3 Lints : pas d'`assert` hors tests, pas de `cast`, pas d'`Any`, pas de `print` dans les bibliothèques ; exception par règle précise avec ` — raison`, modes pyright abaissés interdits.
- § 4 Tests : `hypothesis` pour les analyseurs, `syrupy` pour les sorties, `mutmut` en fin de plan. Pas encore installés : chaque plan les ajoute avec `uv add --dev` quand il en a besoin le premier.
- § 5 Boucle rapide : hooks `.claude/` (`py-check.sh`, `verify.sh`), sorties concises.
- § 6 Organisation : fichiers de moins de 300 lignes, données immuables, code synchrone, packages et règles d'imports (`meute.core` limité à la stdlib, `meute/core/__init__.py` vide d'imports).
- § 7 Dépendances : `uv add` uniquement, docs à jour, `uv.lock` commité.
- § 8 Git : voir ci-dessous.
- § 9 Vérification complète : `bash scripts/verify.sh`.

## Langue

Code, identifiants et commentaires en anglais ; interface utilisateur en anglais ; spécification, plans et guide en français ; messages de commit et titres de PR en anglais.

## Git

Une branche par plan, une PR assignée à `gaetinux`, jamais de push sur `main`. Les commits finissent par `Co-Authored-By: Claude …`, sans ligne `Claude-Session` ni lien de session.
