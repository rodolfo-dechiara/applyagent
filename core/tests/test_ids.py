"""Crockford base32 IDs (120 bits = 24 chars + 1 checksum). Red-first."""

from django.test import SimpleTestCase

from core.ids import (
    ALPHABET,
    CHECKSUM_ALPHABET,
    DATA_CHARS,
    ID_LENGTH,
    decode,
    is_valid,
    new_id,
)


class CrockfordIdTests(SimpleTestCase):
    def test_new_id_is_25_chars_with_24_data_chars(self) -> None:
        identifier = new_id()
        self.assertEqual(len(identifier), ID_LENGTH)
        self.assertEqual(len(identifier[:DATA_CHARS]), 24)

    def test_data_chars_use_crockford_alphabet_only(self) -> None:
        for _ in range(200):
            identifier = new_id()
            for ch in identifier[:DATA_CHARS]:
                self.assertIn(ch, ALPHABET)
            self.assertNotIn("I", identifier[:DATA_CHARS])
            self.assertNotIn("L", identifier[:DATA_CHARS])
            self.assertNotIn("O", identifier[:DATA_CHARS])
            self.assertNotIn("U", identifier[:DATA_CHARS])

    def test_checksum_char_is_from_37_symbol_alphabet(self) -> None:
        self.assertEqual(len(CHECKSUM_ALPHABET), 37)
        for _ in range(200):
            self.assertIn(new_id()[DATA_CHARS], CHECKSUM_ALPHABET)

    def test_roundtrip(self) -> None:
        for value in (0, 1, 31, 32, 2**119, 2**120 - 1, 123456789012345678901234567890):
            from core.ids import _checksum, _encode

            identifier = _encode(value) + _checksum(value)
            self.assertTrue(is_valid(identifier))
            self.assertEqual(decode(identifier[:DATA_CHARS]), value)

    def test_ids_are_unique_and_url_safe(self) -> None:
        ids = {new_id() for _ in range(2000)}
        self.assertEqual(len(ids), 2000)
        for identifier in ids:
            self.assertTrue(is_valid(identifier))
            self.assertRegex(identifier, r"^[0-9A-HJKMNP-TV-Z*~$@+]{25}$")

    def test_invalid_ids_rejected(self) -> None:
        self.assertFalse(is_valid(""))
        self.assertFalse(is_valid("A" * 24))  # missing checksum
        self.assertFalse(is_valid("A" * 25))  # bad checksum
        self.assertFalse(is_valid("I" * 24 + "0"))  # I is not in the alphabet
        self.assertFalse(is_valid("0" * 24 + "!"))  # bad checksum symbol
        good = new_id()
        self.assertFalse(is_valid(good[:-1] + ("0" if good[-1] != "0" else "1")))
        with self.assertRaises(ValueError):
            decode("XYZ")
