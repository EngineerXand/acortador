"""Codificación Base62: convierte un número entero en un código corto.

Usamos 62 símbolos (0-9, a-z, A-Z). Con 7 caracteres caben
62^7 ≈ 3.5 billones de enlaces distintos.
"""

ALFABETO = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALFABETO)


def codificar(numero: int) -> str:
    """Convierte un entero no negativo a texto Base62. Ej: 125 -> '21'."""
    if numero < 0:
        raise ValueError("El número debe ser no negativo")
    if numero == 0:
        return ALFABETO[0]
    codigo = []
    while numero > 0:
        numero, resto = divmod(numero, BASE)
        codigo.append(ALFABETO[resto])
    return "".join(reversed(codigo))


def decodificar(codigo: str) -> int:
    """Operación inversa: convierte texto Base62 a entero. Ej: '21' -> 125."""
    numero = 0
    for caracter in codigo:
        numero = numero * BASE + ALFABETO.index(caracter)
    return numero
