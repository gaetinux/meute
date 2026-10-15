# Développement assisté par IA sur meute

meute est développé à 100 % avec Claude Code. Ce document décrit les règles et les outils qui rendent ce mode de travail fiable. Il fait référence pour les humains comme pour les agents. Le fichier `CLAUDE.md` à la racine en reprend l'essentiel et renvoie ici pour le détail.

**Le principe.** Plus le compilateur, les lints et les tests attrapent d'erreurs, moins il reste de choses à relire. Rust permet de pousser ce principe très loin : chaque règle ci-dessous transforme une erreur typique d'agent en échec de compilation, de lint ou de test.

## 1. TDD systématique

Tout développement se fait en TDD strict :

1. écrire le test ;
2. le lancer et le voir **échouer pour la bonne raison** (pas une simple faute de frappe) ;
3. écrire le code minimal qui le fait passer ;
4. refactoriser, avec les tests au vert.

Règles associées :

- Aucun code de production n'est écrit sans un test qui l'exige.
- Un correctif de bug commence par un test qui reproduit le bug.
- **On ne modifie, ne supprime ni ne désactive (`#[ignore]`) jamais un test existant pour le faire passer.** Si un test semble faux, on s'arrête et on le signale explicitement, avec la raison, dans le message de commit et dans la PR.
- Les instantanés `insta` (§ 4) sont relus ligne par ligne par rapport à la spécification avant d'être acceptés (`cargo insta review`). On n'utilise jamais `cargo insta accept` à l'aveugle.

## 2. Le compilateur comme spécification

- **États impossibles irreprésentables.** On utilise des types dédiés pour les identifiants (`TaskId(i64)` plutôt qu'un `i64` nu) et des enums porteuses de données (`Blocked { reason }` plutôt qu'un statut et une raison séparés).
- **Pas de `_ =>` sur nos propres enums.** Le lint `clippy::wildcard_enum_match_arm` est activé. Quand on ajoute une variante, le compilateur liste tous les `match` à compléter.
- **Pas de `#[non_exhaustive]` sur les types internes au workspace**, car il désactive précisément cette vérification.
- **Des `///` sur tout élément public de `meute-core`** (`#![warn(missing_docs)]`, transformé en erreur par `-D warnings`). Ces commentaires sont le contrat que lisent les agents qui travaillent dans les autres crates.

## 3. Lints contre les mauvaises habitudes des agents

Ils sont déclarés dans `[workspace.lints]` du `Cargo.toml` racine, et chaque crate déclare `[lints] workspace = true`.

| Lint | Niveau | Ce qu'il empêche |
|---|---|---|
| `rust::unsafe_code` | `forbid` | tout code `unsafe` |
| `clippy::unwrap_used`, `clippy::expect_used` | `deny` | les paniques de facilité (autorisées dans les tests via `clippy.toml`) |
| `clippy::todo`, `clippy::unimplemented` | `deny` | le code laissé à moitié écrit |
| `clippy::dbg_macro` | `deny` | les traces de débogage oubliées |
| `clippy::allow_attributes_without_reason` | `deny` | un `#[allow(...)]` sans `reason = "…"`, l'échappatoire classique d'un agent bloqué |
| `clippy::wildcard_enum_match_arm` | `deny` | le `_ =>` qui masque une variante oubliée |
| `clippy::print_stdout`, `clippy::print_stderr` | `deny`, dans `meute-core` seulement | les sorties console depuis la bibliothèque |
| `rust::missing_docs` | `warn`, dans `meute-core` seulement | les éléments publics non documentés |

Toute exception passe par `#[expect(lint, reason = "…")]`, de préférence à `#[allow]`. `expect` signale l'exception si elle devient inutile. Chaque exception est mentionnée dans la PR.

## 4. Des tests qui testent vraiment

Le risque principal du TDD avec une IA, ce sont des tests qui passent sans rien vérifier. Trois outils complètent les tests unitaires et d'intégration :

