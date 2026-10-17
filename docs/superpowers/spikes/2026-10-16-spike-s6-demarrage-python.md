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

## Commandes de reproduction

```bash
# variante 1 : interpréteur système (/usr/bin/python3.13), sans venv ni script d'entrée uv
hyperfine -N --warmup 5 --runs 100 --export-json v1.json 'python3 -I -c pass'
# variante 2
uv tool install --force spikes/s6
hyperfine -N --warmup 5 --runs 100 --input hook.json --export-json v2.json 'meute-s6 ingest hook PostToolUse'
# variante 3
uv tool install --force --compile-bytecode spikes/s6
hyperfine -N --warmup 5 --runs 100 --input hook.json --export-json v3.json 'meute-s6 ingest hook PostToolUse'
# variante 4
hyperfine -N --warmup 5 --runs 100 --input statusline.json --export-json v4.json 'meute-s6 ingest statusline'
# importtime : interpréteur du venv de l'outil (shebang de meute-s6), même entrée
$(head -1 $(command -v meute-s6) | sed 's/^#!//') -X importtime -c \
  "import sys; sys.argv=['meute-s6','ingest','hook','PostToolUse']; from meute_s6._entry import main; main()" \
  < hook.json 2> raw.txt; sort -t'|' -k2 -n -r raw.txt | head -16
```

`MEUTE_S6_DB` pointe vers un dossier temporaire sous `$HOME`. hyperfine 2.0 n'exporte pas de champ `times` : médiane, p95 (95e valeur sur 100, triée) et max sont calculés à partir de `results[0].measurements[].time_wall_clock.value`.

**Interpréteurs.** La variante 1 mesure le Python système (`/usr/bin/python3.13`, avec `-I`), alors que les variantes 2 à 4 lancent le script d'entrée généré par uv, dont le shebang vise le Python du venv de l'outil (également 3.13.5, mais avec `site` complet et le `.pth` du paquet). Le « plancher » de 7,9 ms est donc indicatif, pas strictement comparable.

## Décision

Médiane de la meilleure variante parmi 2 et 3 : **46,7 ms, tranche 35 à 50 ms : on continue**, mais avec une marge quasi nulle (p95 de 49,9 et 50,9 ms pour les variantes 3 et 4 ; médiane de 47,6 ms pour la variante 4). Aucune médiane ne dépasse 50 ms, le point d'arrêt n'est pas déclenché.

**Conséquence de la tranche (conception § 6) : le plan continue avec le test `importtime` comme garde stricte et obligatoire**, exécuté en test d'intégration, sans exception.

**Conclusion adoptée :** `meute/core/__init__.py` ne ré-exporte rien (aucun import), et `ingest` importe uniquement les sous-modules de `core` dont il a besoin.

## Part du paquet `core` : deux mesures, deux réserves

- `-X importtime` : 22,4 ms cumulés pour `meute_s6.core`, soit environ 47 % de la médiane de 46,7 ms. Réserves : `-X importtime` ajoute lui-même un surcoût par import, et le cumulé recouvre des modules partagés (`json`, `dataclasses`, `re`, `typing`, `sqlite3`) que `ingest` importerait de toute façon, que `core` les tire ou non.
- Mesure complémentaire en temps réel : `python -c 'import meute_s6.core'` dure 39,7 ms, soit environ 32 ms au-dessus du plancher de 7,9 ms (indicatif, cf. interpréteurs), contre 14,5 ms pour `import json, sqlite3` + décodage. Réserve : cette valeur inclut le démarrage de l'interpréteur du venv et les imports partagés.

Les deux chiffres ne sont pas directement réconciliables (surcoût d'`importtime`, recouvrement). Ordre de grandeur retenu : le paquet `core` pèse entre un tiers et la moitié de la médiane, dont une partie est incompressible (imports standard partagés). Le surcoût propre à `core` (au-delà de `json`, `sqlite3`, `dataclasses`) n'a pas été isolé.

## Recommandation sur `--compile-bytecode`

Aucun gain mesurable (46,9 contre 46,7 ms ; l'écart est dans le bruit). Cette mesure suit 5 exécutions de chauffe, donc elle ne dit rien de l'exécution à froid, non mesurée. Le bytecode est de toute façon écrit à la première exécution quand le dossier est inscriptible. Recommandation : le garder (il déplace le coût à l'installation, ce qui allonge celle-ci d'une durée non mesurée, et évite la compilation à la première exécution ou dans un dossier non inscriptible), sans compter dessus pour tenir le budget.

## Pistes (si la marge doit grandir)

**Estimation non mesurée :** limiter les imports du chemin `ingest` aux sous-modules nécessaires pourrait ramener la médiane vers 25 à 30 ms. Ce chiffre est une extrapolation à partir des mesures ci-dessus, à confirmer sur le vrai code (conception § 6).
