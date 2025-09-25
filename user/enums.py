from django.db import models
from django.utils.translation import gettext_lazy as _

class UserTypeEnums(models.IntegerChoices):
    ADMIN = 0, _("Admin")
    SELLER = 1, _("Seller")
    USER = 3, _("User")