- **`proptest`** : tests de propriétés sur les analyseurs, par exemple la saisie rapide. On génère des milliers d'entrées au hasard et on vérifie des invariants (« ne panique jamais », « le titre n'est jamais vide quand le résultat est `Ok` »).
- **`insta`** : tests d'instantané pour les sorties textuelles (CLI, puis rendu du TUI). La relecture se fait sur un diff lisible.
- **`cargo-mutants`** : il introduit des mutations dans le code (une condition inversée, une valeur par défaut renvoyée…) et vérifie qu'un test échoue. Une mutation « manquée » révèle un test trop faible. Il est lancé **à la fin de chaque plan**, car il est trop lent pour chaque tâche. Chaque mutation manquée donne lieu soit à un nouveau test (en TDD), soit à une justification écrite dans la PR.

## 5. Une boucle de rétroaction rapide et automatique

### Hooks Claude Code du dépôt (`.claude/settings.json`)

| Hook | Déclencheur | Action |
|---|---|---|
| `.claude/hooks/rust-check.sh` | `PostToolUse` sur `Edit`, `Write` ou `MultiEdit` d'un fichier `.rs` | Lance `cargo fmt` sur le fichier, puis `cargo check --workspace --all-targets --message-format=short`. En cas d'erreur, il sort avec le code **2** et écrit les erreurs sur stderr : Claude les voit immédiatement |
| `.claude/hooks/verify.sh` | `Stop` et `SubagentStop` | Si des fichiers Rust ou Cargo ont changé (`git status --porcelain`), il exige que `cargo clippy --all-targets -- -D warnings` et `cargo nextest run` passent. Sinon, il sort avec le code 2 : l'agent ne peut pas annoncer « terminé » |

Garde-fou contre les boucles infinies : si le champ `stop_hook_active` est vrai, `verify.sh` laisse l'agent s'arrêter. Il écrit alors sur stderr que la vérification a échoué, et l'agent doit le signaler explicitement dans son rapport.

### Compilation et sorties

- **Linker `mold`**, via `clang`, configuré dans `.cargo/config.toml` pour `x86_64-unknown-linux-gnu`. Prérequis local : `sudo apt install mold clang`. La CI l'installe avec `rui314/setup-mold`.
- **Sorties concises** : `cargo check --message-format=short` et `cargo nextest run --failure-output final --hide-progress-bar`. Moins de bruit, c'est plus de contexte utile.
- **Découpage en crates** : une modification ne recompile que la crate concernée et celles qui en dépendent.

## 6. Contexte et organisation du code

- **Fichiers courts** : visez moins de 300 lignes, avec un maximum indicatif de 400. Un module par responsabilité. Un agent raisonne mieux sur un fichier qu'il voit en entier.
- **`CLAUDE.md` par crate** quand une crate a des règles propres (par exemple `crates/meute-tmux/CLAUDE.md` : « tests uniquement sur un serveur tmux jetable »). Claude Code le charge quand il travaille dans ce dossier.
- **Données possédées plutôt que durées de vie complexes.** En dehors des chemins critiques, on préfère des types possédés et `.clone()` à des signatures avec plusieurs durées de vie. Un agent peut perdre beaucoup de temps à se battre avec le borrow checker pour un gain nul.
- **Code synchrone par défaut.** `tokio` est réservé à `meute-mcp` (spécification § 4.3).

## 7. Dépendances

- **Ajouter une dépendance uniquement avec `cargo add`**, qui prend la dernière version publiée, puis consulter sa documentation **à jour** (plugin context7, `docs.rs` ou `cargo doc --open`). Ne jamais se fier à la mémoire du modèle : les agents inventent souvent des API d'anciennes versions.
- **`Cargo.lock` est commité**, puisque meute est un binaire.
- **`cargo deny check`** en CI vérifie les licences (liste blanche dans `deny.toml`), les avis de sécurité RustSec et les sources des dépendances.
- **`cargo machete`** en CI repère les dépendances déclarées mais inutilisées.

## 8. Workflow Git

- Une branche par plan ou par modification, jamais de commit ni de push sur `main`.
- Un commit par tâche, avec tous les tests au vert.
- Une PR assignée à `gaetinux`, qui la relit et la merge lui-même.
- Les messages de commit se terminent par `Co-Authored-By: Claude …`, **sans lien de session**.

## 9. Vérification complète

C'est la commande que lance la CI, et qu'un agent doit voir passer avant d'annoncer qu'une tâche est terminée :

```bash
cargo fmt --check \
  && cargo clippy --workspace --all-targets -- -D warnings \
  && cargo nextest run --workspace \
  && cargo deny check \
  && cargo machete
```
