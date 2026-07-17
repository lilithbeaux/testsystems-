#!/usr/bin/env python3
"""
SMS → Emerge Integration (Final)
Read SMS VSA vectors from ZODB, store as Emerge objects
"""
import sys, os, pathlib, pickle, json, subprocess, tempfile

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

# Helper to convert numpy types to native Python
def to_native(obj):
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    elif hasattr(obj, 'item'):
        return obj.item()
    elif isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_native(v) for v in obj]
    elif hasattr(obj, '__array__'):  # numpy array
        return to_native(obj.__array__())
    return obj

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
subprocess.run(cmd, shell=True, capture_output=True, text=True)

# 3. Store each vector
for key, vec_bytes in vectors.items():
    try:
        vec = pickle.loads(vec_bytes)
        meta = metadata.get(key, {})
        
        # Convert everything to native Python
        content = {
            "key": key,
            "vector_shape": to_native(vec.shape) if hasattr(vec, 'shape') else len(vec),
            "metadata": to_native(meta),
            "vector_data": to_native(vec)
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(f'''#!/usr/bin/env python3
from emerge.core.client import Z0RPCClient as Client
import json
c = Client('localhost', '54242')
content = {json.dumps(content)}
c.store('/sms_vectors', '{key}', json.dumps(content))
print('Stored: {key}')
''')
            temp_path = f.name
        
        result = subprocess.run(['python3.13', temp_path], capture_output=True, text=True)
        os.unlink(temp_path)
        
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
