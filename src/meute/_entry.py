import sys
from collections.abc import Sequence
from typing import NoReturn


def main(argv: Sequence[str] | None = None) -> int:
    # Imports stay inside the function: the ingest path must never load the CLI.
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "ingest":
        from meute import ingest  # noqa: PLC0415 — keeps the ingest start-up fast

        return ingest.run(args[1:])
    from meute import cli  # noqa: PLC0415 — typer is only needed off the ingest path

    return cli.run(args)


def console() -> NoReturn:
    sys.exit(main())
