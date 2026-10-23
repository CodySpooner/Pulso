"""Safe Data Health codes; provider messages can contain IPs or credentials."""

import json

from pulso_sources.framework import Response, RunDeferred


class CJError(RunDeferred):
    def __init__(self, code: str, message: str, *, disable: bool = False) -> None:
        super().__init__(message)
        self.code, self.disable = code, disable


# The framework persists exception class names as Data Health error codes.
class cj_api_disabled_inactivity(CJError):
    pass


class cj_ip_user_limit(CJError):
    pass


class cj_points_exhausted(CJError):
    pass


class cj_rate_limited(CJError):
    pass


class cj_category_unresolved(CJError):
    pass


def classify_error(response: Response) -> CJError | None:
    try:
        payload = json.loads(response.body or b"{}")
    except ValueError, UnicodeDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    code = str(payload.get("code", ""))
    message = str(payload.get("message", "")).lower()
    if code == "1600014":
        return cj_api_disabled_inactivity(
            "cj_api_disabled_inactivity",
            "CJ API disabled: 30 days without orders; reactivate the owning account in My CJ",
            disable=True,
        )
    if "one ip limit" in message or b"one ip limit" in (response.body or b"").lower():
        return cj_ip_user_limit(
            "cj_ip_user_limit", "CJ permits at most three users per IP", disable=True
        )
    if code == "16900500" or "insufficient api points" in message:
        return cj_points_exhausted(
            "cj_points_exhausted", "CJ points exhausted; wait for a later slot"
        )
    if response.status_code == 429 or code == "1600200":
        return cj_rate_limited("cj_rate_limited", "CJ rate limit; wait for a later slot")
    if code in {"1600001", "1600003"}:
        return CJError("cj_token_expired", "CJ token rejected; refresh once")
    if response.status_code == 401:
        return CJError("cj_auth_failed", "CJ authentication or account level rejected")
    if payload.get("result") is False or code not in {"", "200"}:
        return CJError("cj_api_error", "CJ API rejected the request")
    if response.status_code is not None and response.status_code >= 400:
        return CJError("cj_http_error", "CJ HTTP request failed")
    return None
