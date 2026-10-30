"""Errors the API and CLI can show without leaking stack traces."""


class CareBridgeError(Exception):
    """Expected failure with a message that is safe to show a patient or developer."""


class PlanNotFound(CareBridgeError):
    """No care plan is stored under the given id."""


class DocumentError(CareBridgeError):
    """The discharge file could not be read."""
