from mistralai.client import Mistral

key = input("Enter Mistral API key: ")

client = Mistral(api_key=key)

result = client.audio.voices.list(limit=10, offset=0)

print(f"Total voices: {result.total}")
for voice in result.items:
    print(f"  - {voice.name} ({voice.id})  languages={voice.languages}")

# Paginate through all voices
offset = 0
all_voices = []
while True:
    page = client.audio.voices.list(limit=10, offset=offset)
    all_voices.extend(page.items)
    if offset + len(page.items) >= page.total:
        break
    offset += len(page.items)
