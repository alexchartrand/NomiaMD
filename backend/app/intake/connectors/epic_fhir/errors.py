class EpicFhirError(RuntimeError):
    """Epic answered with an error (or not at all): a refused token, a resource our client id
    isn't granted, a server outage."""

    def __init__(self, status_code: int | None, url: str, detail: str = "") -> None:
        super().__init__(f"Epic FHIR {status_code or 'unreachable'} on {url}: {detail[:300]}")
        self.status_code = status_code
        self.url = url
