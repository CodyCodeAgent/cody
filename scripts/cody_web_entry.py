"""PyInstaller entry point for cody-web (API-only, no frontend)."""
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(prog="cody-web")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="start backend API server")
    run_parser.add_argument("--host", default="0.0.0.0")
    run_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    if args.command == "run":
        from web.backend.app import app
        import uvicorn
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
