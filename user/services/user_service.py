from typing import Optional
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth import get_user_model
from user.enums import UserTypeEnums
from rest_framework.generics import get_object_or_404

User = get_user_model()


class UserService:
    """Service class for handling user-related operations"""

    @staticmethod
    @transaction.atomic
    def create_user(phone_number: str, user_type: int, password: str = None, **kwargs) -> User:
        if not UserTypeEnums.is_valid(user_type):
            raise ValidationError("Invalid user type")

        user = User(phone_number=phone_number, user_type=user_type, **kwargs)
        
        if password:
            user.set_password(password)
            
        user.full_clean()
        user.save()
        return user

    @staticmethod
    def get_user_by_phone(phone_number: str) -> Optional[User]:
        return get_object_or_404(User, phone_number=phone_number)

    @staticmethod
    @transaction.atomic
    def update_user(user: User, **kwargs) -> User:
        for field, value in kwargs.items():
            if field == 'password':
                user.set_password(value)
            else:
                setattr(user, field, value)
                
        user.full_clean()
        user.save()
        return user

    @staticmethod
    def delete_user(user: User) -> None:
        user.delete()

    @staticmethod
    def get_users_by_type(user_type: int) -> list[User]:
        if not UserTypeEnums.is_valid(user_type):
            raise ValidationError("Invalid user type")
            
        return list(User.objects.filter(user_type=user_type))

    @staticmethod
    def authenticate_user(phone_number: str, password: str) -> Optional[User]:
        user = UserService.get_user_by_phone(phone_number)
        if user and user.check_password(password):
            return user
        return None