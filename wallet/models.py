import uuid
from utils.base_models import BaseTimeModel
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from wallet.enums import ChargeSaleTypeEnums, CreditRequestStatusEnums, TransactionTypeEnums, WalletStatusEnums
from decimal import Decimal
from django.core.validators import MinValueValidator

User = get_user_model()

class Wallet(BaseTimeModel):
    user = models.OneToOneField(User, verbose_name=_("user"), on_delete=models.CASCADE)
    balance = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    status = models.IntegerField(verbose_name=_("status"), choices=WalletStatusEnums.choices, default=WalletStatusEnums.ACTIVE)
    
    def __str__(self):
        return f"{self.user.phone_number} - Balance: {self.balance}"
    
    class Meta:
        verbose_name = "wallet"
        verbose_name_plural = "wallets"


class CreditRequest(BaseTimeModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credit_requests')
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1000.00'))]
    )
    status = models.IntegerField(verbose_name=_("status"), choices=CreditRequestStatusEnums.choices, default=CreditRequestStatusEnums.WAITING)
    admin = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='processed_credit_requests'
    )
    
    class Meta:
        verbose_name = "credit_request"
        verbose_name_plural = "created_requests"
    
    def __str__(self):
        return f"Credit Request - {self.user.phone_number}: {self.amount} ({self.status})"



class Transaction(BaseTimeModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.IntegerField(verbose_name=_("transaction_type"), choices=TransactionTypeEnums.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    balance_before = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    balance_after = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    reference_id = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    admin_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='supervised_transactions'
    )
    
    class Meta:
        verbose_name = "transaction"
        verbose_name_plural = "transactions"
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.seller.phone_number}: {self.amount}"


class ChargeSale(BaseTimeModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='charge_sales')
    phone_number = models.CharField(max_length=11, verbose_name=_("phone_number"))
    amount = models.DecimalField(
        max_digits=15, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1000.00'))]
    )
    status = models.IntegerField(verbose_name=_("status"), choices=ChargeSaleTypeEnums.choices, default=ChargeSaleTypeEnums.PENDING)
    transaction = models.OneToOneField(
        Transaction, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='charge_sale'
    )

    class Meta:
        verbose_name = "charge_sale"
        verbose_name_plural = "charge_sales"
