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


class IdempotencyConflict(ValueError):
    """The same request identity conflicts with recorded verified evidence."""


class AnalysisClarificationError(ValueError):
    def __init__(self, questions: tuple):
        self.questions = tuple(questions)
        super().__init__("Analysis needs clarification: {}".format(" ".join(self.questions)))
