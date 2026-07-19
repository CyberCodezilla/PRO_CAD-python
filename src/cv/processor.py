"""
CV Processor - OpenCV-based preprocessing and feature extraction
"""
import cv2
import numpy as np
from typing import List, Tuple, Dict, Any

class CVProcessor:
    """Computer vision processing for shape analysis"""
    
    def __init__(self):
        self.edge_threshold1 = 50
        self.edge_threshold2 = 150
        
    def preprocess_shapes(self, shapes: List[Dict[str, Any]], image_size: Tuple[int, int] = (800, 600)) -> np.ndarray:
        """Convert shapes to binary image for CV processing"""
        # Create blank canvas
        canvas = np.zeros(image_size, dtype=np.uint8)
        
        for shape in shapes:
            self._draw_shape_on_canvas(canvas, shape)
            
        return canvas
        
    def _draw_shape_on_canvas(self, canvas: np.ndarray, shape: Dict[str, Any]):
        """Draw a shape on OpenCV canvas"""
        shape_type = shape.get('type')
        color = 255  # White for shapes
        thickness = 2
        
        if shape_type == 'line':
            p1 = tuple(map(int, shape['start']))
            p2 = tuple(map(int, shape['end']))
            cv2.line(canvas, p1, p2, color, thickness)
            
        elif shape_type == 'circle':
            center = tuple(map(int, shape['center']))
            radius = int(shape['radius'])
            cv2.circle(canvas, center, radius, color, thickness)
            
        elif shape_type == 'rectangle':
            x, y, w, h = map(int, shape['rect'])
            cv2.rectangle(canvas, (x, y), (x+w, y+h), color, thickness)
            
        elif shape_type == 'polygon':
            points = np.array(shape['points'], dtype=np.int32)
            cv2.polylines(canvas, [points], True, color, thickness)
            
    def extract_edges(self, image: np.ndarray) -> np.ndarray:
        """Extract edges using Canny edge detection"""
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
        # Apply Gaussian blur
        blurred = cv2.GaussianBlur(image, (5, 5), 0)
        
        # Canny edge detection
        edges = cv2.Canny(blurred, self.edge_threshold1, self.edge_threshold2)
        
        return edges
        
    def extract_contours(self, image: np.ndarray) -> List[np.ndarray]:
        """Extract contours from binary image"""
        contours, _ = cv2.findContours(
            image,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        return contours
        
    def extract_silhouette(self, shapes: List[Dict[str, Any]], image_size: Tuple[int, int] = (800, 600)) -> np.ndarray:
        """Extract silhouette representation of shapes"""
        # Create canvas
        canvas = self.preprocess_shapes(shapes, image_size)
        
        # Fill interior
        filled = canvas.copy()
        contours = self.extract_contours(canvas)
        cv2.drawContours(filled, contours, -1, 255, -1)  # Fill all contours
        
        return filled
        
    def compute_shape_descriptors(self, contour: np.ndarray) -> Dict[str, Any]:
        """Compute shape descriptors for feature matching"""
        # Area
        area = cv2.contourArea(contour)
        
        # Perimeter
        perimeter = cv2.arcLength(contour, True)
        
        # Bounding box
        x, y, w, h = cv2.boundingRect(contour)
        
        # Moments
        M = cv2.moments(contour)
        if M['m00'] != 0:
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
        else:
            cx, cy = 0, 0
            
        # Aspect ratio
        aspect_ratio = float(w) / h if h != 0 else 0
        
        # Extent (area / bounding box area)
        extent = float(area) / (w * h) if w * h != 0 else 0
        
        # Solidity (area / convex hull area)
        hull = cv2.convexHull(contour)
        hull_area = cv2.contourArea(hull)
        solidity = float(area) / hull_area if hull_area != 0 else 0
        
        # Circularity
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter != 0 else 0
        
        return {
            'area': area,
            'perimeter': perimeter,
            'centroid': (cx, cy),
            'bounding_box': (x, y, w, h),
            'aspect_ratio': aspect_ratio,
            'extent': extent,
            'solidity': solidity,
            'circularity': circularity
        }
        
    def match_features_across_views(
        self,
        top_shapes: List[Dict[str, Any]],
        front_shapes: List[Dict[str, Any]],
        side_shapes: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find feature correspondences across orthographic views"""
        correspondences = []
        
        # Convert shapes to contours
        top_contours = self._shapes_to_contours(top_shapes)
        front_contours = self._shapes_to_contours(front_shapes)
        side_contours = self._shapes_to_contours(side_shapes)
        
        # Compute descriptors
        top_descriptors = [self.compute_shape_descriptors(c) for c in top_contours]
        front_descriptors = [self.compute_shape_descriptors(c) for c in front_contours]
        side_descriptors = [self.compute_shape_descriptors(c) for c in side_contours]
        
        # Match features based on descriptors
        for i, top_desc in enumerate(top_descriptors):
            best_matches = {
                'top_index': i,
                'top_descriptor': top_desc,
                'front_match': None,
                'side_match': None
            }
            
            # Find best front match
            if front_descriptors:
                front_scores = [
                    self._compute_descriptor_similarity(top_desc, f_desc)
                    for f_desc in front_descriptors
                ]
                best_front_idx = np.argmax(front_scores)
                if front_scores[best_front_idx] > 0.5:  # Threshold
                    best_matches['front_match'] = {
                        'index': best_front_idx,
                        'descriptor': front_descriptors[best_front_idx],
                        'score': front_scores[best_front_idx]
                    }
                    
            # Find best side match
            if side_descriptors:
                side_scores = [
                    self._compute_descriptor_similarity(top_desc, s_desc)
                    for s_desc in side_descriptors
                ]
                best_side_idx = np.argmax(side_scores)
                if side_scores[best_side_idx] > 0.5:  # Threshold
                    best_matches['side_match'] = {
                        'index': best_side_idx,
                        'descriptor': side_descriptors[best_side_idx],
                        'score': side_scores[best_side_idx]
                    }
                    
            correspondences.append(best_matches)
            
        return correspondences
        
    def _shapes_to_contours(self, shapes: List[Dict[str, Any]]) -> List[np.ndarray]:
        """Convert shapes to OpenCV contours"""
        canvas = self.preprocess_shapes(shapes)
        contours = self.extract_contours(canvas)
        return contours
        
    def _compute_descriptor_similarity(self, desc1: Dict[str, Any], desc2: Dict[str, Any]) -> float:
        """Compute similarity between two shape descriptors"""
        # Normalize features
        features = ['aspect_ratio', 'extent', 'solidity', 'circularity']
        
        similarity = 0.0
        for feat in features:
            v1 = desc1.get(feat, 0)
            v2 = desc2.get(feat, 0)
            
            # Compute normalized difference
            max_val = max(abs(v1), abs(v2), 1e-6)
            diff = abs(v1 - v2) / max_val
            similarity += (1.0 - diff)
            
        return similarity / len(features)
