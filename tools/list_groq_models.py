from groq import Groq
from dotenv import load_dotenv
import os
load_dotenv(".env")  # explicit path — avoids the heredoc AssertionError

c = Groq(api_key=os.environ["GROQ_API_KEY"])
for m in sorted(c.models.list().data, key=lambda x: x.id):
    print(f"  {m.id}")
