"""Deduplication and canonical hashing for Maths Maharathi.

Provides:
- Exact canonical hashing (SHA-256 on normalized text + sorted options)
- SimHash / token shingles for near-duplicate question detection
- Safe comparison without external heavy dependencies, with embedding hooks
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Set, Tuple

from schemas.models import Question


def normalize_math_text(text: str) -> str:
    """Normalizes text by lowercasing, stripping punctuation, and standardizing math operators."""
    t = text.lower()
    t = t.replace("×", "*").replace("÷", "/").replace("−", "-").replace("—", "-")
    # Replace non-alphanumeric except basic math symbols
    t = re.sub(r"[^\w\s\+\-\*\/\%\=\.\^]", " ", t)
    # Collapse multiple whitespaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def get_token_shingles(text: str, k: int = 2) -> Set[str]:
    """Generates k-shingle tokens for n-gram overlap."""
    words = normalize_math_text(text).split()
    if len(words) < k:
        return set(words)
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculates Jaccard similarity coefficient between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return float(intersection) / float(union) if union > 0 else 0.0


def compute_simhash_64(text: str) -> int:
    """Computes a 64-bit SimHash fingerprint for near-duplicate detection."""
    tokens = normalize_math_text(text).split()
    if not tokens:
        return 0
    v = [0] * 64
    for token in tokens:
        # 64-bit MD5 digest slice
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(64):
            bit = (h >> i) & 1
            v[i] += 1 if bit == 1 else -1
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """Calculates Hamming distance between two 64-bit integer hashes."""
    x = hash1 ^ hash2
    return bin(x).count("1")


class DedupeEngine:
    """Deduplication engine managing question pools and collision detection."""

    def __init__(self, exact_pool: Optional[Set[str]] = None, near_pool: Optional[List[Question]] = None):
        self.exact_hashes: Set[str] = exact_pool or set()
        self.questions_pool: List[Question] = near_pool or []

    def check_duplicate(
        self,
        candidate: Question,
        similarity_threshold: float = 0.85,
    ) -> Tuple[bool, Optional[str], float]:
        """Checks if a question is an exact or near duplicate.
        
        Returns:
            (is_duplicate, duplicate_question_id, score)
        """
        c_hash = candidate.calculate_dedupe_hash()
        if c_hash in self.exact_hashes:
            return True, "EXACT_HASH_MATCH", 1.0

        c_shingles = get_token_shingles(candidate.text_en, k=2)
        c_simhash = compute_simhash_64(candidate.text_en)

        for existing in self.questions_pool:
            if existing.id == candidate.id:
                continue
            e_hash = existing.dedupe_hash or existing.calculate_dedupe_hash()
            if e_hash == c_hash:
                return True, existing.id, 1.0

            # Near duplicate check via SimHash & Jaccard shingles
            e_simhash = compute_simhash_64(existing.text_en)
            dist = hamming_distance(c_simhash, e_simhash)
            
            # Less than 4 bit difference in 64-bit SimHash suggests high similarity
            if dist <= 3:
                e_shingles = get_token_shingles(existing.text_en, k=2)
                sim = jaccard_similarity(c_shingles, e_shingles)
                if sim >= similarity_threshold:
                    return True, existing.id, round(sim, 3)

        return False, None, 0.0

    def register(self, question: Question) -> None:
        """Adds a question to the dedupe registry."""
        h = question.dedupe_hash or question.calculate_dedupe_hash()
        question.dedupe_hash = h
        self.exact_hashes.add(h)
        self.questions_pool.append(question)
