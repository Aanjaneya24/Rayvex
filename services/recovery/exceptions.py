from models.enums import CaseState


class InvalidTransitionError(Exception):

    def __init__(self, from_state: CaseState | None, to_state: CaseState):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Illegal state transition: {from_state.value if from_state else 'None'} "
            f"-> {to_state.value}"
        )


class CaseNotFoundError(Exception):
    def __init__(self, case_id):
        self.case_id = case_id
        super().__init__(f"Case not found: {case_id}")


class RecoveryConfigNotFoundError(Exception):

    def __init__(self, merchant_id: str | None):
        self.merchant_id = merchant_id
        super().__init__(
            f"No active recovery config found for merchant_id={merchant_id!r} "
            f"and no global default is active either."
        )


class WrongCaseStateError(Exception):

    def __init__(self, case_id, expected: CaseState, actual: CaseState):
        self.case_id = case_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Case {case_id} must be in {expected.value} for this operation, "
            f"but is in {actual.value}"
        )
