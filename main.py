import os
import json
import base64
import struct
import asyncio
import audioop
import websockets
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv

load_dotenv(override=True)

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PORT = int(os.getenv("PORT", 5050))
SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)
MODEL = "gemini-3.1-flash-live-preview"
VOICE = "Aoede"

app = FastAPI()

if not GEMINI_API_KEY:
    raise ValueError("Missing the Gemini API key. Please set it in the .env file.")


def ulaw_to_pcm16k_base64(ulaw_b64: str) -> str:
    """PCMU base64 (8kHz) → PCM16 base64 (16kHz). Upsampled for Gemini."""
    pcm8 = audioop.ulaw2lin(base64.b64decode(ulaw_b64), 2)
    pcm16, _ = audioop.ratecv(pcm8, 2, 1, 8000, 16000, None)
    return base64.b64encode(pcm16).decode("utf-8")


class OutputAudioConverter:
    """Stateful 24kHz PCM → 8kHz PCMU converter with buffered alignment."""

    def __init__(self):
        self._buffer = b""

    def pcm24k_to_ulaw_base64(self, pcm_b64: str) -> str | None:
        raw = base64.b64decode(pcm_b64)
        self._buffer += raw

        # Need groups of 3 samples (6 bytes) for 3:1 downsampling
        n_groups = len(self._buffer) // 6
        if n_groups == 0:
            return None

        usable = n_groups * 6
        samples = struct.unpack_from(f"<{n_groups * 3}h", self._buffer)
        self._buffer = self._buffer[usable:]

        # Average every 3 samples for 24kHz → 8kHz
        averages = [
            (samples[i * 3] + samples[i * 3 + 1] + samples[i * 3 + 2]) // 3
            for i in range(n_groups)
        ]
        downsampled = struct.pack(f"<{n_groups}h", *averages)
        ulaw = audioop.lin2ulaw(downsampled, 2)
        return base64.b64encode(ulaw).decode("utf-8")


@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"message": "Twilio Media Stream Server is running!"}


@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    response = VoiceResponse()
    # <Say> punctuation to improve text-to-speech flow
    response.say("Connecting you now.", voice="Google.en-US-Chirp3-HD-Aoede")
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f"wss://{host}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and Gemini Live."""
    print("Client connected")
    await websocket.accept()

    async with websockets.connect(
        f"wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={GEMINI_API_KEY}"
    ) as gemini_ws:
        await initialize_session(gemini_ws)

        # Have Gemini speak first
        await gemini_ws.send(
            json.dumps(
                {
                    "realtimeInput": {
                        "text": "Say hi and ask how you can help. Keep it under 15 words."
                    }
                }
            )
        )

        # Connection specific state
        stream_sid = None
        latest_media_timestamp = 0
        mark_queue = []
        gemini_transcript = ""
        output_converter = OutputAudioConverter()

        async def receive_from_twilio():
            """Receive audio data from Twilio and send it to Gemini Live."""
            nonlocal stream_sid, latest_media_timestamp
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    if data["event"] == "media" and gemini_ws.state.name == "OPEN":
                        latest_media_timestamp = int(data["media"]["timestamp"])
                        await gemini_ws.send(
                            json.dumps(
                                {
                                    "realtimeInput": {
                                        "audio": {
                                            "data": ulaw_to_pcm16k_base64(
                                                data["media"]["payload"]
                                            ),
                                            "mimeType": "audio/pcm;rate=16000",
                                        }
                                    }
                                }
                            )
                        )
                    elif data["event"] == "start":
                        stream_sid = data["start"]["streamSid"]
                        print(f"Incoming stream has started {stream_sid}")
                        latest_media_timestamp = 0
                    elif data["event"] == "mark":
                        if mark_queue:
                            mark_queue.pop(0)
            except WebSocketDisconnect:
                print("Client disconnected.")
                if gemini_ws.state.name == "OPEN":
                    await gemini_ws.close()

        async def send_to_twilio():
            """Receive events from Gemini Live, send audio back to Twilio."""
            nonlocal stream_sid, gemini_transcript
            try:
                async for gemini_message in gemini_ws:
                    response = json.loads(gemini_message)

                    if "serverContent" in response:
                        server_content = response["serverContent"]

                        # Audio output from Gemini
                        if "modelTurn" in server_content:
                            for part in server_content["modelTurn"].get("parts", []):
                                if "inlineData" in part:
                                    audio_b64_ulaw = (
                                        output_converter.pcm24k_to_ulaw_base64(
                                            part["inlineData"]["data"]
                                        )
                                    )
                                    if audio_b64_ulaw is None:
                                        continue
                                    audio_delta = {
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {"payload": audio_b64_ulaw},
                                    }
                                    await websocket.send_json(audio_delta)
                                    await send_mark(websocket, stream_sid)

                        # Handle interruption (barge-in)
                        if server_content.get("interrupted"):
                            print("Gemini response interrupted by user speech.")
                            gemini_transcript = ""
                            await websocket.send_json(
                                {"event": "clear", "streamSid": stream_sid}
                            )
                            mark_queue.clear()

                        # Log transcription
                        if "outputTranscription" in server_content:
                            gemini_transcript += server_content["outputTranscription"][
                                "text"
                            ]

                        # User transcription
                        if "inputTranscription" in server_content:
                            user_text = server_content["inputTranscription"]["text"]
                            if user_text:
                                print(f"You said: {user_text}")

                        # Print full Gemini transcript on turn complete
                        if server_content.get("turnComplete") and gemini_transcript:
                            print(f"Gemini said: {gemini_transcript}")
                            gemini_transcript = ""

            except Exception as e:
                print(f"Error in send_to_twilio: {e}")

        async def send_mark(connection, stream_sid):
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"},
                }
                await connection.send_json(mark_event)
                mark_queue.append("responsePart")

        await asyncio.gather(receive_from_twilio(), send_to_twilio())


async def initialize_session(gemini_ws):
    """Send initial configuration to Gemini Live API."""
    setup_message = {
        "setup": {
            "model": f"models/{MODEL}",
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}
                },
            },
            "systemInstruction": {"parts": [{"text": SYSTEM_MESSAGE}]},
            "inputAudioTranscription": {},
        }
    }
    print("Sending setup:", json.dumps(setup_message))
    await gemini_ws.send(json.dumps(setup_message))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
