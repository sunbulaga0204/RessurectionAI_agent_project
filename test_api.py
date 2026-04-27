import requests

data = {
    "query": "Who are you?",
    "system_prompt": "You are a test.",
    "death_date_ah": "505"
}

resp = requests.post("http://127.0.0.1:8000/api/v1/ghazali/chat", json=data)
print(resp.status_code)
print(resp.text)
