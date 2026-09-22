"""Stable error taxonomy for UI, logs, and automation."""


class DipStudioError(Exception):
    """Base error that may be shown as a controlled application failure."""


class ValidationError(DipStudioError):
    """A domain invariant or input validation failed."""


class NotFoundError(DipStudioError):
    """A requested entity or resource was not found."""


class PersistenceError(DipStudioError):
    """A project could not be saved or loaded."""


class ProcessingError(DipStudioError):
    """A processing operation failed."""


class OptionalBackendError(ProcessingError):
    """A processor requires an unavailable optional backend."""


class RenderingError(DipStudioError):
    """A document could not be rendered from its layer data."""


class CancellationError(DipStudioError):
    """A cooperative operation was cancelled."""


class PluginError(DipStudioError):
    """A plugin violated its contract or failed to load."""
