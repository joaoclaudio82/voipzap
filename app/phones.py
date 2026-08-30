"""Variações de um telefone brasileiro (com e sem o nono dígito).

O WhatsApp entrega o número de celular ora com o 9 inicial, ora sem — o
disparo da ligação usa 13 dígitos e o `remoteJid` pode chegar com 12. Sem
tratar isso, o bot não encontra o aviso que ele mesmo acabou de dar.
"""


def variants(phone: str) -> list[str]:
    digits = "".join(c for c in phone if c.isdigit())
    if not digits.startswith("55"):
        return [digits]

    resto = digits[2:]
    # DDD (2) + celular (9 dígitos, começando com 9) = 11
    if len(resto) == 11 and resto[2] == "9":
        return [digits, "55" + resto[:2] + resto[3:]]
    # DDD (2) + 8 dígitos; vira celular se o primeiro for 6-9
    if len(resto) == 10 and resto[2] in "6789":
        return [digits, "55" + resto[:2] + "9" + resto[2:]]
    return [digits]
