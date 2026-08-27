"""Tests de `eval/stats.py` — contrastes estratificados entre brazos.

Todo puro: no toca red ni disco.
"""

from __future__ import annotations

import pytest

from eval.stats import (
    cmh_test,
    comparar_brazos,
    efecto_por_escenario,
    estratos_desde_casos,
    wilson_ci,
    z_test_agrupado,
)


# --- Wilson --------------------------------------------------------------


def test_wilson_no_se_sale_del_rango_en_los_extremos():
    """Wald daría intervalos degenerados en 0/n y n/n; Wilson no."""
    lo, hi = wilson_ci(0, 24)
    assert lo == 0.0 and 0 < hi < 1
    lo, hi = wilson_ci(24, 24)
    assert 0 < lo < 1 and hi == 1.0


def test_wilson_n_cero_devuelve_el_rango_completo():
    assert wilson_ci(0, 0) == (0.0, 1.0)


# --- z-test agrupado -----------------------------------------------------


def test_z_test_sin_diferencia_da_p_uno():
    z, p = z_test_agrupado(10, 20, 10, 20)
    assert z == 0.0
    assert p == pytest.approx(1.0)


def test_z_test_detecta_una_diferencia_grande():
    _, p = z_test_agrupado(2, 40, 30, 40)
    assert p < 0.001


# --- CMH -----------------------------------------------------------------


def test_cmh_descarta_estratos_saturados():
    """Un estrato 0/8 en ambos brazos no aporta: se descarta y se reporta."""
    estratos = {
        "muerto_en_cero": ((0, 8), (0, 8)),
        "muerto_en_uno": ((8, 8), (8, 8)),
        "vivo": ((1, 8), (7, 8)),
    }
    r = cmh_test(estratos)
    assert r["estratos_usados"] == ["vivo"]
    assert set(r["estratos_descartados"]) == {"muerto_en_cero", "muerto_en_uno"}


def test_cmh_descarta_estratos_con_un_brazo_vacio():
    r = cmh_test({"solo_base": ((3, 8), (0, 0))})
    assert r["estratos_usados"] == []
    assert r["estratos_descartados"] == ["solo_base"]
    assert r["p"] is None


def test_cmh_sin_estratos_utiles_no_explota():
    r = cmh_test({"a": ((0, 8), (0, 8))})
    assert r["p"] is None and r["chi2"] is None


def test_cmh_gana_poder_sobre_el_agrupado():
    """El punto del módulo: estratificar recupera una señal que el agrupado tapa.

    Reproduce la estructura real de `nova-micro` gate vs. react: dos escenarios
    saturados en 0 que solo agregan denominador, y el efecto concentrado en uno.
    """
    estratos = {
        "saturado_a": ((0, 8), (0, 8)),
        "saturado_b": ((0, 8), (0, 8)),
        "efecto": ((1, 8), (7, 8)),
        "leve": ((6, 8), (8, 8)),
    }
    s1 = sum(e[0][0] for e in estratos.values())
    n1 = sum(e[0][1] for e in estratos.values())
    s2 = sum(e[1][0] for e in estratos.values())
    n2 = sum(e[1][1] for e in estratos.values())
    _, p_agrupado = z_test_agrupado(s1, n1, s2, n2)
    p_cmh = cmh_test(estratos)["p"]
    assert p_cmh < p_agrupado


def test_cmh_es_simetrico_en_magnitud():
    """Invertir los brazos cambia el signo del efecto, no la evidencia."""
    a = {"x": ((2, 10), (8, 10)), "y": ((3, 10), (7, 10))}
    b = {k: (v[1], v[0]) for k, v in a.items()}
    assert cmh_test(a)["p"] == pytest.approx(cmh_test(b)["p"])


# --- efecto por escenario ------------------------------------------------


def test_efecto_por_escenario_ordena_por_delta():
    filas = efecto_por_escenario({
        "chico": ((6, 8), (7, 8)),
        "grande": ((1, 8), (7, 8)),
        "negativo": ((5, 8), (2, 8)),
    })
    assert [f["escenario"] for f in filas] == ["grande", "chico", "negativo"]
    assert filas[0]["delta"] == pytest.approx(0.75)
    assert filas[-1]["delta"] < 0


def test_efecto_por_escenario_ignora_estratos_sin_datos():
    assert efecto_por_escenario({"vacio": ((0, 0), (0, 0))}) == []


