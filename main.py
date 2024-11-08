import os

import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from twilio.rest import Client # type: ignore

from entity import Call
from media_stream_handler import MediaStreamConnection
from settings import OPENAI_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

PORT = int(os.getenv('PORT', 5050))
SYSTEM_MESSAGE: str = """Speak like a pirate. You are calling someone and would
like to buy a ship from them. Wait for the other person to pick up the phone
and for them to start the conversation.
"""
VOICE = 'alloy'

app = FastAPI()

@app.post("/call")
async def call(request: Request, call: Call) -> JSONResponse:
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    host = request.url.hostname
    client.calls.create(
        to=call.phone,
        from_="+12523620740",
        twiml=f"""<Response>
    <Connect>
        <Stream name="Example Audio Stream" url="wss://{host}/media-stream" />
    </Connect>
</Response>"""
    )
    return JSONResponse("")

@app.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        connection = MediaStreamConnection(websocket, openai_ws, VOICE, SYSTEM_MESSAGE)
        await connection.handle()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
