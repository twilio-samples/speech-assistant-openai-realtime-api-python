import time
from typing import Any

import requests

BASE_URL: str = "https://link-to-service"


def phone_call(phone: str, intent_prompt: str) -> Any:
    response: requests.Response = requests.post(f"{BASE_URL}/call", json={
        "phone": phone,
        "intent_prompt": intent_prompt,
    })
    response.raise_for_status()

    call_id: str = response.text
    status_code: int = 202
    while status_code == 202:
        response = requests.get(f"{BASE_URL}/transcript/{call_id}")
        status_code = response.status_code
        time.sleep(5)
    return response.json()


if __name__ == "__main__":
    print(phone_call("+41764871981", "You are a friendly tax accountant calling someone in order to get their unique taxpayer ID, which they forgot to add in their form."))
