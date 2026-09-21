"""Run with jobagent setup or python -m jobagent setup from a checkout."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="JobAgent: your local job-search assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup", help="Open the guided, resumable terminal setup")
    setup.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    from jobagent.setup_tui import SetupApp
    SetupApp(args.workspace.resolve()).run()


if __name__ == "__main__":
    main()
