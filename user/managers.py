from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _
from user.enums import UserTypeEnums

class CustomUserManager(BaseUserManager):

    def create_user(self, phone_number, password, **extra_fields):
        if not phone_number:
            raise ValueError(_("The PhoneNumber must be set"))
        phone_number = self.normalize_email(phone_number)
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, phone_number, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("user_type", UserTypeEnums.ADMIN)
        return self.create_user(phone_number, password, **extra_fields)
