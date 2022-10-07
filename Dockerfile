FROM python:3.10.6-alpine

RUN adduser -D containeruser
USER containeruser
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main.py .

CMD [ "python", "/app/main.py" ]
