import secrets

BARCODE_ATTEMPTS = 5
_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_barcode(prefix: str) -> str:
    suffix = "".join(secrets.choice(_CROCKFORD_ALPHABET) for _ in range(8))
    return prefix + suffix
