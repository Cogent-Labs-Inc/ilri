class InputRejected(Exception):
    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason


class CaptureConfigurationError(RuntimeError):
    pass


class ApprovalNotPermitted(ValueError):
    pass
