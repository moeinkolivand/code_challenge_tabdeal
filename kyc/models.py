from django.db import models
from utils.base_models import BaseTimeModel
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()

class Kyc(BaseTimeModel):
    user = models.OneToOneField(User, verbose_name=_("user"), on_delete=models.CASCADE)
    """
    fields for kyc will be add here in the bussines logic dosnt say anything about it 
    fields like national_code, prof video , signature image, etc ...
    """
    
    class Meta:
        verbose_name = "kyc"
        verbose_name_plural = "kyces"
