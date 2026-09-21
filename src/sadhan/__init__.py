import sys


def main() -> None:
    from . import config

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        try:
            config.cwd = config.resolve_workdir(args[0])
        except ValueError as e:
            print(f"sadhan: error: {e}", file=sys.stderr)
            sys.exit(1)

    from .main import main as cli_main

    cli_main()
