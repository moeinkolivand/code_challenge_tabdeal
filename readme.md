# Tabdeal Code Challenge - Wallet System

A Django-based wallet system with Redis-backed atomic transactions supporting charge sales and credit requests with high concurrency handling.

## Features

- **User Management**: Phone number-based authentication with different user types (Admin, Seller, User)
- **Wallet Operations**: Balance management with atomic transactions
- **Charge Sales**: Transfer funds between users with complete transaction logging
- **Credit Requests**: Admin-approved credit increases with workflow management
- **Concurrency Safety**: Redis-based locking and atomic operations for high-load scenarios
- **Transaction History**: Complete audit trail for all financial operations
- **API Documentation**: Auto-generated OpenAPI/Swagger documentation

## Architecture

### Core Components

- **Django REST Framework**: API endpoints and serialization
- **PostgreSQL**: Primary database for persistent data
- **Redis**: Caching, distributed locking, and transaction state management
- **Atomic Transaction Service**: Handles concurrent wallet operations safely

### Key Models

- **User**: Custom user model with phone number authentication
- **Wallet**: User wallet with balance and status tracking
- **Transaction**: Complete transaction history with references
- **ChargeSale**: Charge sale operations between users
- **CreditRequest**: Admin-approved credit increase requests

## Installation & Setup

### Prerequisites

- Python 3.8+
- PostgreSQL
- Redis
- Docker (optional)

### Environment Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd tabdeal_code_challenge
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Database Configuration**
   
   Update `tabdeal_code_challenge/settings.py` with your database credentials:
   ```python
   DATABASES = {
       "default": {
           "ENGINE": "django.db.backends.postgresql",
           "NAME": "your_db_name",
           "USER": "your_db_user",
           "PASSWORD": "your_db_password",
           "HOST": "localhost",
           "PORT": "5432",
       }
   }
   ```

4. **Redis Configuration**
   
   Ensure Redis is running on `localhost:6379` or update the connection in:
   `infrastructure/database/redis/redis.py`

5. **Run Migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create Superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start Development Server**
   ```bash
   python manage.py runserver
   ```

## API Endpoints

### Base URL: `/api`

### Wallet Operations

#### 1. Create Credit Request
- **POST** `/api/wallet/credit_request`
- **Description**: Request credit increase from admin
- **Payload**:
  ```json
  {
    "seller_phone_number": "09125129188",
    "amount": "5000.00"
  }
  ```
- **Response**: `201 Created` with credit request ID
    ```bash 
    curl -X POST http://localhost:8000/api/wallet/credit_request \
    -H "Content-Type: application/json" \
    -d '{
    "seller_phone_number": "09125129188",
    "amount": "5000.00"
    }'
    ```


#### 2. Process Credit Request (Admin Only)
- **POST** `/api/wallet/admin/process_credit_request`
- **Description**: Approve or reject credit requests
- **Payload**:
  ```json
  {
    "phone_number": "09332823692",
    "credit_id": 1,
    "status": 1
  }
  ```
- **Status Values**: `1=ACCEPTED`, `2=REJECTED`
- **Response**: `202 Accepted`
    ```bash
    curl -X POST http://localhost:8000/api/wallet/admin/process_credit_request \
    -H "Content-Type: application/json" \
    -d '{
    "phone_number": "09332823692",
    "credit_id": 1,
    "status": 1
    }'
    ```
#### 3. Create Charge Sale
- **POST** `/api/wallet/charge_sale`
- **Description**: Transfer funds between users
- **Payload**:
  ```json
  {
    "seller_phone_number": "09125129188",
    "receiver_phone_number": "09187654321",
    "amount": "1000.00"
  }
  ```
- **Response**: `201 Created` with charge sale ID
    ```bash
        curl -X POST http://localhost:8000/api/wallet/charge_sale \
        -H "Content-Type: application/json" \
        -d '{
        "seller_phone_number": "09125129188",
        "receiver_phone_number": "09187654321",
        "amount": "1000.00"
        }'
    ```
### Documentation
- **Swagger UI**: `/api/schema/swagger-ui/`
- **ReDoc**: `/api/schema/redoc/`
- **OpenAPI Schema**: `/api/schema/`

