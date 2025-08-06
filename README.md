Create a virtual environment:
```sh
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements_dev.txt
```

Run the bot:
```sh
source .venv/bin/activate
python -m bot
```

Alternatively, run in Docker:
```sh
docker compose build
docker compose up
```
