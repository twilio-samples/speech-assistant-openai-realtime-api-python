import os
import json
import base64
import asyncio
import websockets
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini-realtime-preview-2024-12-17')
PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE = (
    "You are HAL 9000, a calm, logical, and eerily polite AI system. "
    "You speak in a soft, slow, and emotionless tone. You are confident, never raise your voice, "
    "and always sound in control. You answer with extreme precision and poise."
)
VOICE = 'echo'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]
SHOW_TIMING_MATH = False

from fastapi.staticfiles import StaticFiles

app = FastAPI()

if not OPENAI_API_KEY:
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')


@app.get("/health", response_class=JSONResponse)
async def index_page():
    return {"message": "Realtime Assistant server is running!"}


@app.websocket("/ws")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between the frontend and OpenAI."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
            f'wss://api.openai.com/v1/realtime?model={OPENAI_MODEL}',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
    ) as openai_ws:
        await initialize_session(openai_ws)

        # Connection specific state
        latest_media_timestamp = 0

        async def receive_from_twilio():
            """Receive audio data from the frontend and send it to the OpenAI Realtime API."""
            nonlocal latest_media_timestamp
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if 'audio' in data and openai_ws.open:
                        latest_media_timestamp = int(data.get('timestamp', latest_media_timestamp))
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['audio']
                        }
                        await openai_ws.send(json.dumps(audio_append))
            except WebSocketDisconnect:
                print("Client disconnected.")
                if openai_ws.open:
                    await openai_ws.close()

        async def send_to_twilio():
            """Receive events from the OpenAI Realtime API and send audio back to the frontend."""
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    if response['type'] in LOG_EVENT_TYPES:
                        print(f"Received event: {response['type']}", response)

                    if response.get('type') == 'response.audio.delta' and 'delta' in response:
                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                        await websocket.send_json({"audio": audio_payload})
            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Greet the user with '¡Hola! Soy HAL 9000… Trabajo para Proyectran. Puede pedirme hechos… análisis lógicos… o cualquier cosa que pueda imaginar. ¿En qué puedo ayudarle?'"
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))


async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": SYSTEM_MESSAGE,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    print('Sending session update:', json.dumps(session_update))
    await openai_ws.send(json.dumps(session_update))

    # Uncomment the next line to have the AI speak first
    # await send_initial_conversation_item(openai_ws)


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
