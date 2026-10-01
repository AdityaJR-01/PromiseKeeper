"""Domain errors. The API maps these to HTTP 404/422 instead of leaking 500s."""


class PromiseKeeperError(ValueError):
    """Base class: the caller sent something we can't safely act on."""


class InvalidScope(PromiseKeeperError):
    pass


class InvalidState(PromiseKeeperError):
    pass


class UnknownDomain(PromiseKeeperError):
    pass


class UnknownIntervention(PromiseKeeperError):
    pass


class UnknownSimulation(PromiseKeeperError):
    pass
