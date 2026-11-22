import os
import pickle
import chromadb
from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook
from sentence_transformers import SentenceTransformer

# Paths for stored vector database and keyword search index
CHROMA_DIR = os.path.join("data", "chroma_db")
BM25_PATH = os.path.join("data", "bm25_index.pkl")
SOPS_DIR = os.path.join("data", "sops")

# Lightweight embedding model (~90 MB) safe for 8 GB RAM laptops
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


def extract_text_pages(filepath):
    """Extracts text along with page/sheet metadata from PDF, DOCX, or XLSX files."""
    ext = os.path.splitext(filepath)[1].lower()
    filename = os.path.basename(filepath)
    doc_id = filename.split("_")[0] if "_" in filename else os.path.splitext(filename)[0]
    extracted = []

    if ext == ".pdf":
        reader = PdfReader(filepath)
        for page_num, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                extracted.append({
                    "text": text,
                    "source": filename,
                    "doc_id": doc_id,
                    "page": page_num
                })

    elif ext == ".docx":
        doc = Document(filepath)
        full_text = "\n".join([p.text.strip() for p in doc.paragraphs if p.text.strip()])
        if full_text:
            extracted.append({
                "text": full_text,
                "source": filename,
                "doc_id": doc_id,
                "page": 1
            })

    elif ext == ".xlsx":
        wb = load_workbook(filepath, data_only=True)
        for sheet_idx, sheet_name in enumerate(wb.sheetnames, start=1):
            ws = wb[sheet_name]
            rows = []
            for row in ws.iter_rows(values_only=True):
                row_vals = [str(cell) for cell in row if cell is not None]
                if row_vals:
                    rows.append(" | ".join(row_vals))
            if rows:
                extracted.append({
                    "text": f"Sheet: {sheet_name}\n" + "\n".join(rows),
                    "source": filename,
                    "doc_id": doc_id,
                    "page": sheet_idx
                })

    return extracted


def chunk_text(text, chunk_size=500, overlap=80):
    """Splits long text into overlapping chunks so context is not lost at boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def ingest_directory(folder_path=SOPS_DIR):
    """Reads all supported files in folder_path and updates ChromaDB + BM25 index."""
    print("[1/4] Loading lightweight embedding model (all-MiniLM-L6-v2)...")
    embedder = SentenceTransformer(EMBED_MODEL_NAME)

    # Initialize persistent ChromaDB collection
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    # Reset collection on full re-index so duplicate chunks are never created
    try:
        client.delete_collection("pharma_docs")
    except Exception:
        pass
    collection = client.create_collection(name="pharma_docs")

    print(f"[2/4] Reading and chunking documents from '{folder_path}'...")
    all_chunks = []
    all_metadatas = []
    all_ids = []

    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if not os.path.isfile(fpath):
            continue
        pages = extract_text_pages(fpath)
        for item in pages:
            pieces = chunk_text(item["text"], chunk_size=500, overlap=80)
            for idx, piece in enumerate(pieces):
                chunk_id = f"{item['source']}_p{item['page']}_c{idx}"
                all_chunks.append(piece)
                all_metadatas.append({
                    "source": item["source"],
                    "doc_id": item["doc_id"],
                    "page": item["page"]
                })
                all_ids.append(chunk_id)

    if not all_chunks:
        print("[WARN] No text chunks found to index.")
        return 0

    print(f"[3/4] Generating vector embeddings and storing {len(all_chunks)} chunks in ChromaDB...")
    embeddings = embedder.encode(all_chunks, show_progress_bar=False).tolist()
    collection.add(
        documents=all_chunks,
        embeddings=embeddings,
        metadatas=all_metadatas,
        ids=all_ids
    )

    print("[4/4] Saving BM25 keyword corpus to disk...")
    bm25_payload = {
        "chunks": all_chunks,
        "metadatas": all_metadatas,
        "ids": all_ids
    }
    with open(BM25_PATH, "wb") as f:
        pickle.dump(bm25_payload, f)

    print(f"[OK] Indexed {len(all_chunks)} chunks across {len(os.listdir(folder_path))} documents!")
    return len(all_chunks)


if __name__ == "__main__":
    ingest_directory()