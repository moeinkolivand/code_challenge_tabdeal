import random
from django.test import TransactionTestCase
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.db import connection
from user.enums import UserTypeEnums
from wallet.models import User, Wallet  
from decimal import Decimal
import threading
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from wallet.models import Wallet, Transaction, ChargeSale
from wallet.enums import (
    ChargeSaleTypeEnums, 
    CreditRequestStatusEnums, 
    TransactionTypeEnums, 
)
from user.enums import UserTypeEnums
from infrastructure.database.redis.redis import redis_client
from wallet.services.wallet_service import WalletService

User = get_user_model()

from django.db.models import Sum

class ConcurrencyChargeSaleTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.redis_client = redis_client
        self.wallet_service = WalletService()
        self.redis_client.flushall()
        self.user = User.objects.create(phone_number="08994562531", password="132456789", user_type=UserTypeEnums.ADMIN)
        wallet = self.wallet_service.get_or_create_wallet(self.user)
        self.initialize_balance = Decimal("30000000")
        wallet.balance = self.initialize_balance # 10,000,000,000
        wallet.save(update_fields=["balance"])
        self.redis_client.hset(f"wallet:user:{self.user.id}", "balance", str(wallet.balance))

    def tearDown(self):
        cursor = connection.cursor()
        cursor.execute("SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = 'test_django_db' AND pid <> pg_backend_pid();")
        return super().tearDown()
    
    def test_concurrent_create_charge_sale(self):
        phone_numbers = {
            "1": {"phone_number": "09123456789", "chosen_time": 0},
            "2": {"phone_number": "09129129122", "chosen_time": 0}
        }
        amount = Decimal("30000")
        num_threads = 50
        results = []
        seller_wallet = Wallet.objects.get(user=self.user)
        seller_balance_before_request = seller_wallet.balance
        calls_per_thread = 1000 // num_threads
        phone_lock = threading.Lock()

        def worker():
            results = []
            for _ in range(calls_per_thread):
                try:
                    with phone_lock:
                        key = random.choice(list(phone_numbers.keys()))
                        phone_numbers[key]["chosen_time"] += 1
                        phone = phone_numbers[key]["phone_number"]
                    sale = self.wallet_service.create_charge_sale(self.user, phone, amount)
                    results.append(sale.status)
                except (WalletLockException, InsufficientBalanceException) as e:
                    logger.warning(f"Charge sale failed: {str(e)}")
                    results.append(str(e))
                finally:
                    connection.close()
            return results


        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker) for _ in range(num_threads)]
            for f in as_completed(futures):
                results.append(f.result())

        wallet = Wallet.objects.get(user=self.user)
        final_balance = wallet.balance
        redis_balance = Decimal(self.redis_client.hget(f"wallet:user:{self.user.id}", "balance"))

        seller_transactions = Transaction.objects.filter(
            seller=self.user,
            transaction_type=TransactionTypeEnums.CHARGE_SALE
        )
        total_amount_seller = seller_transactions.aggregate(total_decrease=Sum("amount"))['total_decrease']

        target_transactions = {}
        for _, info in phone_numbers.items():
            phone = info['phone_number']
            target_transactions[phone] = Transaction.objects.filter(
                seller__phone_number=phone,
                transaction_type=TransactionTypeEnums.CREDIT_INCREASE
            )
            total_amount_target = target_transactions[phone].aggregate(total_increase=Sum("amount"))['total_increase']
            target_wallet = Wallet.objects.get(user__phone_number=phone)
            expected_target_balance = amount * info['chosen_time']
            self.assertEqual(
                target_wallet.balance, expected_target_balance,
                f"Target wallet balance for {phone} must match expected"
            )
            self.assertEqual(
                total_amount_target, expected_target_balance,
                f"Total transaction amount for {phone} must match wallet balance"
            )
            self.assertEqual(
                target_transactions[phone].count(), info['chosen_time'],
                f"Number of transactions for {phone} must match chosen_time"
            )

        expected_seller_balance = seller_balance_before_request + total_amount_seller
        self.assertEqual(seller_transactions.count(), calls_per_thread * num_threads, "Number of seller transactions must match successful sales")
        self.assertEqual(final_balance, expected_seller_balance, "Seller balance must match expected balance")
        self.assertEqual(final_balance, redis_balance, "Redis and DB balances must match")
        self.assertGreaterEqual(final_balance, 0, "Final balance must be non-negative")

        charge_sales = ChargeSale.objects.filter(user=self.user)
        self.assertEqual(
            charge_sales.filter(status=ChargeSaleTypeEnums.COMPLETED).count(),
            calls_per_thread * num_threads,
            "Number of completed charge sales must match"
        )
        for sale in charge_sales.filter(status=ChargeSaleTypeEnums.COMPLETED):
            transaction = Transaction.objects.get(reference_id=str(sale.id), seller=self.user)
            self.assertEqual(transaction.amount, -amount, f"Transaction for sale {sale.id} must have correct amount")
            self.assertEqual(
                transaction.transaction_type,
                TransactionTypeEnums.CHARGE_SALE,
                f"Transaction for sale {sale.id} must be CHARGE_SALE"
            )

        print(
            f"Final balance: {final_balance}, Redis balance: {redis_balance}, "
            f"Phone selections: { {k: v['chosen_time'] for k, v in phone_numbers.items()} } \n"
            f"Total Request {num_threads * calls_per_thread} And Each Call Reduce {amount} \n So Total Value Reduced Must Be :{num_threads * calls_per_thread * amount} \n And Admin Balance Is {final_balance} And Initialized Balance Is {self.initialize_balance}"
        )

    def test_concurrent_approve_credit_request(self):
        """Test concurrent credit request approvals (self-transfer)."""
        num_threads = 5
        user = User.objects.create(phone_number="09125129188", user_type=UserTypeEnums.USER, password="123123")
        credit_request_amount = Decimal("1000.00")
        credit_requests = [
            self.wallet_service.create_credit_request(user, credit_request_amount)
            for _ in range(num_threads)
        ]
        results = []
        admin_wallet = Wallet.objects.get(user=self.user)
        admin_wallet_balance_before_request = admin_wallet.balance
        admin_wallet_balance_before_request_redis = Decimal(
            self.redis_client.hget(f"wallet:user:{self.user.id}", "balance")
        )
        def worker(request_id):
            try:
                request = self.wallet_service.approve_credit_request_single(request_id, self.user)
                return request.status
            except (
                WalletLockException,
                InsufficientBalanceException,
                ValidationError,
                ConcurrencyException,
            ) as e:
                return str(e)
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker, req.id) for req in credit_requests]
            for f in as_completed(futures):
                results.append(f.result())

        user_wallet = Wallet.objects.get(user=user)
        
        successful_approvals = sum(
            1 for r in results if r == CreditRequestStatusEnums.ACCEPTED
        )
        redis_user_balance = Decimal(
            self.redis_client.hget(f"wallet:user:{user.id}", "balance")
        )
        redis_admin_balance = Decimal(
            self.redis_client.hget(f"wallet:user:{self.user.id}", "balance")
        )
        wallet_admin_balance = Wallet.objects.get(user=self.user)
        expected_user_balance = credit_request_amount * len(results)
        self.assertEqual(redis_admin_balance, admin_wallet_balance_before_request_redis - expected_user_balance)
        self.assertEqual(wallet_admin_balance.balance, admin_wallet_balance_before_request - expected_user_balance)
        self.assertEqual(user_wallet.balance, expected_user_balance)
        self.assertEqual(redis_user_balance, user_wallet.balance)

        for request in credit_requests:
            request.refresh_from_db()
            if request.status == CreditRequestStatusEnums.ACCEPTED:
                self.assertEqual(request.admin, self.user)
        print(
            f"User final balance: {user_wallet.balance}, Redis balance: {redis_user_balance}, "
            f"Successful approvals: {successful_approvals}"
        )
