from dotenv import load_dotenv
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
load_dotenv(project_root / ".env")

from pymilvus import connections, Collection, utility

connections.connect(host='localhost', port='19530')
print("Collections:", utility.list_collections())

if utility.has_collection('kb_item_names'):
    col = Collection('kb_item_names')
    col.load()
    results = col.query(expr='', limit=10, output_fields=['*'])
    print('item_names count:', len(results))
    for r in results:
        print('  ', r)

if utility.has_collection('kb_chunks'):
    col = Collection('kb_chunks')
    col.load()
    print('chunks count:', col.num_entities)
    results = col.query(expr='', limit=3, output_fields=['item_name', 'text'])
    for r in results:
        print('  item_name:', r.get('item_name', 'N/A'))
        print('  text:', str(r.get('text', ''))[:150])
else:
    print('kb_chunks not found!')

connections.disconnect('default')
