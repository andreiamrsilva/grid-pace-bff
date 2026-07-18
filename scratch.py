import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("TWITTER_API_IO_KEY")

url = "https://api.twitterapi.io/twitter/user/info?userName=OfficialWRC"
req = urllib.request.Request(url, headers={"X-API-Key": key})
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print("Error:", e)
