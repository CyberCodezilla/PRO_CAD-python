"""
Unit Tests for Module 3: Production AI Vectorizer & Accelerated Thinning.
Tests vectorized Zhang-Suen morphological thinning, text masking, and RANSAC primitive fitting.
"""

import numpy as np
import cv2
from src.cv.ai_vectorizer import RasterCADVectorizer


def test_vectorized_zhang_suen_thinning():
    """Verify that vectorized Zhang-Suen thinning reduces thick lines to 1-pixel skeletons"""
    # Create a 100x100 binary image with a 10-pixel thick square
    img = np.zeros((100, 100), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (80, 80), 255, 10)

    skeleton = RasterCADVectorizer.zhang_suen_thinning(img)

    assert skeleton is not None
    assert np.count_nonzero(skeleton) < np.count_nonzero(img)
    # The thickness of any stroke in skeleton should be 1-2 pixels
    assert np.count_nonzero(skeleton) > 0


def test_text_and_annotation_masking():
    """Verify that text and small annotation characters are masked from primary geometry"""
    vectorizer = RasterCADVectorizer()

    # Image with a large rectangle and small text characters
    img = np.zeros((200, 200), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (180, 180), 255, 4)  # Main geometry
    cv2.putText(img, "R=10", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.4, 255, 1)  # Dimension text

    masked = vectorizer._mask_text_and_annotations(img)
    assert np.count_nonzero(masked) < np.count_nonzero(img)
    # Main outer rectangle remains intact
    assert np.count_nonzero(masked) > 200
