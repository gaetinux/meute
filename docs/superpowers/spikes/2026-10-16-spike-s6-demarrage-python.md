# Spike S6 — Temps de démarrage de `meute ingest` en Python

- Date : 2026-10-16
- Versions : Python 3.13.5, uv 0.13.1, hyperfine 2.0.0, Linux 6.18.54.1-microsoft-standard-WSL2 (ext4, hors `/mnt/c`)
- Référence : conception `docs/superpowers/specs/2026-10-16-migration-python-design.md`, § 6 ; seuil de la spécification § 7.3 (les hooks appellent `meute ingest` à chaque événement Claude)
- Méthode : prototype jetable (`uv init --package`, point d'entrée `meute_s6._entry:main`, import paresseux de `typer` hors du chemin `ingest`, paquet `core` de 12 modules d'environ 50 lignes important `dataclasses`, `enum`, `datetime`, `zoneinfo`, `json`, `sqlite3`, `pathlib`, `re`, `typing`). `ingest` lit le JSON sur stdin, ouvre une base SQLite en WAL (`timeout=0.2`), crée la table si besoin, insère une ligne, commit. `statusline` affiche en plus une ligne. Mesure : `hyperfine -N --warmup 5 --runs 100 --input <json>`, base dans un dossier temporaire sous `$HOME`. Le JSON du hook est reconstitué d'après les champs du § S2 du rapport S1-S5, celui de la statusline d'après le § S3 (le rapport ne contient pas de JSON brut). Le prototype est supprimé.

## Résultats (ms, 100 exécutions)

| # | Variante | Médiane | p95 | Max |
|---|---|---|---|---|
| 1 | `python3 -I -c pass` (plancher) | 7,9 | 8,2 | 8,4 |
| 2 | `uv tool install`, `meute-s6 ingest hook PostToolUse` | 46,9 | 49,2 | 52,4 |
| 3 | idem avec `--compile-bytecode` | 46,7 | 49,9 | 59,2 |
| 4 | variante 3, `meute-s6 ingest statusline` | 47,6 | 50,9 | 53,3 |

`typer` n'apparaît dans aucun `-X importtime` des variantes 2 à 4 (0 occurrence).

## `-X importtime` (variante 3, cumulé en µs, extrait)

```
 22426  meute_s6.core            (12 modules, dont m01 : 11977)
  6215  meute_s6.ingest
  5826  dataclasses  (dont inspect : 4846)
  4744  json
  3749  re
  1760  zoneinfo
  1748  site
  1635  typing
  1399  sqlite3
```

Mesures complémentaires (diagnostic, hors brief) avec l'interpréteur de l'outil : `import json, sqlite3` + décodage = 14,5 ms ; `import meute_s6.core` seul = 39,7 ms.

## Décision

Médiane de la meilleure variante parmi 2 et 3 : **46,7 ms, tranche 35 à 50 ms : on continue**, mais avec une marge quasi nulle. Le p95 des variantes 3 et 4 touche 50 ms (49,9 et 50,9) et la variante 4 a une médiane de 47,6 ms, sous le seuil de 50 ms mais à moins de 3 ms. Aucune variante ne dépasse 50 ms en médiane, donc le point d'arrêt n'est pas déclenché.

## Recommandation sur `--compile-bytecode`

Aucun gain mesurable (46,9 contre 46,7 ms ; l'écart est dans le bruit). Les `.pyc` sont de toute façon écrits à la première exécution quand le dossier est inscriptible, et la mesure a lieu après 5 exécutions de chauffe. Recommandation : le garder (coût nul, évite la première exécution à froid et un dossier non inscriptible), sans compter dessus pour tenir le budget.

## Pistes (si la marge doit grandir)

Le prototype est pessimiste sur un point : chaque module a des imports lourds (`dataclasses` entraîne `inspect`, `re`, `zoneinfo`, `typing`) et le plancher de l'interpréteur est de 8 ms. Les 22 ms du paquet `core` pèsent donc ~40 % du total. Le chemin `ingest` devrait importer uniquement ce dont il a besoin (pas le paquet `core` entier, `__init__` sans import en cascade), ce qui ramènerait vraisemblablement la médiane vers 25 à 30 ms. À vérifier dans le vrai code (conception § 6).
