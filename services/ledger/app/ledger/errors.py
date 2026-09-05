class LedgerError(Exception):
    pass


class EmptyTransaction(LedgerError):
    pass


class UnbalancedTransaction(LedgerError):
    pass


class ZeroAmountLeg(LedgerError):
    pass


class CurrencyMismatch(LedgerError):
    pass


class AccountNotInGroup(LedgerError):
    pass


class IdempotencyKeyConflict(LedgerError):
    pass


class TransactionNotFound(LedgerError):
    pass


class TransactionAlreadyReversed(LedgerError):
    pass
