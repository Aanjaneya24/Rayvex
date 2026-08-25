class PolicyConfigNotFoundError(Exception):

    def __init__(self, merchant_id: str | None):
        self.merchant_id = merchant_id
        super().__init__(
            f"No active policy config found for merchant_id={merchant_id!r} "
            f"and no global default is active either."
        )
