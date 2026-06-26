import asyncio
import aiohttp
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def main():
    chrono_token = os.getenv("CHRONO_API_KEY")
    circle_id = sys.argv[1] if len(sys.argv) > 1 else "567130959"
    url = f"https://api.chronogenesis.net/club_profile?circle_id={circle_id}"
    
    print(f"Loading environment from: {os.getcwd()}")
    print(f"CHRONO_API_KEY is: {chrono_token} (len={len(chrono_token) if chrono_token else 0})")
    
    headers = {
        "Authorization": f"{chrono_token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as response:
                print(f"Status: {response.status}")
                text = await response.text()
                print("Response:", text[:1000])
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
