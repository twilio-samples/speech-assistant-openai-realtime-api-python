import json
import websockets
import asyncio

class OpenAIRealtimeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.observers = []
        self.openai_ws = None

    def register(self, observer):
        observer.register_client(self)
        self.observers.append(observer)

    async def notify_observers(self, message):
        for observer in self.observers:
            await observer.update(message)

    async def _read_from_client(self, openai_ws):
        try:
            async for openai_message in openai_ws:
                response = json.loads(openai_message)
                await self.notify_observers(response)
        except Exception as e:
            print(f"Error in _read_from_client: {e}")

    async def run_openai_client(self):
        async with websockets.connect(
        'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01',
        extra_headers={
                "Authorization": f"Bearer {self.api_key}",
                "OpenAI-Beta": "realtime=v1"
            }
        ) as openai_ws:
            self.openai_ws = openai_ws
            await asyncio.gather(self._read_from_client(openai_ws), *[observer.run(openai_ws) for observer in self.observers])