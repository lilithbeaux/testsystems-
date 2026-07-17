#!/usr/bin/env python3
"""
SMS → Emerge Integration
Read SMS VSA vectors from ZODB, store as Emerge objects
"""
import sys, os, pathlib, pickle, json, subprocess

# 1. Read SMS vectors from ZODB
import ZODB, ZODB.FileStorage
store_path = pathlib.Path.home() / '.NOTTHEONETOEDIT' / 'profiles' / 'thotheauphis' / 'memory' / 'store' / 'vsa_vectors.fs'
fs = ZODB.FileStorage.FileStorage(str(store_path))
db = ZODB.DB(fs)
conn = db.open()
root = conn.root()
vectors = root.get('vectors', {})
metadata = root.get('metadata', {})

print(f"Found {len(vectors)} VSA vectors in SMS store")

# 2. Create directory on Emerge
cmd = """python3.13 -c "
from emerge.core.client import Z0RPCClient as Client
c = Client('localhost', '54242')
try:
    c.mkdir('/sms_vectors')
    print('Created /sms_vectors directory')
except:
    print('/sms_vectors already exists')
"
"""
result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
print("STDOUT:", result.stdout.strip())
print("STDERR:", result.stderr.strip())

# 3. Store each vector
for key, vec_bytes in vectors.items():
    try:
        vec = pickle.loads(vec_bytes)
        meta = metadata.get(key, {})
        content = {
            "key": key,
            "vector_shape": vec.shape if hasattr(vec, 'shape') else len(vec),
            "metadata": meta,
            "vector_data": vec.tolist() if hasattr(vec, 'tolist') else list(vec)
        }
        content_json = json.dumps(content)
        cmd = f'''python3.13 -c "
from emerge.core.client import Z0RPCClient as Client
import json
c = Client('localhost', '54242')
c.store('/sms_vectors', '{key}', {json.dumps(content_json)})
print('Stored: {key}')
"'''
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✅ Stored: {key}")
        else:
            print(f"  ❌ Failed {key}: {result.stderr[:200]}")
    except Exception as e:
        print(f"  ❌ Failed {key}: {e}")

# 4. Verify
print("\nVerifying...")
result = subprocess.run("python3.13 -c \"from emerge.core.client import Z0RPCClient as Client; c=Client('localhost','54242'); print(c.list('/sms_vectors', 0, 0))\"", shell=True, capture_output=True, text=True)
print(f"Emerge objects: {result.stdout}")

conn.close()
db.close()
fs.close()
print("Done!")
