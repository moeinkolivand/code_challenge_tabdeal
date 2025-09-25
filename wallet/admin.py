from django.contrib import admin
from wallet.models import ChargeSale, CreditRequest, Transaction, Wallet

admin.site.register(ChargeSale)
admin.site.register(CreditRequest)
admin.site.register(Transaction)
admin.site.register(Wallet)
