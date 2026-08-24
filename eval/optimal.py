"""Cálculo del óptimo de tool-calls por escenario, vía búsqueda.

En lugar de hardcodear el óptimo del enunciado, lo **derivamos** con una
BFS sobre el grafo de estados del mundo: cada arista es una tool-call
(`examine`/`take`/`use`/`go`) y buscamos el camino más corto desde el
estado inicial hasta uno que cumpla `check_goal`. El largo de ese camino
es el óptimo (mínimo número de acciones que resuelven el escenario).

Por qué BFS y no confiar en la tabla:
  - Es una métrica **derivada del mundo**, no un número copiado a mano.
  - Cross-valida el enunciado: si coincide, ambos quedan verificados.

Detalles:
  - `look` no muta el estado, así que nunca forma parte de un óptimo: no
    lo expandimos (y el enunciado tampoco lo cuenta).
  - Aplicamos las tools REALES (`make_world_tools`) sobre copias del mundo;
    no reimplementamos las mecánicas.
  - Deduplicamos por un estado canónico. El `event_log` solo entra en la
    clave cuando el goal usa `sequence` (ahí el orden importa); si no, lo
    excluimos para que la BFS colapse estados físicamente iguales.
  - El resultado se cachea en `eval/optimal_cache.json` (clave: id +
    hash del archivo del escenario) para no recomputar en cada corrida.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import deque
from pathlib import Path
from typing import Any

from mia_world.goals import check_goal
from mia_world.scenarios import load_scenario
from mia_world.state import Scenario, World
from mia_world.tools import make_world_tools


_CACHE_PATH = Path(__file__).resolve().parent / "optimal_cache.json"


def _goal_uses_sequence(goal: dict[str, Any]) -> bool:
    """True si el goal (recursivo) contiene algún combinador `sequence`."""
    if goal.get("type") == "sequence":
        return True
    return any(_goal_uses_sequence(g) for g in goal.get("goals", []))


def _canonical(world: World, with_events: bool) -> tuple:
    """Clave hashable del estado relevante para transiciones y goal."""
    items_key = tuple(
        sorted(
            (
                item.id,
                item.open_state,
                tuple(sorted(item.inserted)),
                tuple(item.contains),
            )
            for item in world.items.values()
        )
    )
    key: tuple = (
        world.current_room,
        tuple(sorted(world.inventory)),
        tuple(sorted(world.revealed)),
        items_key,
    )
    if with_events:
        key = key + (tuple(world.event_log),)
    return key


def _candidate_actions(world: World) -> list[tuple[str, dict[str, str]]]:
    """Acciones que podrían mutar el estado (excluye `look`).

    Las no-ops (examinar algo no visible, usar algo que no está en el
    inventario, etc.) devuelven el mismo estado y la BFS las descarta por
    deduplicación; enumerarlas de más no afecta la corrección.
    """
    item_ids = list(world.items)
    acciones: list[tuple[str, dict[str, str]]] = []

    for tid in item_ids:
        acciones.append(("examine", {"target": tid}))
        acciones.append(("take", {"item": tid}))

    for inv_item in world.inventory:
        for tid in item_ids:
            acciones.append(("use", {"item": inv_item, "target": tid}))

    room = world.rooms[world.current_room]
    for direction in set(room.exits) | set(room.locked_exits):
        acciones.append(("go", {"direction": direction}))

    return acciones


def compute_optimal(
    scenario: Scenario,
    max_depth: int = 40,
    node_cap: int = 400_000,
) -> int | None:
    """Óptimo de tool-calls por BFS. `None` si no se halla dentro de las cotas.

    `max_depth` acota la profundidad (los óptimos conocidos ≤ 21) y
    `node_cap` la cantidad de estados explorados, como red de seguridad
    ante un blow-up.
    """
    goal = scenario.goal
    with_events = _goal_uses_sequence(goal)

    start = copy.deepcopy(scenario.initial_world)
    if check_goal(start, goal)[0]:
        return 0

    seen: set[tuple] = {_canonical(start, with_events)}
    frontier: deque[tuple[World, int]] = deque([(start, 0)])

    while frontier:
        world, depth = frontier.popleft()
        if depth >= max_depth:
            continue

        for name, kwargs in _candidate_actions(world):
            nxt = copy.deepcopy(world)
            tools = {schema.name: fn for fn, schema in make_world_tools(nxt)}
            fn = tools.get(name)
            if fn is None:
                continue
            try:
                fn(**kwargs)
            except Exception:  # noqa: BLE001 — una acción inválida no aporta
                continue

            key = _canonical(nxt, with_events)
            if key in seen:
                continue

            if check_goal(nxt, goal)[0]:
                return depth + 1

            seen.add(key)
            frontier.append((nxt, depth + 1))

            if len(seen) > node_cap:
                return None

    return None


def _file_hash(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def _load_cache() -> dict[str, Any]:
    if _CACHE_PATH.exists():
        try:
            return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — cache corrupta: la ignoramos
            return {}
    return {}


def optimal_for_path(scenario_path: Path, use_cache: bool = True) -> int | None:
    """Óptimo de un escenario por path, con cache por (id, hash de archivo)."""
    scenario = load_scenario(scenario_path)
    fhash = _file_hash(scenario_path)
    cache_key = f"{scenario.id}:{fhash}"

    cache = _load_cache() if use_cache else {}
    if use_cache and cache_key in cache:
        return cache[cache_key]

    value = compute_optimal(scenario)

    if use_cache:
        cache[cache_key] = value
        _CACHE_PATH.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return value
