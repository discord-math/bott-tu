# Running Everything in Docker

- Build the containers:
  ```sh
  docker compose build
  ```
- Initial configuration (only required once):
  ```sh
  docker compose run bot python -m bot.setup
  # You will be prompted to enter the token
  ```
- Run the bot:
  ```sh
  docker compose up
  # ^C to stop
  ```

Upon every change to the codebase you'll need to re-do the "build" step. If the DB is cleaned out by e.g. `docker compose down --volumes`, you'll need to re-do the "initial configuration" step.

# Running the Bot in a Virtual Environment

- Create the Python virtual environment (only required once):
  ```sh
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt -r requirements_dev.txt
  ```
- Start the database in Docker:
  ```sh
  docker compose run migrations
  ```
  If there were no migrations since last time you can simply start the DB directly:
  ```sh
  docker compose start db
  ```
- Every time you open a new shell you'll need to enter the virtual environment:
  ```sh
  source .venv/bin/activate
  ```
- Initial configuration (only required once):
  ```sh
  python -m bot.setup
  DATABASE=postgres://bot:bot@localhost/bot python -m bot.setup
  # You will be prompted to enter the token
  ```
- Run the bot:
  ```sh
  DATABASE=postgres://bot:bot@localhost/bot python -m bot
  # ^C to stop
  ```

This way the bot will run the code in the working directory. If the DB is cleaned out by e.g. `docker compose down --volumes`, you'll need to re-do the "initial configuration" step.
