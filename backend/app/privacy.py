import re


def mask_sensitive(raw: str) -> tuple[str, list[str]]:
    """Removes secrets from customer text before it is stored, shown to an agent or sent to an AI provider."""
    text = raw
    masked: list[str] = []
    rules = [
        (r"(mot de passe|password)(\s*(?:est|:|=)?\s*)\S+", r"\1\2[masqué]", "mot de passe", re.I),
        (r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){10,30}\b", "[IBAN masqué]", "IBAN", re.I),
        (r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", "[numéro de carte masqué] ", "numéro de carte", 0),
        (r"\b(code|pin|cvv|cvc|cryptogramme)\b([^\d\n]{0,20})\d{3,6}\b", r"\1\2[code masqué]", "code secret", re.I),
    ]
    for pattern, replacement, label, flags in rules:
        text, count = re.subn(pattern, replacement, text, flags=flags)
        if count:
            masked.append(label)
    return text.strip(), masked
