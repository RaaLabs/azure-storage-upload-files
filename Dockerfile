FROM python:3.10.6-alpine

RUN adduser -D containeruser

WORKDIR /app

ENV VIRTUAL_ENV=/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main.py .

USER containeruser

CMD [ "python", "/app/main.py" ]
