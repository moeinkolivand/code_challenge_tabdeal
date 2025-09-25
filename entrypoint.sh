#!/bin/sh

echo "Waiting for postgres..."
while ! nc -z db 5432; do
  sleep 0.5
done

echo "Postgres is up — running migrations..."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Create superuser if not exists
python manage.py shell <<EOF
from django.contrib.auth import get_user_model
from wallet.models import Wallet
from decimal import Decimal
User = get_user_model()
if not User.objects.filter(phone_number="09332823692").exists():
    user = User.objects.create_superuser(phone_number="09332823692", password="admin123", user_type=0)
    Wallet.objects.get_or_create(user=user, balance=Decimal("100000"))
if not User.objects.filter(phone_number="09125129188").exists():
    user = User.objects.create(phone_number="09125129188", password="admin123", user_type=3)
EOF

exec "$@"