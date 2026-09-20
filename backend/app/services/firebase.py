"""Firebase Authentication: verify ID tokens (RS256 JWTs signed by Google) without any Google SDK.

The rules are Google's documented ones: the token must be signed by one of the certificates published for
securetoken@system.gserviceaccount.com, `aud` must be the Firebase project ID, `iss` must be
https://securetoken.google.com/<project>, and it must not be expired.
"""
import json
import threading
import time
import urllib.request

import jwt
from cryptography import x509

from .. import config

CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"

_lock = threading.Lock()
_cache: dict = {"certs": {}, "until": 0.0}


class InvalidToken(Exception):
    pass


def enabled() -> bool:
    return bool(config.FIREBASE_PROJECT_ID)


def _certs(force: bool = False) -> dict[str, str]:
    """kid -> PEM certificate, cached for as long as Google says (Cache-Control max-age)."""
    with _lock:
        if force or time.time() >= _cache["until"] or not _cache["certs"]:
            with urllib.request.urlopen(CERTS_URL, timeout=10) as r:
                certs = json.load(r)
                cache_control = r.headers.get("Cache-Control", "")
            max_age = 3600
            for part in cache_control.split(","):
                if part.strip().startswith("max-age="):
                    max_age = int(part.strip().split("=")[1])
            _cache.update(certs=certs, until=time.time() + max_age)
        return _cache["certs"]


def verify(id_token: str) -> dict:
    """Return {"uid", "email", "email_verified", "name"} for a valid token; raise InvalidToken otherwise."""
    project = config.FIREBASE_PROJECT_ID
    issuer = f"https://securetoken.google.com/{project}"
    try:
        if config.FIREBASE_AUTH_EMULATOR_HOST:
            # The local emulator signs nothing. Only ever enable this on a development machine.
            claims = jwt.decode(id_token, options={"verify_signature": False, "verify_aud": False}, algorithms=["none", "RS256"])
            if claims.get("aud") != project or claims.get("iss") != issuer:
                raise InvalidToken("wrong project")
        else:
            kid = jwt.get_unverified_header(id_token).get("kid")
            pem = _certs().get(kid) or _certs(force=True).get(kid)   # Google rotates keys: refetch once for an unknown kid
            if not pem:
                raise InvalidToken("unknown signing key")
            key = x509.load_pem_x509_certificate(pem.encode()).public_key()
            claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=project, issuer=issuer, leeway=10)
    except InvalidToken:
        raise
    except (jwt.PyJWTError, ValueError, OSError, KeyError) as e:
        raise InvalidToken(str(e)) from e
    if not claims.get("sub"):
        raise InvalidToken("no subject")
    return {"uid": claims["sub"], "email": (claims.get("email") or "").lower() or None,
            "email_verified": bool(claims.get("email_verified")), "name": claims.get("name")}
