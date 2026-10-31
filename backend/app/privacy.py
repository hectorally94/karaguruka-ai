import re
import unicodedata

SECRET_WORD = r"(?:code(?:\s+secret|\s+pin)?|pin|cvv|cvc|cryptogramme)"
# Digits may be spaced out ("1 2 3 4") to get past a simple pattern.
SECRET_DIGITS = r"(?<!\d)\d(?:[\W_]{0,2}\d){2,5}(?!\d)"


def mask_sensitive(raw: str) -> tuple[str, list[str]]:
    """Removes secrets from customer text before it is stored, shown to an agent or sent to an AI provider."""
    # NFKC turns look-alike digits and unusual spaces into their plain forms, so the patterns below see them.
    text = unicodedata.normalize("NFKC", raw)
    masked: list[str] = []
    rules = [
        # Everything after the keyword is hidden, through the next line: a password can contain spaces or follow a line break.
        (r"(?<![^\W\d_])(mot de passe|mdp|password|passphrase|passcode)[^\n]*(?:\n[^\n]*)?", r"\1 [masqué]", "mot de passe", re.I),
        (r"\b[A-Z]{2}\d{2}(?:[\W_]{0,2}[A-Z0-9]){10,30}\b", "[IBAN masqué]", "IBAN", re.I),
        (r"(?<!\d)(?:\d[\W_]{0,3}){12,18}\d(?!\d)", "[numéro de carte masqué]", "numéro de carte", 0),
        (rf"\b({SECRET_WORD})\b([^\d\n]{{0,20}}){SECRET_DIGITS}", r"\1\2[code masqué]", "code secret", re.I),
        (rf"{SECRET_DIGITS}(\s*(?:est|c.est|comme|:)?\s*(?:mon|ma|le|mes)?\s*{SECRET_WORD}\b)", r"[code masqué]\1", "code secret", re.I),
    ]
    for pattern, replacement, label, flags in rules:
        text, count = re.subn(pattern, replacement, text, flags=flags)
        if count and label not in masked:
            masked.append(label)
    return text.strip(), masked
