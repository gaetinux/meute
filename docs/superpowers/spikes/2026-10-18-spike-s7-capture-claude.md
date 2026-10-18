# Spike S7 — Capture des messages réels de Claude Code 2.1.302

- Date : 2026-10-18. Claude Code 2.1.302, modèle `claude-opus-5-5`, tmux 3.5a (WSL2).
- Méthode : `bash scripts/capture-claude-fixtures.sh <dossier brut>`. Serveur tmux jetable `-L meute-capture-<uuid> -f /dev/null`, tué à la fin ; dossier de travail : le dépôt meute (déjà approuvé) ; `claude --settings <fichier de capture> --session-id <uuid> --permission-mode manual --name=<titre>`. Chaque hook et la statusline copient stdin dans `raw/<MEUTE_SESSION>-<type>-<nanosecondes>.json`.
- Fixtures nettoyées : `tests/fixtures/claude/2.1.302/` (`hooks/<Event>-<n>.json` numérotés dans l'ordre d'arrivée, toutes sessions confondues ; `statusline-<n>.json`, une par forme distincte ; `agents.json` ; `settings.json`). Nettoyage : `/home/<utilisateur>` → `/home/user`, dossier de capture → `/tmp/capture`, nom d'utilisateur → `user`, adresses e-mail → `redacted`, `transcript_path` et `agent_transcript_path` → `/home/user/.claude/projects/x/…`.
- Coût : 0,51 $ pour la session principale (`cost.total_cost_usd` de la dernière statusline), plus un premier essai interrompu (deux tours). Plus que « quelques centimes » : le `/compact` et le sous-agent en sont la plus grande part.

## Synthèse

| Question | Réponse | Effet sur le plan |
|---|---|---|
| 1. Forme de `--settings` | ✅ **Sans `matcher`** pour les 11 événements ; tous se déclenchent (sauf `Notification`, jamais émis) | Aucun |
| 2. Champs | `SessionStart.model` est une **chaîne** ; la statusline donne un objet. Voir les écarts ci-dessous | **Plusieurs écarts** (permission refusée sans `Stop`, sous-agent en arrière-plan, `echo` sans permission) |
| 3. Hooks de l'utilisateur | `~/.claude/settings.json` n'a ni hooks ni statusline. Les hooks du **projet** et des **plugins** restent actifs à côté de ceux de `--settings` | `--settings` s'ajoute, ne remplace pas |
| 4. `--name=<titre>` | ✅ accepté, y compris `--name=-meute-capture-dash` | Toujours la forme `--name=` |
| 5. `claude agents --json` | **248,5 ms ± 8,8 ms** (min 241,5, max 267,5 ; 162 Mio) avec 3 sessions actives | Délai de 400 ms du plan suffisant |

## 1. Forme du fichier `--settings`

Le fichier qui a fonctionné (`tests/fixtures/claude/2.1.302/settings.json`) déclare chaque événement **sans `matcher`** :

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "/tmp/capture/capture.sh SessionStart"}]}],
    "PreToolUse":   [{"hooks": [{"type": "command", "command": "/tmp/capture/capture.sh PreToolUse"}]}],
    "…": "même forme pour UserPromptSubmit, PermissionRequest, PostToolUse, PreCompact, SubagentStart, SubagentStop, Stop, SessionEnd, Notification"
  },
  "statusLine": {"type": "command", "command": "/tmp/capture/capture.sh statusline"}
}
```

Sans `matcher`, `PreToolUse`, `PermissionRequest` et `PostToolUse` se déclenchent pour tous les outils (`Bash` et `Agent` observés). Aucune question n'est posée pour approuver les hooks du fichier.

Ordre réel des messages de la session principale :

```
SessionStart statusline UserPromptSubmit Stop                         (pong)
UserPromptSubmit PreToolUse PostToolUse Stop                          (echo, sans permission)
UserPromptSubmit PreToolUse PermissionRequest                         (mkdir, refusé : ni PostToolUse ni Stop)
UserPromptSubmit PreToolUse PostToolUse SubagentStart SubagentStop Stop
UserPromptSubmit Stop                                                 (<task-notification> du sous-agent)
PreCompact SubagentStop SubagentStop SessionStart                     (/compact)
SessionEnd                                                            (/exit)
```

## 2. Champs réels de chaque hook

Champs communs : `session_id`, `transcript_path`, `cwd`, `hook_event_name`, et **`scratchpad_dir`** (nouveau, `/tmp/claude-<uid>/<projet>/<session>/scratchpad`). La plupart ont aussi `prompt_id`, `permission_mode` et `effort` (`{"level": "medium"}`). `SessionStart`, `PreCompact`, `SubagentStart` et `SessionEnd` n'ont **pas** de `permission_mode`.

**`SessionStart`** — `model` est une **chaîne** ; `source` vaut `startup` puis `compact` ; `session_title` reprend `--name`. Celui de `compact` a un `prompt_id`.

```json
{"hook_event_name": "SessionStart", "source": "startup", "model": "claude-opus-5-5", "session_title": "meute-capture"}
```

**`UserPromptSubmit`** — `prompt`, `permission_mode`, `session_title`. **Écart :** la fin d'un sous-agent en arrière-plan arrive comme un `UserPromptSubmit` dont le `prompt` commence par `<task-notification>` (`UserPromptSubmit-5.json`), suivi d'un second `Stop`. `/compact` et `/exit` n'émettent pas de `UserPromptSubmit`.

**`PreToolUse` / `PostToolUse`** — `tool_name`, `tool_input`, `tool_use_id` ; `PostToolUse` ajoute `tool_response` et `duration_ms`.

```json
{"hook_event_name": "PostToolUse", "tool_name": "Bash",
 "tool_input": {"command": "echo meute-capture", "description": "Print a marker string"},
 "tool_response": {"stdout": "meute-capture", "stderr": "", "interrupted": false, "isImage": false, "noOutputExpected": false},
 "duration_ms": 56}
