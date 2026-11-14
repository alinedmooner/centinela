"""Comando de terminal de Centinela."""

import argparse

from centinela import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="centinela",
        description="Guardia para asistentes de IA que leen mensajes en español.",
    )
    parser.add_argument("--version", action="version", version=f"centinela {__version__}")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
