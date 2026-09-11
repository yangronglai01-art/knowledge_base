
from pathlib import Path

from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[2]
load_dotenv(project_root / ".env")
from pymilvus import connections, utility
connections.connect(host='localhost', port='19530')
for c in ['kb_chunks', 'kb_item_names']:
    if utility.has_collection(c):
        utility.drop_collection(c)
        print(f"Dropped {c}")
connections.disconnect('default')
