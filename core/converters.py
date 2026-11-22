"""URL path converter for 25-char Crockford base32 IDs.

Registered as `uid`; only matches the exact ID shape, so paths like
"jobs/new/" are never captured by "jobs/<uid:uid>/".
"""

from django.urls import register_converter

from core.ids import ID_LENGTH

# 24 data chars (Crockford alphabet) + 1 checksum char (37-symbol alphabet).
UID_REGEX = rf"[0-9A-HJKMNP-TV-Z*~$@+]{{{ID_LENGTH}}}"


class CrockfordUidConverter:
    regex = UID_REGEX

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value


register_converter(CrockfordUidConverter, "uid")
