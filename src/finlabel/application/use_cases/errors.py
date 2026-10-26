"""Typed failures returned by application orchestration."""


class ApplicationError(Exception):
    """Base class for errors that inbound adapters can map to their protocol."""


class ProjectNotFound(ApplicationError):
    pass


class InvalidProjectMetadata(ApplicationError):
    pass


class SourceNotFound(ApplicationError):
    pass


class SourceAccessError(ApplicationError):
    pass


class SourceNotReadOnly(ApplicationError):
    pass


class InvalidSourceMetadata(ApplicationError):
    pass


class PlannerUnavailable(ApplicationError, ValueError):
    pass


class PersistenceError(ApplicationError):
    pass
