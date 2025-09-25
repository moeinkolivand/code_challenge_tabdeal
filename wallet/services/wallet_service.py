from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
import json
import logging
import threading
import time
import uuid
from django.db import transaction
import redis
from infrastructure.database.redis.redis import redis_client
from user.enums import UserTypeEnums
from wallet.core.exceptions.wallet_exceptions import *
from redis_lock import RedisLock
from django.contrib.auth import get_user_model

from wallet.enums import ChargeSaleTypeEnums, CreditRequestStatusEnums, TransactionTypeEnums, WalletStatusEnums
from wallet.models import ChargeSale, CreditRequest, Transaction, Wallet

User = get_user_model()
logger = logging.getLogger(__name__)

class AtomicWalletService:
    def __init__(self):
        self.redis_client = redis_client
        self.local_locks = defaultdict(threading.Lock)
        self.lock_timeout = 60
        self.lock_retry_attempts = 20
        self.lock_retry_delay = 0.2
        self.app_lock_time_out = 5.0

    @contextmanager
    def dual_wallet_lock(self, user_id1: int, user_id2: int):
        ids = sorted([user_id1, user_id2])
        lock_keys = [f"lock:wallet:{id}" for id in ids]
        locks = []
        app_lock_key = f"app_lock_{ids[0]}_{ids[1]}"
        
        if not self.local_locks[app_lock_key].acquire(blocking=True, timeout=self.app_lock_time_out):
            raise WalletLockException("Could not acquire application lock")
        
        try:
            for lock_key in lock_keys:
                lock = RedisLock(self.redis_client, lock_key, self.lock_timeout)
                attempts = 0
                while attempts < self.lock_retry_attempts:
                    if lock.acquire():
                        locks.append(lock)
                        break
                    attempts += 1
                    if attempts < self.lock_retry_attempts:
                        time.sleep(self.lock_retry_delay)
                else:
                    raise WalletLockException(f"Could not acquire Redis lock: {lock_key} after {self.lock_retry_attempts} attempts")
            yield locks
        finally:
            for lock in locks:
                lock.release()
            self.local_locks[app_lock_key].release()

    def get_or_create_wallet(self, user: User) -> Wallet:
        wallet, created = Wallet.objects.get_or_create(
            user=user,
            defaults={'balance': Decimal('0.00'), 'status': WalletStatusEnums.ACTIVE}
        )
        user_key = f"wallet:user:{user.id}"
        if self.redis_client.hget(user_key, "balance") is None:
            self.redis_client.hset(user_key, "balance", str(wallet.balance))
        return wallet

    def get_wallet_balance(self, user_id: int) -> Decimal:
        user_key = f"wallet:user:{user_id}"
        balance_str = self.redis_client.hget(user_key, "balance")
        return Decimal(balance_str) if balance_str else Decimal('0.00')

    def create_charge_sale_atomic(self, user: User, phone_number: str, amount: Decimal) -> ChargeSale:
        if amount <= 0:
            raise ValidationError("Amount must be positive")
        if amount < Decimal('1000.00'):
            raise ValidationError("Minimum charge amount is 1000")

        target_user, _ = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={"password": "", "user_type": UserTypeEnums.USER}
        )
        seller_wallet = self.get_or_create_wallet(user)
        target_wallet = self.get_or_create_wallet(target_user)

        if seller_wallet.status != WalletStatusEnums.ACTIVE:
            raise WalletInactiveException("Seller wallet is not active")
        if target_wallet.status != WalletStatusEnums.ACTIVE:
            raise WalletInactiveException("Target wallet is not active")

        charge_sale = ChargeSale.objects.create(
            id=uuid.uuid4(),
            user=user,
            phone_number=phone_number,
            amount=amount,
            status=ChargeSaleTypeEnums.PENDING
        )

        retry_count = 0
        while retry_count < 3:
            try:
                with self.dual_wallet_lock(user.id, target_user.id):
                    seller_key = f"wallet:user:{user.id}"
                    target_key = f"wallet:user:{target_user.id}"
                    seller_trans_key = f"transactions:user:{user.id}"
                    target_trans_key = f"transactions:user:{target_user.id}"

                    seller_original_balance = self.get_wallet_balance(user.id)
                    target_original_balance = self.get_wallet_balance(target_user.id)
                    seller_trans_json = None
                    target_trans_json = None

                    try:
                        # Check balance
                        if seller_original_balance < amount:
                            raise InsufficientBalanceException("Insufficient balance in seller wallet")

                        # Update Redis balances
                        new_seller_balance = seller_original_balance - amount
                        new_target_balance = target_original_balance + amount

                        with self.redis_client.pipeline() as pipe:
                            pipe.watch(seller_key, target_key)
                            current_seller_balance = Decimal(pipe.hget(seller_key, "balance") or '0.00')
                            current_target_balance = Decimal(pipe.hget(target_key, "balance") or '0.00')
                            if current_seller_balance != seller_original_balance or \
                               current_target_balance != target_original_balance:
                                raise redis.WatchError("Balance changed during transaction")
                            if current_seller_balance < amount:
                                raise InsufficientBalanceException("Insufficient balance in seller wallet")

                            pipe.multi()
                            pipe.hset(seller_key, "balance", str(new_seller_balance))
                            pipe.hset(target_key, "balance", str(new_target_balance))
                            
                            # Create transaction data
                            seller_trans = {
                                'id': str(uuid.uuid4()),
                                'amount': str(-amount),
                                'balance_before': str(seller_original_balance),
                                'balance_after': str(new_seller_balance),
                                'reference_id': str(charge_sale.id),
                                'description': f"Charge sale deduction to {phone_number}",
                                'timestamp': int(time.time())
                            }
                            target_trans = {
                                'id': str(uuid.uuid4()),
                                'amount': str(amount),
                                'balance_before': str(target_original_balance),
                                'balance_after': str(new_target_balance),
                                'reference_id': str(charge_sale.id),
                                'description': f"Charge sale credit from {user.phone_number}",
                                'timestamp': int(time.time())
                            }
                            seller_trans_json = json.dumps(seller_trans)
                            target_trans_json = json.dumps(target_trans)
                            pipe.rpush(seller_trans_key, seller_trans_json)
                            pipe.rpush(target_trans_key, target_trans_json)
                            pipe.execute()

                        # Update database
                        with transaction.atomic():
                            seller_transaction = Transaction.objects.create(
                                id=uuid.UUID(seller_trans['id']),
                                seller=user,
                                transaction_type=TransactionTypeEnums.CHARGE_SALE,
                                amount=-amount,
                                balance_before=seller_original_balance,
                                balance_after=new_seller_balance,
                                reference_id=str(charge_sale.id),
                                description=seller_trans['description']
                            )
                            target_transaction = Transaction.objects.create(
                                id=uuid.UUID(target_trans['id']),
                                seller=target_user,
                                transaction_type=TransactionTypeEnums.CREDIT_INCREASE,
                                amount=amount,
                                balance_before=target_original_balance,
                                balance_after=new_target_balance,
                                reference_id=str(charge_sale.id),
                                description=target_trans['description']
                            )
                            seller_wallet.balance = new_seller_balance
                            target_wallet.balance = new_target_balance
                            seller_wallet.save(update_fields=['balance'])
                            target_wallet.save(update_fields=['balance'])
                            charge_sale.status = ChargeSaleTypeEnums.COMPLETED
                            charge_sale.transaction = seller_transaction
                            charge_sale.save(update_fields=['status', 'transaction'])

                        logger.info(f"Charge sale completed: {charge_sale.id}")
                        return charge_sale

                    except Exception as e:
                        # Rollback Redis
                        self.redis_client.hset(seller_key, "balance", str(seller_original_balance))
                        self.redis_client.hset(target_key, "balance", str(target_original_balance))
                        if seller_trans_json:
                            self.redis_client.lrem(seller_trans_key, 1, seller_trans_json)
                        if target_trans_json:
                            self.redis_client.lrem(target_trans_key, 1, target_trans_json)
                        charge_sale.status = ChargeSaleTypeEnums.FAILED
                        charge_sale.save(update_fields=['status'])
                        logger.error(f"Charge sale failed with rollback: {charge_sale.id} - {str(e)}")
                        raise WalletServiceException(f"Charge sale failed: {str(e)}")

            except redis.WatchError:
                retry_count += 1
                logger.warning(f"Redis watch conflict, retry {retry_count}/3")
                if retry_count >= 3:
                    charge_sale.status = ChargeSaleTypeEnums.FAILED
                    charge_sale.save(update_fields=['status'])
                    raise ConcurrencyException("Max retries exceeded for charge sale")
                time.sleep(0.1 * retry_count)

        charge_sale.status = ChargeSaleTypeEnums.FAILED
        charge_sale.save(update_fields=['status'])
        raise ConcurrencyException("Max retries exceeded for charge sale")

    def approve_credit_request_atomic(self, credit_request_id: int, admin_user: User) -> CreditRequest:
        """Approve credit request with atomic dual-wallet updates."""
        try:
            credit_request = CreditRequest.objects.get(
                id=credit_request_id,
                status=CreditRequestStatusEnums.WAITING
            )
        except CreditRequest.DoesNotExist:
            raise ValidationError("Credit request not found or already processed")

        user = credit_request.user
        amount = credit_request.amount

        admin_wallet = self.get_or_create_wallet(admin_user)
        user_wallet = self.get_or_create_wallet(user)

        if admin_wallet.status != WalletStatusEnums.ACTIVE:
            raise WalletInactiveException("Admin wallet is not active")
        if user_wallet.status != WalletStatusEnums.ACTIVE:
            raise WalletInactiveException("User wallet is not active")

        if admin_user.id == user.id:
            with self.dual_wallet_lock(user.id, user.id):  # Single lock for self
                user_key = f"wallet:user:{user.id}"
                user_trans_key = f"transactions:user:{user.id}"
                user_original_balance = self.get_wallet_balance(user.id)
                user_trans_json = None

                try:
                    # No balance change for self-transfer
                    with self.redis_client.pipeline() as pipe:
                        pipe.watch(user_key)
                        current_balance = Decimal(pipe.hget(user_key, "balance") or '0.00')
                        if current_balance != user_original_balance:
                            raise redis.WatchError("Balance changed")
                        if current_balance < amount:
                            raise InsufficientBalanceException("Insufficient balance for self-transfer")

                        user_trans = {
                            'id': str(uuid.uuid4()),
                            'amount': "0.00",
                            'balance_before': str(user_original_balance),
                            'balance_after': str(user_original_balance),
                            'reference_id': str(credit_request.id),
                            'description': f"Self-transfer for credit request {credit_request.id}",
                            'timestamp': int(time.time())
                        }
                        user_trans_json = json.dumps(user_trans)
                        pipe.multi()
                        pipe.hset(user_key, "balance", str(user_original_balance))  # No change
                        pipe.rpush(user_trans_key, user_trans_json)
                        pipe.execute()

                    with transaction.atomic():
                        Transaction.objects.create(
                            id=uuid.UUID(user_trans['id']),
                            seller=user,
                            transaction_type=TransactionTypeEnums.CREDIT_INCREASE,
                            amount=Decimal('0.00'),
                            balance_before=user_original_balance,
                            balance_after=user_original_balance,
                            reference_id=str(credit_request.id),
                            description=user_trans['description'],
                            admin_user=admin_user
                        )
                        user_wallet.balance = user_original_balance
                        user_wallet.save(update_fields=['balance'])
                        credit_request.status = CreditRequestStatusEnums.ACCEPTED
                        credit_request.admin = admin_user
                        credit_request.save(update_fields=['status', 'admin'])

                    logger.info(f"Credit approval (self-transfer) completed: {credit_request.id}")
                    return credit_request

                except Exception as e:
                    if user_trans_json:
                        self.redis_client.lrem(user_trans_key, 1, user_trans_json)
                    credit_request.status = CreditRequestStatusEnums.FAILED
                    credit_request.save(update_fields=['status'])
                    logger.error(f"Credit approval (self-transfer) failed with rollback: {credit_request.id} - {str(e)}")
                    raise WalletServiceException(f"Credit approval failed: {str(e)}")

        retry_count = 0
        while retry_count < 3:
            try:
                with self.dual_wallet_lock(admin_user.id, user.id):
                    admin_key = f"wallet:user:{admin_user.id}"
                    user_key = f"wallet:user:{user.id}"
                    admin_trans_key = f"transactions:user:{admin_user.id}"
                    user_trans_key = f"transactions:user:{user.id}"

                    admin_original_balance = self.get_wallet_balance(admin_user.id)
                    user_original_balance = self.get_wallet_balance(user.id)
                    admin_trans_json = None
                    user_trans_json = None

                    try:
                        if admin_original_balance < amount:
                            raise InsufficientBalanceException("Admin insufficient balance")

                        new_admin_balance = admin_original_balance - amount
                        new_user_balance = user_original_balance + amount

                        with self.redis_client.pipeline() as pipe:
                            pipe.watch(admin_key, user_key)
                            current_admin_balance = Decimal(pipe.hget(admin_key, "balance") or '0.00')
                            current_user_balance = Decimal(pipe.hget(user_key, "balance") or '0.00')
                            if current_admin_balance != admin_original_balance or \
                               current_user_balance != user_original_balance:
                                raise redis.WatchError("Balance changed")
                            if current_admin_balance < amount:
                                raise InsufficientBalanceException("Admin insufficient balance")

                            pipe.multi()
                            pipe.hset(admin_key, "balance", str(new_admin_balance))
                            pipe.hset(user_key, "balance", str(new_user_balance))
                            
                            admin_trans = {
                                'id': str(uuid.uuid4()),
                                'amount': str(-amount),
                                'balance_before': str(admin_original_balance),
                                'balance_after': str(new_admin_balance),
                                'reference_id': str(credit_request.id),
                                'description': f"Transfer to user {user.id} for credit request",
                                'timestamp': int(time.time())
                            }
                            user_trans = {
                                'id': str(uuid.uuid4()),
                                'amount': str(amount),
                                'balance_before': str(user_original_balance),
                                'balance_after': str(new_user_balance),
                                'reference_id': str(credit_request.id),
                                'description': f"Credit increase from admin {admin_user.id}",
                                'timestamp': int(time.time())
                            }
                            admin_trans_json = json.dumps(admin_trans)
                            user_trans_json = json.dumps(user_trans)
                            pipe.rpush(admin_trans_key, admin_trans_json)
                            pipe.rpush(user_trans_key, user_trans_json)
                            pipe.execute()

                        with transaction.atomic():
                            admin_transaction = Transaction.objects.create(
                                id=uuid.UUID(admin_trans['id']),
                                seller=admin_user,
                                transaction_type=TransactionTypeEnums.CHARGE_SALE,
                                amount=-amount,
                                balance_before=admin_original_balance,
                                balance_after=new_admin_balance,
                                reference_id=str(credit_request.id),
                                description=admin_trans['description'],
                                admin_user=admin_user
                            )
                            user_transaction = Transaction.objects.create(
                                id=uuid.UUID(user_trans['id']),
                                seller=user,
                                transaction_type=TransactionTypeEnums.CREDIT_INCREASE,
                                amount=amount,
                                balance_before=user_original_balance,
                                balance_after=new_user_balance,
                                reference_id=str(credit_request.id),
                                description=user_trans['description'],
                                admin_user=admin_user
                            )
                            admin_wallet.balance = new_admin_balance
                            user_wallet.balance = new_user_balance
                            admin_wallet.save(update_fields=['balance'])
                            user_wallet.save(update_fields=['balance'])
                            credit_request.status = CreditRequestStatusEnums.ACCEPTED
                            credit_request.admin = admin_user
                            credit_request.save(update_fields=['status', 'admin'])

                        logger.info(f"Credit approval completed: {credit_request.id}")
                        return credit_request

                    except Exception as e:
                        self.redis_client.hset(admin_key, "balance", str(admin_original_balance))
                        self.redis_client.hset(user_key, "balance", str(user_original_balance))
                        if admin_trans_json:
                            self.redis_client.lrem(admin_trans_key, 1, admin_trans_json)
                        if user_trans_json:
                            self.redis_client.lrem(user_trans_key, 1, user_trans_json)
                        credit_request.status = CreditRequestStatusEnums.FAILED
                        credit_request.save(update_fields=['status'])
                        logger.error(f"Credit approval failed with rollback: {credit_request.id} - {str(e)}")
                        raise WalletServiceException(f"Credit approval failed: {str(e)}")

            except redis.WatchError:
                retry_count += 1
                logger.warning(f"Redis watch conflict, retry {retry_count}/3")
                if retry_count >= 3:
                    credit_request.status = CreditRequestStatusEnums.FAILED
                    credit_request.admin = admin_user
                    credit_request.save(update_fields=['status'])
                    raise ConcurrencyException("Max retries exceeded for credit approval")
                time.sleep(0.1 * retry_count)

        credit_request.status = CreditRequestStatusEnums.FAILED
        credit_request.save(update_fields=['status'])
        raise ConcurrencyException("Max retries exceeded for credit approval")

