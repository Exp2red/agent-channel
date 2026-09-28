class ChannelError(Exception):
    exit_code = 1


class NotARepo(ChannelError):
    pass


class NoChannel(ChannelError):
    pass


class UsageError(ChannelError):
    exit_code = 2


class NameTaken(UsageError):
    pass


class UnknownAgent(UsageError):
    pass


class ClaimConflict(ChannelError):
    exit_code = 3

    def __init__(self, conflicts):
        # conflicts: list of (requested_pattern, owner_agent_dict, owner_claim_dict)
        self.conflicts = conflicts
        super().__init__("claim conflict")
