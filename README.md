# HAL 9000 Web Speech Assistant (Python)

This project exposes a small FastAPI server that connects a HAL 9000‑themed web interface with the OpenAI Realtime API.
Audio from your microphone is streamed to OpenAI over WebSocket and the synthesized response is played back in the browser.
CSS credits: `https://codepen.io/giana/pen/XmjOBG`

## Prerequisites

- **Python 3.13+** – tested with Python 3.13.5
- **An OpenAI API key** with access to the Realtime API
- Optional: Docker if you prefer running the container

## Local Setup

1. (Optional) create and activate a virtual environment
   ```bash
   python3 -m venv env
   source env/bin/activate
   ```
2. Install the dependencies
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example environment file and add your credentials
   ```bash
   cp .env.example .env
   # edit .env and set OPENAI_API_KEY
   ```
4. Start the server
   ```bash
   python main.py
   ```

Visit `http://localhost:5050` and click **Start** to converse with HAL.

## Docker

Create the `.env` file as above and run:
```bash
docker compose up --build
```

## Features

- HAL 9000 inspired UI served from the `static` folder
- Streams audio to and from the OpenAI Realtime API
- Optional initial greeting (see `send_initial_conversation_item` in `main.py`)
- Basic interruption handling when you talk over HAL

Have fun—and remember, HAL is always listening.
