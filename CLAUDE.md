# meute

Gestionnaire de sessions Claude Code en CLI/TUI, écrit en Rust. Spécification : [docs/superpowers/specs/2026-10-15-meute-design.md](docs/superpowers/specs/2026-10-15-meute-design.md). Feuille de route : [docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md](docs/superpowers/plans/2026-10-15-meute-v1-roadmap.md).

## TDD systématique (obligatoire)

- Pour chaque comportement : écrire le test, le voir échouer pour la bonne raison, écrire le code minimal, refactoriser au vert.
- Un correctif de bug commence par un test qui reproduit le bug.
- **Ne jamais modifier, supprimer ni désactiver (`#[ignore]`) un test existant pour le faire passer.** Si un test semble faux, s'arrêter et le signaler.

## Vérification complète (avant d'annoncer « terminé »)

```bash
cargo fmt --check \
  && cargo clippy --workspace --all-targets -- -D warnings \
  && cargo nextest run --workspace \
  && cargo deny check \
  && cargo machete
```

## Guide détaillé

Voir [docs/dev/developpement-assiste-par-ia.md](docs/dev/developpement-assiste-par-ia.md) :

- § 1 TDD : test d'abord, `insta` relu ligne par ligne, jamais `cargo insta accept` à l'aveugle.
- § 2 Compilateur : types dédiés pour les identifiants, pas de `_ =>` sur nos enums, pas de `#[non_exhaustive]` interne, `///` sur tout le public de `meute-core`.
- § 3 Lints : `unsafe` interdit, pas de `unwrap`/`expect`/`todo`/`dbg!`, `#[allow]` sans raison interdit ; exceptions via `#[expect(lint, reason = "…")]`.
- § 4 Tests : `proptest` pour les analyseurs, `insta` pour les sorties, `cargo-mutants` en fin de plan.
- § 5 Boucle rapide : hooks `.claude/`, linker `mold`, sorties concises.
- § 6 Organisation : fichiers de moins de 300 lignes, données possédées, code synchrone.
- § 7 Dépendances : `cargo add` uniquement, docs à jour, `Cargo.lock` commité.
- § 8 Git : voir ci-dessous.
- § 9 Vérification complète : commande ci-dessus.

## Langue

Code, identifiants et commentaires en anglais ; interface utilisateur en français.

## Git

Une branche par plan, une PR assignée à `gaetinux`, jamais de push sur `main`. Les commits finissent par `Co-Authored-By: Claude …`, sans lien de session.
