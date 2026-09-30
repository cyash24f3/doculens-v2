import secrets

from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from doculens.errors import DomainError

bearer = HTTPBearer(auto_error=False)


def authenticate(request: Request, credentials: HTTPAuthorizationCredentials | None) -> bool:
    if credentials is None:
        return False
    expected = request.app.state.settings.admin_token
    if not expected or not secrets.compare_digest(credentials.credentials, expected):
        raise DomainError("unauthorized", "Invalid administrator credential", 401)
    return True


def permitted(scope: str, admin: bool):
    if scope not in {"sample", "private"} or (scope == "private" and not admin):
        raise DomainError("forbidden", "This corpus requires administrator access", 403)
    return scope


def require_admin(admin: bool):
    if not admin:
        raise DomainError("forbidden", "Administrator access is required", 403)
