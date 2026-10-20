"""Loading the data the dashboard and the session jumps both show."""

from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from meute.cli.context import CliContext, local_now
from meute.cli.session_refresh import refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.agents import AgentInfo
from meute.core.board_view import BoardData, SessionRow
from meute.core.clock import local_zone
from meute.core.db.claude_sessions import claude_details_by_session
from meute.core.db.projects import list_projects
from meute.core.db.repos import list_repos
from meute.core.db.samples import latest_metrics_by_session, latest_quota, quota_history
from meute.core.db.sessions import list_sessions
from meute.core.db.task_reads import latest_notes
from meute.core.db.tasks import TaskFilter, list_tasks
from meute.core.project import ProjectRef
from meute.core.quota_view import PROJECTION_WINDOW, QuotaLine, current_quota, projected_limit
from meute.core.session import SessionId
from meute.core.session_project import session_project
from meute.core.session_state import is_live
from meute.core.statusline_render import peak_text
from meute.core.views import bucket_of

RECENTLY_ENDED = timedelta(days=7)


def quota_line(ctx: CliContext, now: datetime, environ: Mapping[str, str]) -> QuotaLine:
    """Return the latest quota, its "limit around" projection and the peak hours (spec 7.4).

    Windows that have reset since the latest sample are left out.
    """
    sample = latest_quota(ctx.db)
    latest = None if sample is None else current_quota(sample, now=now)
    five_resets = None if latest is None else latest.five_hour_resets_at
    history = quota_history(ctx.db, since=now - PROJECTION_WINDOW)
    return QuotaLine(
        five_hour_pct=None if latest is None else latest.five_hour_pct,
        five_hour_resets_at=five_resets,
        seven_day_pct=None if latest is None else latest.seven_day_pct,
        seven_day_resets_at=None if latest is None else latest.seven_day_resets_at,
        limit_at=projected_limit(history, resets_at=five_resets, now=now),
        peak=peak_text(now, ctx.config.quotas, local_zone(environ)),
    )


def recently_ended(
    ctx: CliContext, shown: Collection[SessionId], now: datetime
) -> tuple[SessionRow, ...]:
    """Return the sessions ended within 7 days that `shown` lacks: they have no pane."""
    since = now - RECENTLY_ENDED
    return tuple(
        SessionRow(session=session, has_pane=False, displayed=False)
        for session in list_sessions(ctx.db, include_ended=True)
        if not is_live(session.state)
        and session.id not in shown
        and (session.ended_at or session.last_activity_at) >= since
    )


def load_board_data(
    ctx: CliContext,
    env: TmuxEnv,
    environ: Mapping[str, str],
    agents: Sequence[AgentInfo] | None,
    *,
    assume: bool = True,
) -> BoardData:
    """Reconcile the sessions with tmux, then gather everything the board shows.

    `agents` and `assume` are passed to `refresh`.

    Raises:
        TmuxError: tmux failed.
    """
    snapshot = refresh(ctx, env, agents=agents, assume=assume)
    db = ctx.db
    clock = db.now()
    local = local_now(ctx)
    live = [row.session.id for row in snapshot.sessions if is_live(row.session.state)]
    projects = list_projects(db)
    refs = tuple(ProjectRef(id=project.id, name=project.name) for project in projects)
    repos = list_repos(db)
    repo_by_id = {repo.id: repo for repo in repos}
    displayed = next((row.session for row in snapshot.sessions if row.displayed), None)
    return BoardData(
        sessions=snapshot.sessions,
        repos=tuple(repos),
        orphans=snapshot.orphans,
        home=Path.home(),
        outside=snapshot.outside,
        ended=recently_ended(ctx, {row.session.id for row in snapshot.sessions}, clock),
        details=claude_details_by_session(db),
        metrics=latest_metrics_by_session(db, live),
        projects={project.id: project.name for project in projects},
        quota=quota_line(ctx, clock, environ),
        now=local,
        tasks=tuple(
            task
            for task in list_tasks(db, TaskFilter(include_done=True))
            if bucket_of(task, local) is not None
        ),
        notes={task_id: tuple(found) for task_id, found in latest_notes(db).items()},
        project_refs=refs,
        displayed_project=None
        if displayed is None
        else session_project(displayed, projects=refs, repos=repo_by_id),
    )
