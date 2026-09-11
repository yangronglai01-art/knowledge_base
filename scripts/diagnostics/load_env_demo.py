# knowledge_base/test/load_env.py

import os

from dotenv import load_dotenv

# 使用绝对路径加载 .env
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
load_dotenv(dotenv_path=env_path, override=True)

print(os.getenv("YOUR_KEY"))

print(os.path.dirname(__file__))
print(os.path.join(os.path.dirname(__file__), "../../.env"))
print(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env")))
