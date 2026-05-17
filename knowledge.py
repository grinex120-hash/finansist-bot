import os
import hashlib
import chromadb
from gigachat import GigaChat
from config import GIGACHAT_KEY
import logging

logger = logging.getLogger(__name__)
giga_client = GigaChat(credentials=GIGACHAT_KEY, verify_ssl_certs=False)

CHROMA_DB_PATH = "./chroma_db"
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
collection = chroma_client.get_or_create_collection(name="finance_knowledge")

def get_gigachat_embedding(text: str):
    try:
        emb = giga_client.embeddings.create(input=text, model="Embeddings")
        return emb.data[0].embedding
    except:
        return [0.0] * 1024

def split_text_into_chunks(text: str, chunk_size=500, overlap=50):
    chunks, start = [], 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def index_documents():
    if not os.path.exists("knowledge_base"):
        logger.info("Папка knowledge_base не найдена")
        return
    files = [f for f in os.listdir("knowledge_base") if f.endswith(".txt")]
    if not files:
        logger.info("Нет .txt файлов")
        return
    for filename in files:
        path = os.path.join("knowledge_base", filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        chunks = split_text_into_chunks(content)
        for i, chunk in enumerate(chunks):
            cid = hashlib.md5(f"{filename}_{i}".encode()).hexdigest()
            if collection.get(ids=[cid])['ids']:
                continue
            emb = get_gigachat_embedding(chunk)
            collection.add(documents=[chunk], embeddings=[emb], metadatas=[{"source": filename}], ids=[cid])
    logger.info(f"Индексация завершена: {len(files)} файлов")

def search_knowledge(query, top_k=3):
    try:
        emb = get_gigachat_embedding(query)
        res = collection.query(query_embeddings=[emb], n_results=top_k)
        docs = res['documents'][0] if res['documents'] else []
        metas = res['metadatas'][0] if res['metadatas'] else []
        return list(zip(docs, metas))
    except:
        return []