from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
from user.enums import UserTypeEnums
from user.services.user_service import UserService
from wallet.apies.serializers.wallet_serializers import CreateChargeSaleSerializer, CreateCreditRequestSerializer, ProcessCreditRequestSerializer
from wallet.enums import CreditRequestStatusEnums
from wallet.services.wallet_service import WalletService
from rest_framework import status
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied

user_service = UserService()
wallet_service = WalletService()

class CreateCreditRequest(APIView):
    @extend_schema(
        request=CreateCreditRequestSerializer,
        responses=None
    )
    def post(self, request, *args, **kwargs):
        serializer = CreateCreditRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = user_service.get_user_by_phone(data['seller_phone_number'])
        credit_request = wallet_service.create_credit_request(user, data['amount'])
        return Response(status=status.HTTP_201_CREATED, data={"code": credit_request.id})

class ProccessCreditRequest(APIView):
    @extend_schema(
        request=ProcessCreditRequestSerializer,
        responses=None
    )
    def post(self, request, *args, **kwargs):
        serializer = ProcessCreditRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        admin_user = user_service.get_user_by_phone(data['phone_number'])
        if admin_user.user_type != UserTypeEnums.ADMIN:
            raise PermissionDenied()
        response_data={"msg": "done"}
        if data.get("status") == CreditRequestStatusEnums.ACCEPTED.value:
            wallet_service.approve_credit_request_single(
                credit_request_id=data['credit_id'],
                admin_user=admin_user
            )
            return Response(status=status.HTTP_202_ACCEPTED, data=response_data)
        wallet_service.reject_credit_request(
                credit_request_id=data['credit_id'],
                admin_user=admin_user
        )
        return Response(status=status.HTTP_202_ACCEPTED, data=response_data)

class CreateChargeSale(APIView):
    @extend_schema(
        request=CreateChargeSaleSerializer,
        responses=None
    )
    def post(self, request, *args, **kwargs):
        serializer = CreateChargeSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = user_service.get_user_by_phone(data['seller_phone_number'])
        charge_sale = wallet_service.create_charge_sale(user, data['receiver_phone_number'], data['amount'])
        return Response(status=status.HTTP_201_CREATED, data={"code": charge_sale.id})
