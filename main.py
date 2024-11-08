import os
import uuid
from typing import Optional

import websockets
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse
from twilio.rest import Client  # type: ignore

from entity import Call, Session
from media_stream_handler import MediaStreamConnection
from settings import API_KEY, OPENAI_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

PORT = int(os.getenv('PORT', 5050))
VOICE = 'alloy'

app = FastAPI()

# Permanently retains a history of all calls. Finished calls have their
# transcript property set.
sessions: dict[str, Session] = {}


@app.post("/call")
async def call(request: Request, call: Call) -> PlainTextResponse:
    api_key: Optional[str] = request.headers.get("Authorization")
    if api_key != f"Bearer {API_KEY}":
        raise HTTPException(403, "Invalid phone call tool API key.")

    call_id: str = str(uuid.uuid4())
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    host = request.url.hostname
    client.calls.create(
        to=call.phone,
        from_="+12523620740",
        twiml=f"""<Response>
    <Connect>
        <Stream name="Example Audio Stream" url="wss://{host}/media-stream/{call_id}" />
    </Connect>
</Response>"""
    )

    sessions[call_id] = Session(intent_prompt=call.intent_prompt)
    return PlainTextResponse(call_id)


@app.get("/transcript/{call_id}")
async def transcript(request: Request, call_id: str) -> JSONResponse:
    session: Optional[Session] = sessions.get(call_id)
    if not session:
        raise HTTPException(400, "Invalid session ID.")

    if not session.transcript:
        return JSONResponse(None, 202)

    return JSONResponse([message.model_dump() for message in session.transcript])


@app.websocket("/media-stream/{call_id}")
async def media_stream(websocket: WebSocket, call_id: str):
    """Handle WebSocket connections between Twilio and OpenAI."""
    print("Client connected")
    session: Optional[Session] = sessions.get(call_id)
    if not session:
        return

    await websocket.accept()

    connection: MediaStreamConnection
    async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1"
        }
    ) as openai_ws:
        connection = MediaStreamConnection(
            websocket, openai_ws, VOICE, session.intent_prompt)
        await connection.handle()
    
    session.transcript = connection.transcript

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
