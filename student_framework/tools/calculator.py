from __future__ import annotations
from typing import Annotated
from pydantic import Field
from mia_agents.types import ToolSchema
import ast
import operator

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}



def Calculator(
    text: Annotated[str, Field(description="Expresion a resolver")],
) -> str:
    """Utiliza esta funcion solo cuando se necesiten resolver problemas matematicos. \
    Esta funcion recibe un string que representa una operacion amtematica conteniendo solo contiene \
    únicamente números, paréntesis y los operadores +, -, * y / (division), y devuelve el resultado de la misma"""
    def evaluate(node):
            if isinstance(node, ast.Expression):
                return evaluate(node.body)

            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("Solo se permiten números.")

            if isinstance(node, ast.BinOp):
                if type(node.op) not in _OPERATORS:
                    raise ValueError("Operador no permitido.")
                return _OPERATORS[type(node.op)](
                    evaluate(node.left),
                    evaluate(node.right),
                )

            if isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    return -evaluate(node.operand)
                if isinstance(node.op, ast.UAdd):
                    return evaluate(node.operand)

            raise ValueError("Expresión inválida.")

    try:
        result = evaluate(ast.parse(text, mode="eval"))
        return str(result)
    except ZeroDivisionError:
        return "Error: división por cero."
    except Exception as e:
        return f"Error: {e}"


calcualtor_schema = ToolSchema.from_callable(Calculator)
