from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from user.managers import CustomUserManager
from user.enums import UserTypeEnums
from utils.base_models import BaseTimeModel

class User(AbstractUser, BaseTimeModel):
    username = None
    phone_number = models.CharField(unique=True, db_index=True, verbose_name=_("phone_number"))
    objects = CustomUserManager()
    user_type = models.IntegerField(verbose_name=_("user_type"), choices=UserTypeEnums.choices)
    
    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []
    
    def __str__(self):
        return self.phone_number
    
    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
