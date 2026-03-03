"""
Semantic matching using sentence-transformers.
Embeds resume and job descriptions, computes cosine similarity.
Much more powerful than keyword matching — understands meaning.
"""
import numpy as np
from typing import Optional

# Lazy-load the model to avoid slow import at startup
_model = None
_resume_embedding = None


def _get_model():
    """Lazy-load sentence-transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # all-MiniLM-L6-v2: fast, good quality, 384 dimensions
            # Runs locally — no API key needed
            _model = SentenceTransformer('all-MiniLM-L6-v2')
        except ImportError:
            print("[WARNING] sentence-transformers not installed. Using keyword matching only.")
            return None
    return _model


def get_resume_embedding():
    """Get cached embedding of Cynthia's resume."""
    global _resume_embedding
    if _resume_embedding is None:
        model = _get_model()
        if model is None:
            return None
        from profile import RESUME_TEXT
        _resume_embedding = model.encode(RESUME_TEXT, normalize_embeddings=True)
    return _resume_embedding


def compute_semantic_similarity(job_description: str) -> float:
    """
    Compute semantic similarity between resume and job description.
    Returns a score 0-100.
    """
    model = _get_model()
    if model is None:
        return 50.0  # Neutral fallback

    resume_emb = get_resume_embedding()
    if resume_emb is None:
        return 50.0

    # Encode the job description
    job_emb = model.encode(job_description, normalize_embeddings=True)

    # Cosine similarity (already normalized, so dot product = cosine sim)
    similarity = float(np.dot(resume_emb, job_emb))

    # Map from cosine similarity range to 0-100 score
    # Typical range for job matching: 0.2 (poor) to 0.7 (excellent)
    # Map: < 0.25 → 0-20, 0.25-0.40 → 20-50, 0.40-0.55 → 50-75, 0.55+ → 75-100
    if similarity < 0.20:
        return max(0, similarity * 50)
    elif similarity < 0.35:
        return 20 + (similarity - 0.20) * (30 / 0.15)
    elif similarity < 0.50:
        return 50 + (similarity - 0.35) * (25 / 0.15)
    else:
        return min(100, 75 + (similarity - 0.50) * (25 / 0.20))


def compute_title_similarity(job_title: str) -> float:
    """
    Compute semantic similarity between target roles and a job title.
    Returns 0-100.
    """
    model = _get_model()
    if model is None:
        return 50.0

    from config import TARGET_JOB_TITLES

    # Encode the job title
    job_title_emb = model.encode(job_title, normalize_embeddings=True)

    # Compute similarity against each target title, take the best match
    best_sim = 0.0
    for target in TARGET_JOB_TITLES:
        target_emb = model.encode(target, normalize_embeddings=True)
        sim = float(np.dot(job_title_emb, target_emb))
        best_sim = max(best_sim, sim)

    # Map similarity to score
    # Title matching should be stricter: 0.5+ is good, 0.7+ is great
    if best_sim < 0.4:
        return max(0, best_sim * 50)
    elif best_sim < 0.6:
        return 20 + (best_sim - 0.4) * (40 / 0.2)
    elif best_sim < 0.8:
        return 60 + (best_sim - 0.6) * (30 / 0.2)
    else:
        return min(100, 90 + (best_sim - 0.8) * (10 / 0.2))


def batch_compute_similarities(job_descriptions: list) -> list:
    """
    Efficiently compute similarities for a batch of job descriptions.
    Returns list of scores 0-100.
    """
    model = _get_model()
    if model is None:
        return [50.0] * len(job_descriptions)

    resume_emb = get_resume_embedding()
    if resume_emb is None:
        return [50.0] * len(job_descriptions)

    # Batch encode all descriptions
    job_embs = model.encode(job_descriptions, normalize_embeddings=True,
                            batch_size=32, show_progress_bar=False)

    scores = []
    for job_emb in job_embs:
        similarity = float(np.dot(resume_emb, job_emb))
        if similarity < 0.20:
            score = max(0, similarity * 50)
        elif similarity < 0.35:
            score = 20 + (similarity - 0.20) * (30 / 0.15)
        elif similarity < 0.50:
            score = 50 + (similarity - 0.35) * (25 / 0.15)
        else:
            score = min(100, 75 + (similarity - 0.50) * (25 / 0.20))
        scores.append(score)

    return scores
