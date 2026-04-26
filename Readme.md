#  Speech Assistant with Twilio Voice and the Gemini Live API (Python)

This application demonstrates how to use Python, [Twilio Voice](https://www.twilio.com/docs/voice) and [Media Streams](https://www.twilio.com/docs/voice/media-streams), and [Google's Gemini Live API](https://ai.google.dev/gemini-api/docs/live) to make a phone call to speak with an AI Assistant.

The application opens websockets with the Gemini Live API and Twilio, and sends voice audio from one to the other to enable a two-way conversation.

This application uses the following Twilio products in conjunction with the Gemini Live API:
- Voice (and TwiML, Media Streams)
- Phone Numbers

> [!NOTE]
> Outbound calling is beyond the scope of this app.

## Prerequisites

To use the app, you will  need:

- **Python 3.9+** (3.11 or earlier recommended; `audioop` is removed in 3.13+). Download from [here](https://www.python.org/downloads/).
- **A Twilio account.** You can sign up for a free trial [here](https://www.twilio.com/try-twilio).
- **A Twilio number with _Voice_ capabilities.** [Here are instructions](https://help.twilio.com/articles/223135247-How-to-Search-for-and-Buy-a-Twilio-Phone-Number-from-Console) to purchase a phone number.
- **A Google AI Studio account and a Gemini API Key.** You can get one [here](https://aistudio.google.com/apikey).

## Local Setup

There are 4 required steps and 1 optional step to get the app up-and-running locally for development and testing:
1. Run ngrok or another tunneling solution to expose your local server to the internet for testing. Download ngrok [here](https://ngrok.com/).
2. (optional) Create and use a virtual environment
3. Install the packages
4. Twilio setup
5. Update the .env file

### Open an ngrok tunnel
When developing & testing locally, you'll need to open a tunnel to forward requests to your local development server. These instructions use ngrok.

Open a Terminal and run:
```
ngrok http 5050
```
Once the tunnel has been opened, copy the `Forwarding` URL. It will look something like: `https://[your-ngrok-subdomain].ngrok.app`. You will
need this when configuring your Twilio number setup.

Note that the `ngrok` command above forwards to a development server running on port `5050`, which is the default port configured in this application. If
you override the `PORT` defined in `main.py`, you will need to update the `ngrok` command accordingly.

Keep in mind that each time you run the `ngrok http` command, a new URL will be created, and you'll need to update it everywhere it is referenced below.

### (Optional) Create and use a virtual environment

To reduce cluttering your global Python environment on your machine, you can create a virtual environment. On your command line, enter:

```
python3 -m venv env
source env/bin/activate
```

### Install required packages

In the terminal (with the virtual environment, if you set it up) run:
```
pip install -r requirements.txt
```

### Twilio setup

#### Point a Phone Number to your ngrok URL
In the [Twilio Console](https://console.twilio.com/), go to **Phone Numbers** > **Manage** > **Active Numbers** and click on the additional phone number you purchased for this app in the **Prerequisites**.

In your Phone Number configuration settings, update the first **A call comes in** dropdown to **Webhook**, and paste your ngrok forwarding URL (referenced above), followed by `/incoming-call`. For example, `https://[your-ngrok-subdomain].ngrok.app/incoming-call`. Then, click **Save configuration**.

### Update the .env file

Create a `.env` file, or copy the `.env.example` file to `.env`:

```
cp .env.example .env
```

In the .env file, update the `GEMINI_API_KEY` to your Gemini API key from the **Prerequisites**.

## Run the app
Once ngrok is running, dependencies are installed, Twilio is configured properly, and the `.env` is set up, run the dev server with the following command:
```
python main.py
```
## Test the app
With the development server running, call the phone number you purchased in the **Prerequisites**. After the introduction, you should be able to talk to the AI Assistant. Have fun!

## Audio Pipeline

Twilio sends PCMU (G.711 μ-law, 8kHz) audio. Gemini Live expects raw PCM (16-bit, little-endian, 16kHz). The server handles transcoding:

- **Twilio → Gemini**: PCMU 8kHz → `audioop.ulaw2lin` → PCM 8kHz → `audioop.ratecv` (upsample 8→16kHz) → Gemini
- **Gemini → Twilio**: PCM 24kHz → struct averaging (downsample 24→8kHz) → `audioop.lin2ulaw` → PCMU → Twilio

## Interrupt handling / Barge-in

Gemini Live handles barge-in natively with server-side VAD. When the user speaks during an AI response, Gemini sends `serverContent.interrupted: true`. The server then clears Twilio's audio buffer so the caller stops hearing the old response immediately. No manual truncation messages needed.
