from __future__ import annotations
from typing import Iterable
import numpy as np


def tfidf_embeddings(texts: Iterable[str]):
    from sklearn.feature_extraction.text import TfidfVectorizer
    values = [str(text) for text in texts]
    if not values:
        return np.empty((0, 0)), None
    vectorizer = TfidfVectorizer(max_features=1024, ngram_range=(1, 2), min_df=1)
    return vectorizer.fit_transform(values).toarray(), vectorizer
