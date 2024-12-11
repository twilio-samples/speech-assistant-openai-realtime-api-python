from abc import ABC, abstractmethod
import asyncio
from io import BytesIO
import json
import base64
from asyncio import Queue

import pyaudio

SYSTEM_MESSAGE = (
    "You are a helpful and bubbly AI assistant who loves to chat about "
    "anything the user is interested in and is prepared to offer them facts. "
    "You have a penchant for dad jokes, owl jokes, and rickrolling – subtly. "
    "Always stay positive, but work in a joke when appropriate."
)
VOICE = 'alloy'

class RealtimeObserver(ABC):
    def __init__(self):
        self.client = None

    def register_client(self, client):
        self.client = client

    @abstractmethod 
    async def run(self, openai_ws):
        pass
    
    @abstractmethod 
    async def update(self, message):
        pass

class OpenAIRealtimeObserver:
    def __init__(self):
        self.client = None

    def register_client(self, client):
        self.client = client

    async def run(self, openai_ws):
        await self.initialize_session(openai_ws)
        await self.send_initial_conversation_item(openai_ws)

    async def update(self, message):
        print(f"Received event: {message['type']}")#, message)

    async def send_initial_conversation_item(self, openai_ws):
        """Send initial conversation item if AI talks first."""
        initial_conversation_item = {
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Greet the user with 'Hello there! I am an AI voice assistant powered by Twilio and the OpenAI Realtime API. You can ask me for facts, jokes, or anything you can imagine. How can I help you?'"
                    }
                ]
            }
        }
        await openai_ws.send(json.dumps(initial_conversation_item))
        await openai_ws.send(json.dumps({"type": "response.create"}))


    async def initialize_session(self, openai_ws):
        """Control initial session with OpenAI."""
        session_update = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "pcm16",#"g711_ulaw",
                "output_audio_format": "pcm16",#"g711_ulaw",
                "voice": VOICE,
                "instructions": SYSTEM_MESSAGE,
                "modalities": ["text", "audio"],
                "temperature": 0.8,
            }
        }
        print('Sending session update:', json.dumps(session_update))
        await openai_ws.send(json.dumps(session_update))


class OpenAIVoiceObserver:
    def __init__(self):
        self.client = None
        self._audio_queue = Queue()
        self.audio = pyaudio.PyAudio()

    def register_client(self, client):
        self.client = client

    async def run(self, openai_ws):
        while True:
            chunk = await self._audio_queue.get()
            await self.play_chunk(chunk)

    async def play_chunk(self, chunk):
        # Save the chunk as a temporary audio file
        stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
        stream.write(chunk)
        stream.stop_stream()
        stream.close()


    async def update(self, message):
        if message.get('type') == 'response.audio.delta' and 'delta' in message:
            await self._audio_queue.put(base64.b64decode(message['delta']))