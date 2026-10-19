import enum


class AuditAction(str, enum.Enum):
    """What an audit event records. Stored as its value in a plain String column."""

    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_ROLE_CHANGED = "user.role_changed"
    USER_DEACTIVATED = "user.deactivated"
    USER_REACTIVATED = "user.reactivated"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_SESSIONS_REVOKED = "user.sessions_revoked"
    LOGIN_SUCCEEDED = "login.succeeded"
    LOGIN_FAILED = "login.failed"
    LOGIN_UNLOCKED = "login.unlocked"
    PASSWORD_CHANGED = "password.changed"
    EXTRACTION_RETRIED = "extraction.retried"
