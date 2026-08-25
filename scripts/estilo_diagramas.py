"""Estilo compartido de los diagramas de los informes (M1, M2, M3).

Fuente ÚNICA de la paleta para que los tres informes se lean como una serie.
Los hex son los de la **paleta categórica validada** del skill de dataviz (la
misma que usan los gráficos de datos de M3): así los diagramas de arquitectura
de M1/M2 dejan de usar su paleta vieja (estilo Tailwind) y comparten el lenguaje
visual con M3.

Convención:
  - Colores **saturados** (bordes / relleno fuerte): AZUL, VERDE, NARANJA,
    AMBAR, ROSA, VIOLETA, GRIS, ROJO.
  - `FILL[color]`: el tinte claro correspondiente para el fondo de la caja.
  - Los flowcharts de M1/M2 arman sus pares (fondo claro + borde) como
    `FILL[C], C`; los diagramas de capas de M3 usan el saturado directo con
    `FILL` como fondo.

Sobre rojo/verde: son **status colors** (error/éxito), reservados y legítimos en
un flowchart —viajan siempre con una etiqueta de texto ("FALLO", "OK", "no"),
así que la identidad nunca depende solo del color—.
"""

from __future__ import annotations

# Paleta categórica validada (orden = mecanismo de seguridad CVD; no reordenar).
AZUL = "#2a78d6"      # proceso / código propio / agente autónomo
NARANJA = "#eb6834"   # workflow-con-LLM (summarizer, judge) / acento cálido
VERDE = "#1baf7a"     # éxito / herramientas / workflow determinístico
AMBAR = "#eda100"     # decisión (rombos) / resultado
ROSA = "#e87ba4"      # categoría extra
VIOLETA = "#4a3aa7"   # loop-back / reintento
GRIS = "#9aa0a8"      # neutro / entorno / proveedor
ROJO = "#d64550"      # error (status, reservado) / código FIJO de cátedra
TINTA = "#1f2328"     # texto

# Tintes claros para el fondo de cada caja.
FILL = {
    AZUL: "#eaf2fc",
    NARANJA: "#fdece4",
    VERDE: "#e7f7f1",
    AMBAR: "#fdf3d6",
    ROSA: "#fbeaf1",
    VIOLETA: "#e9e6f5",
    GRIS: "#f1f2f4",
    ROJO: "#fbe9ea",
}
