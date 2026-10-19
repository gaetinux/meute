# Conception — vue Tâches et saisie rapide globale (plan 4b)

- Spécification fonctionnelle : `docs/superpowers/specs/2026-10-15-meute-design.md`, § 9.5 et § 9.6 (précisions de l'auteur du 2026-10-19), § 5.6 (ligne d'état).
- Le plan 4b est rédigé après le merge de la PR #10 (plan 4) ; ce document fixe la conception validée avec l'auteur le 2026-10-19.

## Intention

L'usage principal est de noter vite une idée ou un rappel pendant que Claude travaille, sans quitter ce que l'on regarde, et de voir d'un coup d'œil ce qui est en retard. Le pilotage (lancer Claude sur une tâche, suivre ses sessions liées) vient ensuite. Hors périmètre, au plan 4c : formulaire `N`, « dernier type utilisé » de `n`, actions sur les panneaux orphelins.

## Passe visuelle du tableau

Décision de l'auteur, 2026-10-19 : le tableau est jugé fonctionnel mais peu agréable à l'œil. Le plan 4b commence par une passe visuelle, conçue avec des maquettes et validée par l'auteur avant tout code, pour les deux onglets : en-tête et onglets, titres de groupe distincts des lignes, colonnes alignées, état en couleur, infos secondaires atténuées, palette cohérente avec les repères de focus de la PR #10.

## Décisions de l'auteur

| Question | Décision |
|---|---|
| Où saisir une tâche | De partout par `M-t` (fenêtre `display-popup`) et par `a` dans l'onglet Tâches |
| Cohabitation des vues | Deux onglets dans le tableau ; le nombre de tâches en retard reste visible (titre et ligne d'état) |
| Tâche sans `@projet` dans `M-t` | Rattachée au projet de la session affichée ; `@none` force une tâche volante |
| Édition dans le détail | Une touche par action, ligne de saisie en bas pour le texte |
| Ce que reçoit Claude avec `L` | Le texte de la tâche collé dans sa saisie, sans être envoyé |
| Fenêtre `M-t` | Mini-application Textual dans `tmux display-popup` |

## Architecture

**Cœur (`meute.core`, stdlib seule, fonctions pures)** :
- `tasks_view.py` : le modèle de l'onglet (lignes, en-têtes, compteurs, sélection) à partir des tâches, de l'heure, du filtre, du regroupement, des groupes repliés et du projet affiché ; réutilise `views.py` (groupes d'urgence, tri, format des échéances) et `parse_quick_add`.
- `task_postpone.py` : les reports rapides (+1 h, tonight 6 pm, tomorrow 9 am, Monday 9 am, clear) à partir d'une heure donnée.
- `task_prompt.py` : le texte collé dans Claude (`#12 Titre`, description, notes).
- la ligne d'état gagne le compte des tâches en retard.

**TUI (`meute.tui`)** : `tasks_pane.py` (rendu, sur le modèle de `sessions_pane.py`), `tasks_cursor.py` (navigation, sur le modèle de `sessions_cursor.py`), `task_input.py` (ligne de saisie et courte liste de choix, partagées), `quick_task.py` (mini-application de `M-t`). `board.py` n'ajoute que les onglets et l'aiguillage des touches et reste sous 300 lignes.

**CLI (`meute.cli`)** :
- le protocole `BoardBackend` gagne les actions sur les tâches (créer, modifier, statut, note, supprimer, lancer), qui passent par les fonctions existantes de `meute.core.db` avec la `version` attendue (§ 9.2) ;
- `meute task quick` (commande cachée) lance la mini-application ; la configuration tmux générée lie `[keys] quick_task` (défaut `M-t`, validé comme les autres touches) à `display-popup -E` sur cette commande ;
- « launch Claude on this task » réutilise le lancement existant avec la tâche ; dès que le hook `SessionStart` est reçu, meute colle le texte par `tmux load-buffer` puis `paste-buffer -p` (bracketed paste, pour que les retours à la ligne n'envoient pas le message), sans `Entrée`. Au-delà de 10 s sans Claude prêt : « prompt not pasted ».

**Données** : aucune migration prévue (tâches, notes, événements et `sessions.task_id` existent).

## Spikes au début du plan

- **S8** : collage en bracketed paste dans le vrai Claude, texte multiligne non envoyé (essai avec le vrai `claude`, sur accord explicite de l'auteur).
- **S9** : temps réel d'ouverture de `M-t`, du raccourci au champ utilisable. Mesure indicative au 2026-10-19 : `import textual.app, textual.widgets` 132 ms, `import meute.tui.board` 155 ms (hyperfine, 20 exécutions). Si l'ouverture est nettement trop lente, repli sur une saisie dans le tableau lui-même (`M-t` donne le focus au tableau, onglet Tâches, champ ouvert).

## Erreurs

- Conflit de version : « modified in the meantime », la tâche est rechargée, la saisie en cours est gardée.
- Jeton de saisie rapide non reconnu : il reste dans le titre (§ 9.3), l'aperçu le montre.
- Base verrouillée ou indisponible : erreur dans le pied de page ; la fenêtre `M-t` reste ouverte avec le texte.
- Projet inconnu : signalé dans l'aperçu, création bloquée (la création automatique des projets est au plan 6).
- `L` sans dépôt ni projet : message, rien n'est lancé.
- Suppression : confirmation `y` / `n`, historique conservé.

## Tests

- Cœur : tests unitaires et `hypothesis` (sélection jamais sur un en-tête, reports autour de minuit et du lundi, filtre « this project » sans session affichée).
- TUI : snapshots `pytest-textual-snapshot` de l'onglet à 60 et 100 colonnes et de la fenêtre `M-t` ; tests de touches avec le pilote Textual.
- CLI : `meute task quick` sur un serveur tmux jetable ; « launch on task » avec le faux `claude`, qui vérifie que le collage arrive sans `Entrée`.
- Points de vigilance : échéances très lointaines ou dépassées de plusieurs mois ; titres très longs ou contenant des caractères de contrôle ; 500 tâches ou plus ; `M-t` en mode étroit ; `M-t` pressé deux fois.
- Fin de plan : `mutmut`, `/simplify`, `/security-review` (sous-processus, collage tmux, SQL).
