#!/usr/bin/env python3
"""
SMS → Emerge Integration (Final Working Version)
Read SMS VSA vectors using SMS venv, then store using system python3.13
"""
import sys, os, pathlib, pickle, json, uuid, subprocess
from datetime import datetime

# 1. Read SMS vectors using SMS venv python
venv_python = str(pathlib.Path.home() / '.NOTTHEONETOEDIT' / 'profiles' / 'thotheauphis' / 'memory' / 'sms' / 'venv' / 'bin' / 'python')
store_path = pathlib.Path.home() / '.NOTTHEONETOEDIT' / 'profiles' / 'thotheauphis' / 'memory' / 'store' / 'vsa_vectors.fs'

# Use venv python to extract vectors and save to temp JSON
extract_script = f'''
import sys, pathlib, pickle, json
sys.path.insert(0, str(pathlib.Path.home() / '.NOTTHEONETOEDIT' / 'profiles' / 'thotheauphis' / 'memory' / 'sms' / 'src'))
import ZODB, ZODB.FileStorage

store_path = pathlib.Path("{store_path}")
fs = ZODB.FileStorage.FileStorage(str(store_path))
db = ZODB.DB(fs)
conn = db.open()
root = conn.root()
vectors = root.get('vectors', {{}})
metadata = root.get('metadata', {{}})

result = {{}}
for key, vec_bytes in vectors.items():
    vec = pickle.loads(vec_bytes)
    meta = metadata.get(key, {{}})
    result[key] = {{
        "vector": vec.tolist() if hasattr(vec, 'tolist') else list(vec),
        "shape": vec.shape if hasattr(vec, 'shape') else len(vec),
        "metadata": meta
    }}

conn.close()
db.close()
fs.close()

with open("/tmp/sms_vectors.json", "w") as f:
    json.dump(result, f)
print(f"Extracted {{len(result)}} vectors")
'''

result = subprocess.run([venv_python, "-c", extract_script], capture_output=True, text=True)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])

# 2. Load extracted vectors and store to Emerge using system python
with open("/tmp/sms_vectors.json") as f:
    vectors = json.load(f)

print(f"Loaded {len(vectors)} vectors from temp file")

# 3. Store each vector using python3.13 (has emerge)
for key, data in vectors.items():
    content = {
        "key": key,
        "vector_shape": data["shape"],
        "metadata": data["metadata"],
        "vector_data": data["vector"],
        "stored_at": datetime.now().isoformat()
    }
    content_json = json.dumps(content)
    
    # Create EmergeFile via python3.13
    store_script = f'''
from emerge.core.client import Z0RPCClient as Client
from emerge.core.objects import EmergeFile
import json, uuid
from datetime import datetime

c = Client("localhost", "54242")

obj = EmergeFile(
    id="{key}",
    data={json.dumps(content_json)},
    date=datetime.now().strftime("%b %d %Y %H:%M:%S"),
    name="{key}",
    path="/sms_vectors",
    perms="rw-r--r--",
    type="file",
    uuid=str(uuid.uuid4()),
    node="sms_integration",
    version=0
)

c.store(obj)
print("Stored: {key}")
'''
    
    result = subprocess.run(["python3.13", "-c", store_script], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"  ✅ Stored: {key}")
    else:
        print(f"  ❌ Failed {key}: {result.stderr[:200]}")

# 4. Verify
verify_result = subprocess.run([
    "python3.13", "-c",
    "from emerge.core.client import Z0RPCClient as Client; c=Client('localhost','54242'); print(c.list('/sms_vectors', 0, 0))"
], capture_output=True, text=True)

print(f"\nVerifying... Emerge objects: {verify_result.stdout.strip()}")
print("Done!")
