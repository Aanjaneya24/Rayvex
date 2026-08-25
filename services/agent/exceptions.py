class MalformedAgentOutputError(Exception):

    def __init__(self, detail: str, raw_output: str | None = None):
        self.detail = detail
        self.raw_output = raw_output
        super().__init__(f"Malformed agent output: {detail}")