```

**`PermissionRequest`** — `tool_name`, `tool_input` (le même objet que `PreToolUse`), `permission_suggestions`. `permission_mode` vaut **`"default"`** alors que la session est lancée avec `--permission-mode manual` (l'interface affiche « manual mode on ») : le hook rapporte `manual` sous le nom `default`.

```json
{"hook_event_name": "PermissionRequest", "permission_mode": "default", "tool_name": "Bash",
 "tool_input": {"command": "mkdir /tmp/capture/denied", "description": "Create a directory in another session's scratchpad"},
 "permission_suggestions": [
   {"type": "addDirectories", "directories": ["/tmp/capture"], "destination": "session"},
   {"type": "setMode", "mode": "acceptEdits", "destination": "session"}]}
```

**Écarts sur les permissions :**
- `echo meute-capture` **ne demande pas de permission** (commande en lecture seule, autorisée d'office) : `PreToolUse` puis `PostToolUse`, sans `PermissionRequest`. Le script demande donc ensuite `mkdir /tmp/capture/denied`, **refusé** par `Échap` (le dossier n'a pas été créé).
- Après un refus, **aucun `Stop` ni `PostToolUse`** : l'écran affiche « Interrupted · What should Claude do instead? » et l'invite revient. L'état « permission demandée » ne se termine donc pas forcément par un `Stop` ; le message suivant est le `UserPromptSubmit` du prompt suivant (ou rien). La Task 4 doit en tenir compte (absence de hook ⇒ « stuck? » après le délai, ou statut de `claude agents --json`).

**`SubagentStart` / `SubagentStop`** — `agent_id`, `agent_type`. L'outil s'appelle **`Agent`** (et non `Task`), et le sous-agent tourne **en arrière-plan** (`tool_response.isAsync: true`, `"status": "async_launched"`) : le `Stop` du tour arrive **avant** le `SubagentStop` réel.

```json
{"hook_event_name": "SubagentStart", "agent_id": "aba6836016bc01043", "agent_type": "general-purpose"}
{"hook_event_name": "SubagentStop", "agent_id": "aba6836016bc01043", "agent_type": "general-purpose",
 "stop_hook_active": false,
 "agent_transcript_path": "/home/user/.claude/projects/x/7393e221-…/subagents/agent-aba6836016bc01043.jsonl",
 "last_assistant_message": "pong",
 "background_tasks": [{"id": "aba6836016bc01043", "type": "subagent", "status": "running",
                       "description": "Reply pong", "agent_type": "general-purpose"}],
 "session_crons": []}
