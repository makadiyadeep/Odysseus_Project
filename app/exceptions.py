class BusinessRuleError(Exception):
    """Base exception for domain-level business rule violations."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def __str__(self):
        return f"{self.code}: {self.message}"


class CapacityExceededError(BusinessRuleError):
    def __init__(self, message: str = "Cruise capacity is insufficient."):
        super().__init__("CAPACITY_EXCEEDED", message)


class PromotionValidationError(BusinessRuleError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message)
