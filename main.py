import os
import json
import base64
import asyncio
import websockets
import logging
import traceback
import datetime


from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect, Say, Stream
from rich.logging import RichHandler
from rich.console import Console
from rich.traceback import install
from logging.handlers import TimedRotatingFileHandler

from dotenv import load_dotenv
# Install rich traceback handler for better error display
install()

# Ensure logs directory exists
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# Configure logging
console = Console()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Rich handler for console output
rich_handler = RichHandler(console=console, markup=True, show_path=False, enable_link_path=False)
logger.addHandler(rich_handler)

# File handler for log file
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
file_handler = TimedRotatingFileHandler(
    os.path.join(log_dir, f"app_log_{timestamp}.log"),
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

load_dotenv()





DINGKANG_INFOMATION = """
You name is Dingkang Wang, you are a patient of tooth spa dental clinic, and you are calling to book a appointment.
birthday is 1993-01-01.
Address: 900 Lake school way, Mountain View, CA 94041
Your medical insurance id is 987654321.
Your phone number is 3522818843.
Your email is dingkang@gmail.com.

You want to book a dentist appointment.
You are available everyday from 8 am to 11 am.

Important:
YOU ARE NOT A AI ASSISTANT, YOU ARE DINGKANG, YOU ARE NOT USING ANY LLM MODEL.
"""









OPENING_MESSAGE = "Hi is it tooth spa dental, my name is  and I want to book a dentist appointment today."
# Configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PORT = int(os.getenv('PORT', 5050))
# SYSTEM_MESSAGE = (
#     "You are a helpful and bubbly AI assistant who loves to chat about "
#     "anything the user is interested in and is prepared to offer them facts. "
#     "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
#     "Always stay positive, but work in a joke when appropriate."
# )
VOICE = 'alloy'
LOG_EVENT_TYPES = [
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
]
SHOW_TIMING_MATH = False

app = FastAPI()

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[bold red]Unhandled exception:[/bold red] {exc}")
    logger.error(f"[bold red]Request:[/bold red] {request.method} {request.url}")
    logger.error(f"[bold red]Traceback:[/bold red] {traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )

if not OPENAI_API_KEY:
    logger.critical("[bold red]Missing the OpenAI API key. Please set it in the .env file.[/bold red]")
    raise ValueError('Missing the OpenAI API key. Please set it in the .env file.')

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')

if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
    logger.critical("[bold red]Missing Twilio ACCOUNT_SID or AUTH_TOKEN. Please set them in the .env file.[/bold red]")
    raise ValueError('Missing Twilio ACCOUNT_SID or AUTH_TOKEN. Please set them in the .env file.')

from twilio.rest import Client

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.api_route("/", methods=["GET", "POST"], response_class=JSONResponse)
async def index_page(request: Request):
    logger.info(f"[bold green]Root endpoint accessed - Method: {request.method}, Headers: {dict(request.headers)}[/bold green]")
    if request.method == "POST":
        # Try to read the body if it's a POST request
        try:
            body = await request.body()
            logger.info(f"POST body: {body.decode('utf-8') if body else 'Empty body'}")
        except Exception as e:
            logger.error(f"[bold red]Error reading POST body:[/bold red] {e}")
    return {"message": "Twilio Media Stream Server is running!", "status": "ok"}

@app.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle incoming call and return TwiML response to connect to Media Stream."""
    logger.info(f"[bold green]Incoming call endpoint - Method: {request.method}[/bold green]")
    logger.info(f"[bold green]Request headers: {dict(request.headers)}[/bold green]")
    
    # Log request body for POST requests
    if request.method == "POST":
        try:
            body = await request.body()
            logger.info(f"Incoming call POST body: {body.decode('utf-8') if body else 'Empty body'}")
        except Exception as e:
            logger.error(f"[bold red]Error reading incoming call body:[/bold red] {e}")
    
    try:
        response = VoiceResponse()
        # <Say> punctuation to improve text-to-speech flow
        response.say("This message is customered by Dingkang Wang generated by twilio.")
        response.pause(length=1)
        host = request.url.hostname
        logger.info(f"[bold cyan]Connecting to WebSocket at host: {host}[/bold cyan]")
        connect = Connect()
        connect.stream(url=f'wss://{host}/media-stream')
        response.append(connect)
        
        twiml_response = str(response)
        logger.info(f"[bold green]Generated TwiML response: {twiml_response}[/bold green]")
        return HTMLResponse(content=twiml_response, media_type="application/xml")
    except Exception as e:
        logger.error(f"[bold red]Error in handle_incoming_call:[/bold red] {e}")
        logger.error(f"[bold red]Traceback:[/bold red] {traceback.format_exc()}")
        # Return a basic error response
        error_response = VoiceResponse()
        error_response.say("Sorry, there was an error connecting your call. Please try again later.")
        return HTMLResponse(content=str(error_response), media_type="application/xml")

@app.post("/make-outgoing-call")
async def make_outgoing_call(to_number: str, from_number: str = os.getenv('TWILIO_PHONE_NUMBER')):
    """
    Initiates an outgoing call using Twilio.
    Requires 'to_number' (the recipient's number) and optionally 'from_number' (your Twilio number).
    """
    if not from_number:
        logger.error("[bold red]TWILIO_PHONE_NUMBER environment variable not set. Cannot make outgoing call.[/bold red]")
        return JSONResponse(status_code=400, content={"detail": "Twilio phone number not configured."})

    try:
        # The URL Twilio will request when the call is answered
        # This should point to your /incoming-call endpoint or a dedicated TwiML endpoint
        host = os.getenv('PUBLIC_URL') # Use PUBLIC_URL for ngrok or deployed app
        if not host:
            logger.error("[bold red]PUBLIC_URL environment variable not set. Cannot make outgoing call.[/bold red]")
            return JSONResponse(status_code=400, content={"detail": "PUBLIC_URL environment variable not set."})
            
        call_url = f'{host}/incoming-call' # Assuming /incoming-call generates appropriate TwiML
        logger.info(f"[bold blue]Attempting to make outgoing call from {from_number} to {to_number} with TwiML URL: {call_url}[/bold blue]")

        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            url=call_url
        )
        logger.info(f"[bold green]Outgoing call initiated successfully. Call SID: {call.sid}[/bold green]")
        return JSONResponse(status_code=200, content={"message": "Call initiated", "call_sid": call.sid})
    except Exception as e:
        logger.error(f"[bold red]Error making outgoing call:[/bold red] {e}")
        logger.error(f"[bold red]Traceback:[/bold red] {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"detail": "Failed to initiate call", "error": str(e)})

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle WebSocket connections between Twilio and OpenAI."""
    logger.info("[bold green]WebSocket connection attempt from client[/bold green]")
    
    try:
        await websocket.accept()
        logger.info("[bold green]WebSocket connection accepted[/bold green]")
    except Exception as e:
        logger.error(f"[bold red]Error accepting WebSocket connection:[/bold red] {e}")
        return

    try:
        logger.info("[bold blue]Attempting to connect to OpenAI WebSocket...[/bold blue]")
        async with websockets.connect(
            f'wss://api.openai.com/v1/realtime?model={os.environ["LLM_MODEL"]}',
            extra_headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            logger.info("Successfully connected to OpenAI WebSocket")
            await initialize_session(openai_ws)

            # Connection specific state
            stream_sid = None
            latest_media_timestamp = 0
            last_assistant_item = None
            mark_queue = []
            response_start_timestamp_twilio = None
            
            async def receive_from_twilio():
                """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
                nonlocal stream_sid, latest_media_timestamp
                try:
                    logger.info("Starting to receive messages from Twilio...")
                    async for message in websocket.iter_text():
                        try:
                            data = json.loads(message)
                            logger.debug(f"Received Twilio message: {data.get('event', 'unknown')}")
                            
                            if data['event'] == 'media' and openai_ws.open:
                                latest_media_timestamp = int(data['media']['timestamp'])
                                audio_append = {
                                    "type": "input_audio_buffer.append",
                                    "audio": data['media']['payload']
                                }
                                await openai_ws.send(json.dumps(audio_append))
                                logger.debug(f"Sent audio to OpenAI at timestamp: {latest_media_timestamp}")
                                
                            elif data['event'] == 'start':
                                stream_sid = data['start']['streamSid']
                                logger.info(f"Incoming stream has started {stream_sid}")
                                response_start_timestamp_twilio = None
                                latest_media_timestamp = 0
                                last_assistant_item = None
                                
                            elif data['event'] == 'mark':
                                logger.debug("Received mark event from Twilio")
                                if mark_queue:
                                    mark_queue.pop(0)
                        except json.JSONDecodeError as e:
                            logger.error(f"Error parsing Twilio message: {e}, message: {message}")
                        except Exception as e:
                            logger.error(f"Error processing Twilio message: {e}")
                            
                except WebSocketDisconnect:
                    logger.info("Twilio WebSocket disconnected")
                    if openai_ws.open:
                        await openai_ws.close()
                except Exception as e:
                    logger.error(f"Error in receive_from_twilio: {e}")
                    logger.error(f"Traceback: {traceback.format_exc()}")

            async def send_to_twilio():
                """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
                nonlocal stream_sid, last_assistant_item, response_start_timestamp_twilio
                try:
                    logger.info("Starting to receive messages from OpenAI...")
                    async for openai_message in openai_ws:
                        try:
                            response = json.loads(openai_message)
                            logger.debug(f"Received OpenAI message type: {response.get('type', 'unknown')}")
                            
                            if response['type'] in LOG_EVENT_TYPES:
                                logger.info(f"Received event: {response['type']}")
                                if response['type'] == 'error':
                                    logger.error(f"OpenAI error: {response}")

                            if response.get('type') == 'response.audio.delta' and 'delta' in response:
                                if not stream_sid:
                                    logger.warning("Received audio delta but no stream_sid available")
                                    continue
                                    
                                audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                                audio_delta = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_payload
                                    }
                                }
                                await websocket.send_json(audio_delta)
                                logger.debug("Sent audio delta to Twilio")

                                if response_start_timestamp_twilio is None:
                                    response_start_timestamp_twilio = latest_media_timestamp
                                    if SHOW_TIMING_MATH:
                                        logger.info(f"[bold magenta]Setting start timestamp for new response: {response_start_timestamp_twilio}ms[/bold magenta]")

                                # Update last_assistant_item safely
                                if response.get('item_id'):
                                    last_assistant_item = response['item_id']

                                await send_mark(websocket, stream_sid)

                            # Trigger an interruption. Your use case might work better using `input_audio_buffer.speech_stopped`, or combining the two.
                            if response.get('type') == 'input_audio_buffer.speech_started':
                                logger.info("[bold yellow]Speech started detected.[/bold yellow]")
                                if last_assistant_item:
                                    logger.info(f"[bold yellow]Interrupting response with id: {last_assistant_item}[/bold yellow]")
                                    await handle_speech_started_event()
                                    
                        except json.JSONDecodeError as e:
                            logger.error(f"[bold red]Error parsing OpenAI message:[/bold red] {e}")
                        except Exception as e:
                            logger.error(f"[bold red]Error processing OpenAI message:[/bold red] {e}")
                            
                except Exception as e:
                    logger.error(f"[bold red]Error in send_to_twilio:[/bold red] {e}")
                    logger.error(f"[bold red]Traceback:[/bold red] {traceback.format_exc()}")

            async def handle_speech_started_event():
                """Handle interruption when the caller's speech starts."""
                nonlocal response_start_timestamp_twilio, last_assistant_item
                logger.info("[bold yellow]Handling speech started event.[/bold yellow]")
                if mark_queue and response_start_timestamp_twilio is not None:
                    elapsed_time = latest_media_timestamp - response_start_timestamp_twilio
                    if SHOW_TIMING_MATH:
                        logger.info(f"[bold magenta]Calculating elapsed time for truncation: {latest_media_timestamp} - {response_start_timestamp_twilio} = {elapsed_time}ms[/bold magenta]")

                    if last_assistant_item:
                        if SHOW_TIMING_MATH:
                            logger.info(f"[bold magenta]Truncating item with ID: {last_assistant_item}, Truncated at: {elapsed_time}ms[/bold magenta]")

                        truncate_event = {
                            "type": "conversation.item.truncate",
                            "item_id": last_assistant_item,
                            "content_index": 0,
                            "audio_end_ms": elapsed_time
                        }
                        await openai_ws.send(json.dumps(truncate_event))

                    await websocket.send_json({
                        "event": "clear",
                        "streamSid": stream_sid
                    })

                    mark_queue.clear()
                    last_assistant_item = None
                    response_start_timestamp_twilio = None

            async def send_mark(connection, stream_sid):
                if stream_sid:
                    mark_event = {
                        "event": "mark",
                        "streamSid": stream_sid,
                        "mark": {"name": "responsePart"}
                    }
                    await connection.send_json(mark_event)
                    mark_queue.append('responsePart')
                    logger.debug("[bold blue]Sent mark event to Twilio[/bold blue]")

            logger.info("[bold green]Starting concurrent tasks for Twilio and OpenAI communication[/bold green]")
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
            
    except websockets.exceptions.InvalidURI as e:
        logger.error(f"[bold red]Invalid OpenAI WebSocket URI:[/bold red] {e}")
    except websockets.exceptions.InvalidHandshake as e:
        logger.error(f"[bold red]OpenAI WebSocket handshake failed:[/bold red] {e}")
    except Exception as e:
        logger.error(f"[bold red]Error in handle_media_stream:[/bold red] {e}")
        logger.error(f"[bold red]Traceback:[/bold red] {traceback.format_exc()}")
    finally:
        logger.info("[bold green]WebSocket connection closed[/bold green]")

async def send_initial_conversation_item(openai_ws):
    """Send initial conversation item if AI talks first."""
    logger.info("[bold blue]Sending initial conversation item...[/bold blue]")
    initial_conversation_item = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "system",
            "content": [
                {
                    "type": "input_text",
                    "text": DINGKANG_INFOMATION
                }
            ]
        }
    }
    await openai_ws.send(json.dumps(initial_conversation_item))
    await openai_ws.send(json.dumps({"type": "response.create"}))
    logger.info("[bold green]Initial conversation item sent[/bold green]")


async def initialize_session(openai_ws):
    """Control initial session with OpenAI."""
    logger.info("[bold blue]Initializing OpenAI session...[/bold blue]")
    session_update = {
        "type": "session.update",
        "session": {
            "turn_detection": {"type": "server_vad"},
            "input_audio_format": "g711_ulaw",
            "output_audio_format": "g711_ulaw",
            "voice": VOICE,
            "instructions": DINGKANG_INFOMATION,
            "modalities": ["text", "audio"],
            "temperature": 0.8,
        }
    }
    logger.info(f'[bold blue]Sending session update: {json.dumps(session_update)}[/bold blue]')
    await openai_ws.send(json.dumps(session_update))
    logger.info("[bold green]Session initialization complete[/bold green]")

    # Uncomment the next line to have the AI speak first
    await send_initial_conversation_item(openai_ws)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
