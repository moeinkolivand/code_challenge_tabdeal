from django.db import models
from django.utils.translation import gettext_lazy as _

class WalletStatusEnums(models.IntegerChoices):
    ACTIVE = 0, _("Active")
    DEACTIVE = 1, _("DeActive")
    SUSPEND = 2, _("Suspend") 

class CreditRequestStatusEnums(models.IntegerChoices):
    WAITING = 0, _("Waiting")
    ACCEPTED = 1, _("Accepted")
    REJECTED = 2, _("Rejeted")

class TransactionTypeEnums(models.IntegerChoices): 
    CREDIT_INCREASE = 0, _("CreditIncrease")
    CHARGE_SALE = 1, _("ChargeSale")
    REFUND = 2, _("Refund")


class ChargeSaleTypeEnums(models.IntegerChoices):
    PENDING = 0, _("Pending")
    COMPLETED = 1, _("Completed")
    FAILED = 2, _("Failed")
    REFUNDED = 3, _("Refunded")
