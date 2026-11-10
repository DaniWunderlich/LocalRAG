"""Safe application errors suitable for API responses and registry metadata."""


class AppError(Exception):
    """Describe an actionable failure without exposing upstream response bodies."""

    def __init__(
        self, message: str, status_code: int = 503, code: str = "service_unavailable"
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
