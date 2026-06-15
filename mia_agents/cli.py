"""Runner estandarizado por línea de comandos.

Uso:
    python -m mia_agents.cli run --module student_framework --message "¿Cuánto es 17 * 23?"

Importa `<module>.build_agent`, ejecuta el agente con el mensaje indicado e
imprime el `AgentResult` en formato JSON.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict

from mia_agents.types import AgentResult


def _run(module_name: str, message: str) -> AgentResult:
    module = importlib.import_module(module_name)
    if not hasattr(module, "build_agent"):
        raise SystemExit(
            f"El módulo {module_name!r} no exporta `build_agent`. "
            "Toda entrega debe exponer `build_agent(config) -> Agent`."
        )
    agent = module.build_agent()
    return agent.run(message)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mia_agents")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Ejecuta un agente con un único mensaje.")
    run.add_argument(
        "--module",
        default="student_framework",
        help="Módulo Python que expone `build_agent` (por defecto: student_framework).",
    )
    run.add_argument("--message", required=True, help="Mensaje del usuario a enviar.")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        result = _run(args.module, args.message)
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
