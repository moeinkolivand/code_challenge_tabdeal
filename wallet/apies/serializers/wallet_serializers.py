from decimal import Decimal
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from wallet.enums import CreditRequestStatusEnums
from wallet.models import CreditRequest


class CreateCreditRequestSerializer(serializers.Serializer):
    seller_phone_number = serializers.CharField(max_length=11, min_length=11)
    amount = serializers.DecimalField(min_value=Decimal("1000"), max_digits=15, decimal_places=2)


class CreateChargeSaleSerializer(serializers.Serializer):
    seller_phone_number = serializers.CharField(max_length=11, min_length=11)
    receiver_phone_number = serializers.CharField(max_length=11, min_length=11)
    amount = serializers.DecimalField(min_value=Decimal("1000"), max_digits=15, decimal_places=2)


class ProcessCreditRequestSerializer(serializers.ModelSerializer):
    status = serializers.IntegerField(help_text="1=WAITING, 2=ACCEPTED, 3=REJECTED")
    credit_id = serializers.IntegerField(min_value=1)
    phone_number = serializers.CharField(max_length=11, min_length=11)
    
    class Meta:
        model = CreditRequest
        fields = (
            "status",
            "credit_id",
            "phone_number",
        )
