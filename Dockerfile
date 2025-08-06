FROM python:3.13.5-alpine3.22

WORKDIR /srv/bot

COPY . .

RUN pip install -r requirements.txt

CMD python -m bot