```

Le bruit relevé en S2 est confirmé : `/compact` émet deux `SubagentStop` avec `agent_type: ""` et sans `SubagentStart` (le second porte le résumé de compaction dans `last_assistant_message`).

**`Stop`** — `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`.

**`PreCompact`** — `trigger` (`"manual"`), `custom_instructions` (`null`). Aucun `Stop` après `/compact`.

```json
{"hook_event_name": "PreCompact", "trigger": "manual", "custom_instructions": null}
```

**`SessionEnd`** — `reason` vaut **`"prompt_input_exit"`** après `/exit` (les deux sessions).

**`Notification`** — jamais émis : la permission a été refusée en moins d'une seconde, et aucune attente d'inactivité n'a eu lieu.

**Statusline** (`statusline-1.json` au démarrage, `statusline-2.json` après le premier tour ; 10 appels pour la session) — `model` est un **objet** `{"id": "claude-opus-5-5", "display_name": "Opus 5.5"}` ; `session_name` ; `workspace.repo` `{"host", "owner", "name"}` ; `context_window.used_percentage` vaut `null` au démarrage, puis un entier ; `rate_limits.five_hour` / `seven_day` `{"used_percentage", "resets_at"}` (secondes Unix) apparaissent après le premier appel à l'API, de même que `prompt_cache`. Nouveaux : `effort`, `thinking.enabled`, `fast_mode`, `exceeds_200k_tokens`.

```json
"rate_limits": {"five_hour": {"used_percentage": 27, "resets_at": 1792340400},
                "seven_day": {"used_percentage": 42, "resets_at": 1792717200}}
```

## 3. Les hooks de l'utilisateur restent-ils actifs ?

`~/.claude/settings.json` (lu sans modification) n'a que `enabledPlugins`, `language`, `theme` et `agentPushNotifEnabled` : **ni hooks ni statusline**. La question ne peut donc pas être tranchée pour ce fichier précis.

En revanche, le transcript de la session montre que les autres sources de hooks **restent actives** et s'exécutent à côté de celles de `--settings` : pour chaque `Stop`, trois commandes (`hookCount: 3`) :

```json
{"hookCount": 3, "hookInfos": [
  {"command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/verify.sh", "durationMs": 23},
  {"command": "/tmp/capture/capture.sh Stop", "durationMs": 10},
  {"command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/sg-python.sh\" \"${CLAUDE_PLUGIN_ROOT}/hooks/security_reminder_hook.py\""}]}
```

et le `SessionStart` du plugin superpowers (`"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" session-start`, `exitCode: 0`) au démarrage et après la compaction. **`--settings` ajoute ses hooks aux autres, il ne les remplace pas** ; par analogie, des hooks dans `~/.claude/settings.json` resteraient très probablement actifs.

## 4. `--name=<titre>`

`--name=meute-capture` et `--name=-meute-capture-dash` sont acceptés. Le titre qui commence par `-` apparaît tel quel dans `SessionStart.session_title`, dans la statusline (`"session_name": "-meute-capture-dash"`), dans `claude agents --json` (`"name": "-meute-capture-dash"`) et dans le bord de la zone de saisie. La forme en deux arguments (`--name -titre`) n'a pas été essayée : meute doit toujours passer `--name=<titre>`.

## 5. `claude agents --json`

`hyperfine -N --runs 10 'claude agents --json'`, pendant que deux sessions de capture (et la session de l'auteur) tournent :

```
Benchmark 1: claude agents --json (10 runs)
  Wall Time    248.5 ms  ±     8.8 ms     241.5 ms  …   267.5 ms
  Memory       162.0 MiB ±     0.3 MiB    161.6 MiB …   162.4 MiB
```

Forme d'une entrée (`agents.json`, réduit aux deux sessions de capture) :

```json
{"pid": 388326, "cwd": "/home/user/git/poc-app-rust", "kind": "interactive", "startedAt": 1792327897812,
 "sessionId": "7393e221-2a26-44ab-ae9c-fc905efac6e6", "name": "meute-capture", "status": "idle"}
```

`startedAt` est en **millisecondes** Unix. Le champ `state` relevé en S1 n'apparaît pas pour des sessions interactives inactives.

## Écarts par rapport au plan

1. Une permission refusée ne produit ni `Stop` ni `PostToolUse` (Task 4 : l'état « permission » doit pouvoir être quitté par le `UserPromptSubmit` suivant).
2. Le sous-agent tourne en arrière-plan : `Stop` avant `SubagentStop`, puis un `UserPromptSubmit` `<task-notification>` et un second `Stop` (Task 4 : un `Stop` n'implique pas qu'aucun sous-agent ne tourne ; `background_tasks` le dit).
3. `echo` ne demande pas de permission ; le prompt imposé ne produit pas de `PermissionRequest` (le script en provoque un autre, refusé).
4. `permission_mode` vaut `"default"` sous `--permission-mode manual`.
5. Aucune `Notification` observée.
