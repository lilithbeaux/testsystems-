#!/usr/bin/env python3
"""
SMS → Emerge Integration (Working Version)
Read SMS VSA vectors from ZODB, store as Emerge objects
"""
import sys, pathlib, pickle, json, uuid
from datetime import datetime

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

# 2. Store each vector as EmergeFile
from emerge.core.client import Z0RPCClient as Client
from emerge.core.objects import EmergeFile
import dill

c = Client("localhost", "54242")

# Ensure directory
try:
    c.mkdir("/sms_vectors")
    print("Created /sms_vectors directory")
except:
    print("/sms_vectors already exists")

for key, vec_bytes in vectors.items():
    try:
        vec = pickle.loads(vec_bytes)
        meta = metadata.get(key, {})
        
        # Convert vector to JSON-serializable
        if hasattr(vec, 'tolist'):
            vec_data = vec.tolist()
        else:
            vec_data = list(vec)
        
        content = {
            "key": key,
            "vector_shape": vec.shape if hasattr(vec, 'shape') else len(vec),
            "metadata": meta,
            "vector_data": vec_data,
            "stored_at": datetime.now().isoformat()
        }
        
        # Create EmergeFile
        obj = EmergeFile(
            id=key,
            data=json.dumps(content),
            date=datetime.now().strftime("%b %d %Y %H:%M:%S"),
            name=key,
            path="/sms_vectors",
            perms="rw-r--r--",
            type="file",
            uuid=str(uuid.uuid4()),
            node="sms_integration",
            version=0
        )
        
        c.store(obj)
        print(f"  ✅ Stored: {key} (shape: {content['vector_shape']})")
    except Exception as e:
        print(f"  ❌ Failed {key}: {e}")

# 3. Verify
print("\nVerifying...")
result = c.list("/sms_vectors", 0, 0)
print(f"Emerge objects: {result}")

conn.close()
db.close()
fs.close()
print("Done!")
