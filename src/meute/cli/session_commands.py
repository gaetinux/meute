"""The `meute session` commands."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer

from meute.claude.agents import run_agents
from meute.claude.launch import find_claude
from meute.cli.confirm import confirmed
from meute.cli.context import open_context
from meute.cli.folder_repo import main_repo_or_fail, repo_id_of_folder
from meute.cli.json_out import echo_json
from meute.cli.session_jump import jump_to_attention
from meute.cli.session_launch_claude import start_session
from meute.cli.session_refresh import refresh
from meute.cli.session_show import show_session
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import open_tmux_env
from meute.cli.worktree_launch import launch_in_new_worktree
from meute.core.agents import AgentInfo, parse_agents
from meute.core.claude_session import ClaudeDetails, claude_details_to_json
from meute.core.db.claude_sessions import claude_details_by_session
from meute.core.db.sessions import find_session
from meute.core.errors import InvalidInput
from meute.core.json_types import JsonObject
from meute.core.paths import display_path
from meute.core.session import AgentKind, Session, SessionId, session_to_json, short_id
from meute.core.session_state import state_label
from meute.core.text import printable

session_app = typer.Typer(no_args_is_help=True, help="Sessions running in tmux.")


@session_app.command("new")
def new(
    cwd: Annotated[
        Path | None, typer.Option("--cwd", help="Folder to start in (default: here).")
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Session title.")] = None,
    kind: Annotated[AgentKind, typer.Option("--kind", help="What to run.")] = AgentKind.CLAUDE,
    permission_mode: Annotated[
        str | None,
        typer.Option("--permission-mode", help="Claude permission mode (Claude sessions only)."),
    ] = None,
    worktree: Annotated[
        str | None,
        typer.Option("--worktree", help="Start in a new worktree on this new branch."),
    ] = None,
) -> None:
    """Start a session in the background."""
    if kind is AgentKind.BASH and permission_mode is not None:
        message = "--permission-mode only applies to Claude sessions"
        raise InvalidInput(message)
    folder = cwd or Path.cwd()
    with open_context(os.environ) as ctx:
        env = open_tmux_env(ctx, os.environ)

        def launch(folder: Path) -> Session:
            repo_id = repo_id_of_folder(ctx, folder)
            return start_session(
                ctx,
                env,
                os.environ,
                kind=kind,
                cwd=folder,
                repo_id=repo_id,
                title=title,
                permission_mode=permission_mode,
            )

        if worktree is None:
            session = launch(folder)
        else:
            repo = main_repo_or_fail(folder)
            session = launch_in_new_worktree(os.environ, repo, worktree, launch)
    typer.echo(
        f"Launched: {short_id(session.id)} {printable(session.title)} "
        f"({printable(display_path(session.cwd, Path.home()))})"
    )


def _session_json(session: Session, details: Mapping[SessionId, ClaudeDetails]) -> JsonObject:
    found = details.get(session.id)
    base = session_to_json(session)
    return base if found is None else {**base, "claude": claude_details_to_json(found)}


def _outside_json(agent: AgentInfo) -> JsonObject:
    return {
        "pid": agent.pid,
        "cwd": agent.cwd,
        "kind": agent.kind,
        "session_id": agent.session_id,
        "name": agent.name,
        "status": agent.status,
    }


def _read_agents() -> tuple[AgentInfo, ...] | None:
    """Ask `claude agents --json`; `None` when claude is absent or the command failed."""
    claude = find_claude(os.environ)
    text = None if claude is None else run_agents(claude)
    return None if text is None else parse_agents(text)


@session_app.command("list")
def list_(
    *,
    all_: Annotated[
        bool, typer.Option("--all", help="Also list ended sessions without a pane.")
    ] = False,
    json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False,
) -> None:
    """List the sessions after reconciling them with tmux."""
    with open_context(os.environ) as ctx:
        snapshot = refresh(
            ctx, open_tmux_env(ctx, os.environ), include_ended=all_, agents=_read_agents()
        )
        details = claude_details_by_session(ctx.db)
    if json_:
        payload: JsonObject = {
            "sessions": [_session_json(row.session, details) for row in snapshot.sessions],
            "orphans": list(snapshot.orphans),
        }
        if snapshot.outside:  # absent when empty: the shape pinned by test_list_json_shape
            payload["outside"] = [_outside_json(agent) for agent in snapshot.outside]
        echo_json(payload)
        return
    home = Path.home()
    for row in snapshot.sessions:
        session = row.session
        mode = details[session.id].permission_mode if session.id in details else None
        typer.echo(
            f"{short_id(session.id)}  {printable(session.title)}  {state_label(session.state)}"
            f"  {printable(display_path(session.cwd, home))}"
            + ("" if mode is None else f"  [{printable(mode)}]")
        )
    for orphan in snapshot.orphans:
        typer.echo(f"orphan: {printable(orphan)}")
    for agent in snapshot.outside:
        typer.echo(
            f"outside: {printable(agent.status)}  {printable(agent.name)}"
            f"  {printable(display_path(Path(agent.cwd), home))}"
        )


@session_app.command("show")
def show(session_id: Annotated[str, typer.Argument(help="Session id or prefix.")]) -> None:
    """Show a session in the main area."""
    with open_context(os.environ) as ctx:
        session = find_session(ctx.db, session_id)
        show_session(ctx, open_tmux_env(ctx, os.environ), session.id)


@session_app.command("next", hidden=True)
def next_() -> None:
    """Show the next session that needs attention (bound to M-n)."""
    with open_context(os.environ) as ctx:
        _ = jump_to_attention(ctx, open_tmux_env(ctx, os.environ), os.environ, backwards=False)


@session_app.command("previous", hidden=True)
def previous() -> None:
    """Show the previous session that needs attention (bound to M-N)."""
    with open_context(os.environ) as ctx:
        _ = jump_to_attention(ctx, open_tmux_env(ctx, os.environ), os.environ, backwards=True)


@session_app.command("stop")
def stop(
    session_id: Annotated[str, typer.Argument(help="Session id or prefix.")],
    *,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Stop a session: Ctrl-C, then kill it if it does not exit."""
    with open_context(os.environ) as ctx:
        session = find_session(ctx.db, session_id)
        if not yes and not confirmed(f'Stop session "{printable(session.title)}"? [y/N] '):
            typer.echo("Cancelled.")
            return
        stopped = stop_session(ctx, open_tmux_env(ctx, os.environ), session.id, environ=os.environ)
    typer.echo(f"Stopped: {short_id(stopped.id)} {printable(stopped.title)}")
