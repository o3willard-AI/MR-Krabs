from enum import Enum

class FailureAction(Enum):
    LOG_ONLY = "log_only"              # log and continue to next tier
    NOTIFY_AND_ESCALATE = "notify_and_escalate"  # notify, then continue
    NOTIFY_AND_WAIT = "notify_and_wait"          # notify, wait for human, then continue or abort