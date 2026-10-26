import secrets


class TemporaryPasswordGenerator:
    """The one-time password an admin hands over when creating or resetting an account. The
    user must replace it at their first login (User.must_change_password), so it only has to
    survive the hand-off: 16 URL-safe characters, ~96 bits of entropy."""

    def generate(self) -> str:
        return secrets.token_urlsafe(12)
