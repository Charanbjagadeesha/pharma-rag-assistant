import os
import pickle
import chromadb
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

# Paths to saved vector store and BM25 keyword file
CHROMA_DIR = os.path.join("data", "chroma_db")
BM25_PATH = os.path.join("data", "bm25_index.pkl")

# Lightweight models (~90 MB + ~85 MB) safe for 8 GB RAM
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
RERANK_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class HybridRetriever:
    """Combines ChromaDB Vector Search + BM25 Keyword Search + Cross-Encoder Reranking."""

    def __init__(self):
        # Load embedding model and Cross-Encoder reranker once into memory
        self.embedder = SentenceTransformer(EMBED_MODEL_NAME)
        self.reranker = CrossEncoder(RERANK_MODEL_NAME)

        # Connect to persistent ChromaDB collection
        self.client = chromadb.PersistentClient(path=CHROMA_DIR)
        self.collection = self.client.get_or_create_collection(name="pharma_docs")

        # Load BM25 tokenized corpus from disk
        with open(BM25_PATH, "rb") as f:
            payload = pickle.load(f)
        self.chunks = payload["chunks"]
        self.metadatas = payload["metadatas"]
        self.ids = payload["ids"]

        # Tokenize chunks into lowercase words for BM25 keyword scoring
        tokenized_corpus = [doc.lower().split() for doc in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

    def retrieve(self, query: str, top_k: int = 3):
        """Runs hybrid search (Vector + BM25), merges via RRF, and reranks top results."""
        if not self.chunks:
            return []

        candidate_limit = min(6, len(self.chunks))

        # 1. Semantic Vector Search via ChromaDB
        query_vec = self.embedder.encode([query], show_progress_bar=False).tolist()
        vec_res = self.collection.query(
            query_embeddings=query_vec,
            n_results=candidate_limit
        )
        vec_ids = vec_res["ids"][0] if vec_res["ids"] else []

        # 2. Exact Keyword Search via BM25
        tokenized_query = query.lower().split()
        bm25_scores = self.bm25.get_scores(tokenized_query)
        ranked_indices = sorted(
            range(len(bm25_scores)),
            key=lambda i: bm25_scores[i],
            reverse=True
        )[:candidate_limit]
        bm25_ids = [self.ids[i] for i in ranked_indices if bm25_scores[i] > 0]

        # 3. Reciprocal Rank Fusion (RRF) to merge vector and keyword rankings
        rrf_scores = {}
        k_constant = 60
        for rank, doc_id in enumerate(vec_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k_constant + rank + 1)
        for rank, doc_id in enumerate(bm25_ids):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + 1.0 / (k_constant + rank + 1)

        # Map doc_id back to text and metadata
        id_to_idx = {doc_id: i for i, doc_id in enumerate(self.ids)}
        merged_candidates = []
        for doc_id in sorted(rrf_scores, key=rrf_scores.get, reverse=True)[:candidate_limit]:
            idx = id_to_idx[doc_id]
            merged_candidates.append({
                "id": doc_id,
                "text": self.chunks[idx],
                "metadata": self.metadatas[idx],
                "rrf_score": round(rrf_scores[doc_id], 4)
            })

        if not merged_candidates:
            return []

        # 4. Cross-Encoder Reranking to score exact (query, passage) relevance
        pairs = [[query, c["text"]] for c in merged_candidates]
        rerank_scores = self.reranker.predict(pairs)
        for candidate, score in zip(merged_candidates, rerank_scores):
            candidate["rerank_score"] = round(float(score), 4)

        # Sort by highest rerank_score and return top_k passages
        final_results = sorted(
            merged_candidates,
            key=lambda x: x["rerank_score"],
            reverse=True
        )[:top_k]
        return final_results


# Quick standalone test when running 'python app\retriever.py'
if __name__ == "__main__":
    retriever = HybridRetriever()
    sample_q = "What is the dirty equipment hold time for TC-04?"
    hits = retriever.retrieve(sample_q, top_k=3)
    print(f"\nQuery: {sample_q}\n")
    for rank, h in enumerate(hits, start=1):
        meta = h["metadata"]
        print(f"#{rank} [{meta['source']} | Page {meta['page']} | Score: {h['rerank_score']}]")
        print(f"   {h['text'][:160]}...\n")