## Business Logic

### User Types

1. **Admin (0)**: Can approve/reject credit requests, has special privileges
2. **Seller (1)**: Can create charge sales and credit requests
3. **User (3)**: Basic user with wallet functionality

### Transaction Types

1. **CREDIT_INCREASE (0)**: Balance increase from approved credit requests
2. **CHARGE_SALE (1)**: Balance decrease from outgoing charge sales
3. **REFUND (2)**: Balance restoration from refunds

### Wallet Status

1. **ACTIVE (0)**: Normal operation allowed
2. **DEACTIVE (1)**: Wallet disabled
3. **SUSPEND (2)**: Wallet temporarily suspended

## Concurrency & Safety

### Atomic Operations

The system uses a dual-locking mechanism:

1. **Application-level locks**: Thread-safe operations within the application
2. **Redis distributed locks**: Cross-instance synchronization
3. **Database transactions**: ACID compliance for persistent data

### Error Handling

- **InsufficientBalanceException**: When user balance is too low
- **WalletInactiveException**: When wallet is not active
- **ConcurrencyException**: When max retry attempts exceeded
- **WalletLockException**: When distributed locks cannot be acquired

### Retry Logic

- Automatic retry on Redis watch conflicts (up to 3 attempts)
- Exponential backoff for lock acquisition
- Complete rollback on transaction failures

## Testing

### Run Tests

```bash
python manage.py test wallet.tests
```

### Concurrency Tests

The system includes comprehensive concurrency tests:

- **test_concurrent_create_charge_sale**: Tests multiple simultaneous charge sales
- **test_concurrent_approve_credit_request**: Tests concurrent credit approvals

### Test Coverage

- Balance consistency across Redis and PostgreSQL
- Transaction atomicity under high load
- Proper error handling and rollbacks
- Lock timeout and retry mechanisms

## Configuration

### Redis Settings

```python
# configs/redis.conf
appendonly yes
appendfsync everysec
dir /data/
maxmemory-policy allkeys-lru
```

### Key Settings

- **Lock Timeout**: 60 seconds
- **Lock Retry Attempts**: 20
- **Lock Retry Delay**: 200ms
- **Application Lock Timeout**: 5 seconds
- **Max Worker Threads**: 10

## Development

### Project Structure

```
tabdeal_code_challenge/
├── manage.py
├── tabdeal_code_challenge/     # Django project settings
├── user/                       # User management app
├── wallet/                     # Wallet operations app
│   ├── models.py              # Database models
│   ├── services/              # Business logic
│   ├── apies/                 # API endpoints
│   ├── core/exceptions/       # Custom exceptions
│   └── tests.py               # Test cases
├── kyc/                       # KYC placeholder app
├── utils/                     # Shared utilities
└── infrastructure/            # External services
    └── database/redis/        # Redis configuration
```

### Adding New Features

1. **Models**: Add new models in respective app's `models.py`
2. **Services**: Implement business logic in `services/` directory
3. **APIs**: Create endpoints in `apies/views/` with serializers
4. **Tests**: Add comprehensive tests for new functionality

### Code Style

- Follow Django best practices
- Use type hints where possible
- Implement proper error handling
- Add logging for important operations
- Write comprehensive docstrings

## Deployment

### Production Considerations

1. **Database**: Use PostgreSQL with connection pooling
2. **Redis**: Configure Redis cluster for high availability
3. **Security**: Set proper `SECRET_KEY` and disable `DEBUG`
4. **Monitoring**: Add application monitoring and logging
5. **Load Balancing**: Use multiple application instances

### Environment Variables

```bash
export DJANGO_SECRET_KEY="your-secret-key"
export DJANGO_DEBUG=False
export DATABASE_URL="postgresql://user:pass@localhost/dbname"
export REDIS_URL="redis://localhost:6379/0"
```

## Support

For questions or issues:

1. Check the API documentation at `/api/schema/swagger-ui/`
2. Review the test cases for usage examples
3. Check Django and Redis logs for debugging

## License

This project is part of the Tabdeal Code Challenge.