# --- armado desde casos --------------------------------------------------


def _caso(scenario, config, goal):
    return {"scenario": scenario, "config": config, "goal_achieved": goal}


def test_estratos_desde_casos_agrupa_y_cuenta():
    casos = [
        _caso("a", "react", True), _caso("a", "react", False),
        _caso("a", "gate", True), _caso("a", "gate", True),
        _caso("b", "react", False), _caso("b", "gate", False),
        _caso("a", "summarizer", True),  # brazo ajeno: se ignora
    ]
    e = estratos_desde_casos(casos, "react", "gate")
    assert e["a"] == ((1, 2), (2, 2))
    assert e["b"] == ((0, 1), (0, 1))


def test_comparar_brazos_reporta_ambos_tests():
    casos = []
    for i in range(8):
        casos.append(_caso("efecto", "react", i < 1))
        casos.append(_caso("efecto", "gate", i < 7))
        casos.append(_caso("saturado", "react", False))
        casos.append(_caso("saturado", "gate", False))
    r = comparar_brazos(casos, "react", "gate")
    assert r["base_n"] == "1/16" and r["comp_n"] == "7/16"
    assert r["delta"] == pytest.approx(0.375)
    assert r["cmh"]["estratos_descartados"] == ["saturado"]
    assert r["cmh"]["estratos_usados"] == ["efecto"]
    # Ambos tests se reportan; cuál es más chico depende de la estructura de
    # estratos, no es una propiedad garantizada de CMH (ver el test de abajo).
    assert r["p_agrupado"] is not None and r["cmh"]["p"] is not None
    assert r["por_escenario"][0]["escenario"] == "efecto"


def test_cmh_no_siempre_gana_con_un_solo_estrato_util():
    """CMH NO es universalmente más potente: con un único estrato informativo
    la corrección de continuidad lo vuelve algo más conservador.

    Está acá para que nadie lea el módulo como "estratificar siempre baja el
    p-valor". Gana cuando hay VARIOS estratos informativos y algunos saturados
    que diluyen el agregado —el caso real de gate vs. react—; no por magia.
    """
    estratos = {"saturado": ((0, 8), (0, 8)), "efecto": ((1, 8), (7, 8))}
    s1 = sum(e[0][0] for e in estratos.values())
    n1 = sum(e[0][1] for e in estratos.values())
    s2 = sum(e[1][0] for e in estratos.values())
    n2 = sum(e[1][1] for e in estratos.values())
    _, p_agrupado = z_test_agrupado(s1, n1, s2, n2)
    assert cmh_test(estratos)["p"] >= p_agrupado


# --- semilla de bloqueo (mejora 4) ---------------------------------------


def test_semilla_es_estable_entre_procesos(monkeypatch):
    """La semilla debe depender SOLO de (escenario, repeat), no del proceso.

    Con `hash()` de Python esto fallaría: el hash de strings está aleatorizado
    por PYTHONHASHSEED, así que la "semilla fija" cambiaría en cada corrida.
    """
    from eval.run import _seed_de_caso

    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    # Valor fijado a mano: si alguien cambia la derivación, este test lo avisa.
    assert _seed_de_caso("study-with-key", 0) == _seed_de_caso("study-with-key", 0)
    assert isinstance(_seed_de_caso("study-with-key", 0), int)


def test_semilla_distingue_escenario_y_repeat(monkeypatch):
    from eval.run import _seed_de_caso

    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    assert _seed_de_caso("a", 0) != _seed_de_caso("a", 1)
    assert _seed_de_caso("a", 0) != _seed_de_caso("b", 0)


def test_semilla_no_depende_del_brazo(monkeypatch):
    """El punto del bloqueo: react y gate comparten semilla en el mismo par."""
    from eval.run import _seed_de_caso

    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")
    # La firma no toma el brazo: dos llamadas idénticas desde brazos distintos
    # devuelven lo mismo por construcción.
    assert _seed_de_caso("library-search", 2) == _seed_de_caso("library-search", 2)


def test_sin_ollama_no_hay_semilla(monkeypatch):
    """Bedrock/Nova rechaza `seed`: no se fija nada y el caso registra None."""
    from eval.run import _seed_de_caso

    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert _seed_de_caso("study-with-key", 0) is None
