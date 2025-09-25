from django.urls import path
from wallet.apies.views.wallet_views import CreateChargeSale, CreateCreditRequest, ProccessCreditRequest

urlpatterns = [
    path("credit_request", CreateCreditRequest.as_view(), name="credit_request"),
    path("charge_sale", CreateChargeSale.as_view(), name="charge sale"),
    path("admin/process_credit_request", ProccessCreditRequest.as_view(), name="process credit request")
]
