from rest_framework.exceptions import ValidationError

class InsufficientBalanceException(ValidationError):
    """Raised when user doesn't have enough balance"""
    pass

class WalletInactiveException(ValidationError):
    """Raised when wallet is inactive"""
    pass

# Its Not Good Idea To Use Redis Transaction Error As Validation Error
class RedisTransactionError(ValidationError):
    """Raised when Redis transaction fails"""
    pass

class WalletLockException(ValidationError):
    """Raised when Redis transaction fails"""
    pass

class WalletServiceException(ValidationError):
    """Raised when Redis transaction fails"""
    pass

class ConcurrencyException(ValidationError):
    """Raised when Redis transaction fails"""
    pass
