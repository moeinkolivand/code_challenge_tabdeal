from django.urls import path, include


urlpatterns = [
    path("api/wallet/", include("wallet.apies.urls"))
]