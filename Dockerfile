FROM python:3.11-alpine

WORKDIR /app

RUN apk add --no-cache postgresql-dev gcc python3-dev musl-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    apk del gcc python3-dev musl-dev

COPY . .

EXPOSE 8000
