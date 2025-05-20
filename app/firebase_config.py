import json
import os
import firebase_admin
from firebase_admin import credentials, storage
from dotenv import load_dotenv

load_dotenv()

raw = os.getenv("FIREBASE_CREDENTIALS")
if not raw:
    raise ValueError("FIREBASE_CREDENTIALS no está definido en .env o está vacío.")

# Eliminar comillas externas si existen
raw = raw.strip()
if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
    raw = raw[1:-1]

# Decodificar caracteres escapados
unescaped = raw.encode('utf-8').decode('unicode_escape')
firebase_credentials = json.loads(unescaped)

# Asegurarse de que la clave privada tenga saltos de línea correctos
firebase_credentials["private_key"] = firebase_credentials["private_key"].replace("\\n", "\n").strip()

storage_bucket = os.getenv("FIREBASE_STORAGE_BUCKET")
if not storage_bucket:
    raise ValueError("FIREBASE_STORAGE_BUCKET no está definido en .env o está vacío.")
storage_bucket = storage_bucket.strip()

# Inicializar Firebase solo una vez
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_credentials)
    firebase_admin.initialize_app(cred, {"storageBucket": storage_bucket})

bucket = storage.bucket()