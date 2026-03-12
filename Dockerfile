FROM python:3.11-slim

WORKDIR /app

COPY setup.py ./
COPY services ./services
COPY config ./config
COPY helpers ./helpers
COPY tests ./tests

RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install ".[test]"