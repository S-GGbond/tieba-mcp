from __future__ import annotations

from typing import Any


class TiebaError(Exception):
    code = "tieba_error"

    def __init__(self, message: str, hint: str = "", **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.extra = extra

    def to_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        payload.update(self.extra)
        return payload


class VerificationRequired(TiebaError):
    code = "verification_required"


class AccessDenied(TiebaError):
    code = "access_denied"


class NotFound(TiebaError):
    code = "not_found"


class ParseFailure(TiebaError):
    code = "parse_failure"


class NetworkFailure(TiebaError):
    code = "network_failure"