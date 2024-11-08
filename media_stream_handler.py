import asyncio
import base64
import json
from typing import Any, Optional

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from websockets import WebSocketClientProtocol

LOG_EVENT_TYPES: set[str] = {
    'error', 'response.content.done', 'rate_limits.updated',
    'response.done', 'input_audio_buffer.committed',
    'input_audio_buffer.speech_stopped', 'input_audio_buffer.speech_started',
    'session.created'
}


SHOW_TIMING_MATH = False


class MediaStreamConnection:
    """Connect OpenAI and Twilio web sockets.

    Connects an open OpenAI web socket and an active Twilio web socket with
    each other. Mostly just encapsulates Twilio example logic.
    """

    def __init__(self, twilio_peer: WebSocket, openai_peer: WebSocketClientProtocol, ai_voice: str, system_prompt: str) -> None:
        self.twilio_peer = twilio_peer
        self.openai_peer = openai_peer
        self.ai_voice = ai_voice
        self.system_prompt = system_prompt

        self.stream_sid = None
        self.latest_media_timestamp: int = 0
        self.last_assistant_item = None
        self.mark_queue: list[str] = []
        self.response_start_timestamp_twilio: Optional[int] = None

    async def handle(self) -> None:
        """Streams data from OpenAI and Twilio peers to each other.
        """

        await self.__initialize_openai_session()

        await asyncio.gather(self.__receive_from_twilio(), self.__send_to_twilio())

    async def __receive_from_twilio(self):
        """Receive audio data from Twilio and send it to the OpenAI Realtime API."""
        try:
            async for message in self.twilio_peer.iter_text():
                data = json.loads(message)
                if data['event'] == 'media' and self.openai_peer.open:
                    self.latest_media_timestamp = int(
                        data['media']['timestamp'])
                    audio_append: Any = {
                        "type": "input_audio_buffer.append",
                        "audio": data['media']['payload']
                    }
                    await self.openai_peer.send(json.dumps(audio_append))
                elif data['event'] == 'start':
                    self.stream_sid = data['start']['streamSid']
                    print(f"Incoming stream has started {self.stream_sid}")
                    self.response_start_timestamp_twilio = None
                    self.latest_media_timestamp = 0
                    self.last_assistant_item = None
                elif data['event'] == 'mark':
                    if self.mark_queue:
                        self.mark_queue.pop(0)
        except WebSocketDisconnect:
            print("Client disconnected.")
            if self.openai_peer.open:
                await self.openai_peer.close()

    async def __send_to_twilio(self):
        """Receive events from the OpenAI Realtime API, send audio back to Twilio."""
        try:
            async for openai_message in self.openai_peer:
                response = json.loads(openai_message)
                if response['type'] in LOG_EVENT_TYPES:
                    print(f"Received event: {response['type']}", response)

                if response.get('type') == 'response.audio.delta' and 'delta' in response:
                    audio_payload: str = base64.b64encode(
                        base64.b64decode(response['delta'])).decode('utf-8')
                    audio_delta: Any = {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": audio_payload
                        }
                    }
                    await self.twilio_peer.send_json(audio_delta)

                    if self.response_start_timestamp_twilio is None:
                        self.response_start_timestamp_twilio = self.latest_media_timestamp
                        if SHOW_TIMING_MATH:
                            print(f"Setting start timestamp for new response: {
                                  self.response_start_timestamp_twilio}ms")

                    # Update last_assistant_item safely
                    if response.get('item_id'):
                        self.last_assistant_item = response['item_id']

                    await self.__send_mark()

                # Trigger an interruption. Your use case might work better using `input_audio_buffer.speech_stopped`, or combining the two.
                if response.get('type') == 'input_audio_buffer.speech_started':
                    print("Speech started detected.")
                    if self.last_assistant_item:
                        print(f"Interrupting response with id: {
                              self.last_assistant_item}")
                        await self.__handle_speech_started_event()
        except Exception as e:
            print(f"Error in send_to_twilio: {e}")

    async def __handle_speech_started_event(self):
        """Handle interruption when the caller's speech starts."""
        print("Handling speech started event.")
        if self.mark_queue and self.response_start_timestamp_twilio is not None:
            elapsed_time: int = self.latest_media_timestamp - \
                self.response_start_timestamp_twilio
            if SHOW_TIMING_MATH:
                print(f"Calculating elapsed time for truncation: {
                      self.latest_media_timestamp} - {self.response_start_timestamp_twilio} = {elapsed_time}ms")

            if self.last_assistant_item:
                if SHOW_TIMING_MATH:
                    print(f"Truncating item with ID: {
                          self.last_assistant_item}, Truncated at: {elapsed_time}ms")

                truncate_event: Any = {
                    "type": "conversation.item.truncate",
                    "item_id": self.last_assistant_item,
                    "content_index": 0,
                    "audio_end_ms": elapsed_time
                }
                await self.openai_peer.send(json.dumps(truncate_event))

            await self.twilio_peer.send_json({
                "event": "clear",
                "streamSid": self.stream_sid
            })

            self.mark_queue.clear()
            self.last_assistant_item = None
            self.response_start_timestamp_twilio = None

    async def __send_mark(self):
        if self.stream_sid:
            mark_event: Any = {
                "event": "mark",
                "streamSid": self.stream_sid,
                "mark": {"name": "responsePart"}
            }
            await self.twilio_peer.send_json(mark_event)
            self.mark_queue.append('responsePart')

    async def __initialize_openai_session(self):
        """Control initial session with OpenAI."""
        session_update: Any = {
            "type": "session.update",
            "session": {
                "turn_detection": {"type": "server_vad"},
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "voice": self.ai_voice,
                "instructions": self.system_prompt,
                "modalities": ["text", "audio"],
                "temperature": 0.8,
            }
        }
        print('Sending session update:', json.dumps(session_update))
        await self.openai_peer.send(json.dumps(session_update))