class WalletService:
    MAX_THREADS = 10
    MAX_RETRY_ATTEMPTS = 3
    REDIS_TRANSACTION_TTL = 300
    LOCK_TIMEOUT = 30
    
    def __init__(self):
        self.redis_client = redis_client
        self.atomic_service = AtomicWalletService()
        self.local_locks = {}
        self.executor = ThreadPoolExecutor(self.MAX_THREADS, "wallet_service")

    def _get_wallet_key(self, user_id: int) -> str:
        return f"wallet:user:{user_id}"

    def _get_transaction_key(self, user_id: int) -> str:
        return f"transactions:user:{user_id}"

    def get_or_create_wallet_db_only(self, user: User) -> Wallet:
        wallet, created = Wallet.objects.get_or_create(
            user=user,
            defaults={'balance': Decimal('0.00'), 'status': WalletStatusEnums.ACTIVE}
        )
        return wallet

    def get_or_create_wallet(self, user: User) -> Wallet:
        return self.atomic_service.get_or_create_wallet(user)

    def get_wallet_balance(self, user: User) -> Decimal:
        return self.atomic_service.get_wallet_balance(user.id)

    def create_credit_request(self, user: User, amount: Decimal) -> CreditRequest:
        if Decimal(amount) < Decimal('1000.00'):
            raise ValidationError("Minimum credit request amount is 1000")
        credit_request = CreditRequest.objects.create(
            user=user,
            amount=amount,
            status=CreditRequestStatusEnums.WAITING
        )
        logger.info(f"Credit request created: {credit_request.id} for user {user.id}")
        return credit_request

    def reject_credit_request(self, credit_request_id: int, admin_user: User) -> CreditRequest:
        with transaction.atomic():
            try:
                credit_request = CreditRequest.objects.get(
                    id=credit_request_id,
                    status=CreditRequestStatusEnums.WAITING
                )
            except CreditRequest.DoesNotExist:
                raise ValidationError("Credit request not found or already processed")
            credit_request.status = CreditRequestStatusEnums.REJECTED
            credit_request.admin = admin_user
            credit_request.save(update_fields=['status', 'admin'])
            logger.info(f"Credit request rejected: {credit_request.id} by admin {admin_user.id}")
        return credit_request

    def create_charge_sale(self, user: User, phone_number: str, amount: Decimal) -> ChargeSale:
        try:
            future = self.executor.submit(
                self.atomic_service.create_charge_sale_atomic,
                user,
                phone_number,
                amount
            )
            result = future.result()
            return result
        except Exception as e:
            logger.error(f"Charge sale failed for user {user.id}: {str(e)}")
            raise WalletServiceException(f"Charge sale failed: {str(e)}")

    def approve_credit_request_single(self, credit_request_id: int, admin_user: User) -> CreditRequest:
        try:
            future = self.executor.submit(
                self.atomic_service.approve_credit_request_atomic,
                credit_request_id,
                admin_user
            )
            result = future.result()
            return result
        except Exception as e:
            logger.error(f"Credit approval failed for request {credit_request_id}: {str(e)}")
            raise WalletServiceException(f"Credit approval failed: {str(e)}")
