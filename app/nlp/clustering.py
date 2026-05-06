from typing import List
import logging

import numpy as np
from sklearn.cluster import KMeans

from app.db.session import SessionLocal
from app.db.models import EventRecord, EventEmbedding
from app.nlp.embeddings import embed_text

logger = logging.getLogger(__name__)


def compute_and_store_embeddings(limit: int = 500) -> int:
    """Compute embeddings for recent events and store/update EventEmbedding rows."""
    stored = 0
    with SessionLocal() as db:
        records = db.query(EventRecord).order_by(EventRecord.timestamp.desc()).limit(limit).all()
        for rec in records:
            emb = embed_text(rec.summary or rec.text)
            if not emb:
                continue
            # upsert simple: insert new row
            ee = EventEmbedding(event_id=rec.id, embedding={"vector": emb})
            db.add(ee)
            stored += 1
        db.commit()
    return stored


def run_kmeans(n_clusters: int = 8) -> int:
    """Run KMeans on stored embeddings and update cluster_id on EventEmbedding."""
    with SessionLocal() as db:
        rows = db.query(EventEmbedding).all()
        vectors = []
        ids = []
        for r in rows:
            vec = r.embedding.get("vector") if isinstance(r.embedding, dict) else None
            if vec:
                vectors.append(vec)
                ids.append(r.id)

        if not vectors:
            return 0

        X = np.array(vectors)
        kmeans = KMeans(n_clusters=n_clusters, random_state=42).fit(X)
        labels = kmeans.labels_

        for idx, label in zip(ids, labels):
            db.query(EventEmbedding).filter(EventEmbedding.id == idx).update({"cluster_id": str(int(label))})
        db.commit()
        return int(len(labels))
