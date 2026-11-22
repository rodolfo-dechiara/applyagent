"""Crockford base32 IDs: a 120-bit value encoded as 24 base32 chars plus one
checksum character (25 total).

- Data alphabet: the 32 Crockford symbols "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
  (I, L, O, U excluded to avoid misreading).
- Checksum: value mod 37 mapped onto a 37-symbol alphabet — the 32 base
  symbols plus five URL-path-safe extras "*~$@+".

IDs are used in URLs instead of serial integer PKs, so they never leak
object counts. Model `uid` fields use new_id() as their default.
"""

import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CHECKSUM_ALPHABET = ALPHABET + "*~$@+"  # 37 symbols, all URL-path safe
DATA_CHARS = 24  # 24 * 5 bits = 120 bits
ID_LENGTH = DATA_CHARS + 1
BITS = DATA_CHARS * 5


def _encode(value: int) -> str:
    if not 0 <= value < (1 << BITS):
        raise ValueError(f"value out of range for {BITS} bits: {value}")
    chars = []
    for i in range(DATA_CHARS):
        shift = (DATA_CHARS - 1 - i) * 5
        chars.append(ALPHABET[(value >> shift) & 31])
    return "".join(chars)


def _checksum(value: int) -> str:
    return CHECKSUM_ALPHABET[value % 37]


def new_id() -> str:
    """A fresh random 25-char Crockford ID (24 data chars + checksum)."""
    value = secrets.randbits(BITS)
    return _encode(value) + _checksum(value)


def decode(data: str) -> int:
    """Decode the 24 data chars back to the integer. Raises ValueError."""
    if len(data) != DATA_CHARS:
        raise ValueError(f"expected {DATA_CHARS} data chars, got {len(data)}")
    value = 0
    for ch in data.upper():
        idx = ALPHABET.find(ch)
        if idx == -1:
            raise ValueError(f"invalid Crockford symbol: {ch!r}")
        value = value * 32 + idx
    return value


def is_valid(identifier: str) -> bool:
    """True when identifier is 25 chars: 24 valid data chars + matching checksum."""
    if len(identifier) != ID_LENGTH:
        return False
    try:
        value = decode(identifier[:DATA_CHARS])
    except ValueError:
        return False
    check = identifier[DATA_CHARS].upper()
    if check not in CHECKSUM_ALPHABET:
        return False
    return CHECKSUM_ALPHABET.index(check) == value % 37
