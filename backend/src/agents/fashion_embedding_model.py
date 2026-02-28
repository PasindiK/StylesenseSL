"""
Fashion-Specific Embedding Model Wrapper
Uses pre-trained and fine-tuned embeddings optimized for fashion
"""
import numpy as np
from pathlib import Path
from typing import List, Dict
import logging
import json

logger = logging.getLogger(__name__)

class FashionEmbeddingModel:
    """
    Fashion-optimized embedding model with domain-specific enhancements
    Can use fine-tuned weights when available, falls back to base model
    """
    
    def __init__(self, model_type: str = "fashion-optimized"):
        """
        Initialize fashion embedding model
        
        Args:
            model_type: 'fashion-optimized' (our fine-tuned), 'base' (generic)
        """
        try:
            from sentence_transformers import SentenceTransformer
            
            self.model_type = model_type
            self.fashion_vocabulary = self._build_fashion_vocabulary()
            self.embedding_weights = self._load_or_create_weights()
            
            # Load base model at initialization (not lazy)
            if self.model_type == "fashion-optimized":
                # Try to load fine-tuned model
                ft_model_path = Path("models/fashion-embeddings-ft")
                if ft_model_path.exists():
                    logger.info("🎨 Loading fine-tuned fashion embedding model")
                    self.model = SentenceTransformer(str(ft_model_path))
                else:
                    logger.info("📚 Loading base model with fashion vocabulary boost")
                    self.model = SentenceTransformer("all-MiniLM-L6-v2")
            else:
                self.model = SentenceTransformer("all-MiniLM-L6-v2")
            
            logger.info(f"✅ Initialized {model_type} embedding model")
        except Exception as e:
            logger.error(f"Failed to initialize fashion embedding model: {e}")
            raise
        
    def _build_fashion_vocabulary(self) -> Dict[str, float]:
        """Build fashion-specific vocabulary with category weights"""
        return {
            # Categories (high weight)
            'dresses': 1.5, 'sarees': 1.5, 'shirt': 1.2, 'blouse': 1.2,
            'pants': 1.2, 'jeans': 1.2, 'jacket': 1.2, 'coat': 1.2,
            'cardigan': 1.1, 'sweater': 1.1, 'hoodies': 1.1, 'blazer': 1.2,
            'shorts': 1.2, 'skirt': 1.3, 'lehenga': 1.5, 'gown': 1.3,
            'trousers': 1.2, 'chinos': 1.2, 'joggers': 1.2, 'cargo': 1.2,
            'tanks': 1.1, 'polos': 1.1, 't-shirts': 1.1, 'tops': 1.1,
            
            # Colors (high weight)
            'blue': 1.3, 'black': 1.2, 'white': 1.2, 'red': 1.3, 'pink': 1.3,
            'green': 1.2, 'navy': 1.3, 'beige': 1.2, 'grey': 1.1, 'brown': 1.1,
            'gold': 1.3, 'silver': 1.3, 'floral': 1.2, 'striped': 1.2,
            'peach': 1.2, 'mustard': 1.2, 'camouflage': 1.1, 'tie-dye': 1.2,
            
            # Fit types (NEW - CRITICAL for "wide leg", "skinny" etc)
            'wide leg': 1.4, 'wide-leg': 1.4, 'wide': 1.3,
            'skinny': 1.3, 'slim': 1.3, 'slim fit': 1.3,
            'straight leg': 1.3, 'straight': 1.2,
            'boot cut': 1.3, 'bootcut': 1.3,
            'flare': 1.3, 'flared': 1.3,
            'tapered': 1.3, 'taper': 1.2,
            'oversized': 1.4, 'over-sized': 1.4,
            'fitted': 1.2, 'fit': 1.1,
            'loose': 1.2, 'relaxed': 1.3,
            
            # Styles & occasions (medium weight)
            'casual': 1.2, 'formal': 1.3, 'party': 1.3, 'wedding': 1.4,
            'beach': 1.3, 'beachwear': 1.3, 'beach wear': 1.3,
            'office': 1.2, 'sporty': 1.1, 'vintage': 1.2,
            'bohemian': 1.2, 'boho': 1.2, 'minimalist': 1.1, 'luxur': 1.3, 'eco': 1.1,
            'retro': 1.2, 'edgy': 1.2, 'preppy': 1.2, 'smart': 1.2,
            
            # Material (medium weight)
            'cotton': 1.1, 'silk': 1.2, 'wool': 1.1, 'linen': 1.1,
            'denim': 1.2, 'polyester': 0.9, 'leather': 1.2,
            
            # Personal attributes (medium weight)
            'petite': 1.1, 'tall': 1.1, 'curvy': 1.1, 'skinny': 1.0,
            'fair': 0.9, 'dark': 0.9, 'medium': 0.9,
            
            # Price/value (low weight)
            'affordable': 0.9, 'luxury': 1.2, 'budget': 0.8, 'premium': 1.2,
            
            # Modifiers (boost relevance)
            'trending': 1.5, 'bestseller': 1.4, 'new': 1.2, 'sale': 1.1,
            'popular': 1.3, 'exclusive': 1.3
        }
    
    def _load_or_create_weights(self) -> Dict:
        """Load pre-trained fashion weights or create defaults"""
        weights_path = Path("data/processed/fashion_embedding_weights.json")
        
        if weights_path.exists():
            with open(weights_path, 'r') as f:
                return json.load(f)
        else:
            # Create balanced weights
            return {
                'fashion_vocabulary_boost': 0.25,
                'semantic_relevance': 0.40,
                'user_preference_match': 0.20,
                'popularity_score': 0.15
            }
    
    def encode(self, texts: List[str], **kwargs):
        """
        Encode texts to embeddings using sentence transformer
        with fashion-specific enhancements
        
        Args:
            texts: List of text strings to encode
            **kwargs: Additional arguments passed to SentenceTransformer.encode()
                     (e.g., show_progress_bar, batch_size, etc.)
        """
        try:
            # Get base embeddings (pass through kwargs like show_progress_bar)
            embeddings = self.model.encode(texts, **kwargs)
            
            # Apply fashion-specific enhancements
            enhanced_embeddings = self._apply_fashion_boost(texts, embeddings)
            
            return enhanced_embeddings
            
        except Exception as e:
            logger.error(f"Error encoding texts: {e}")
            raise
            
            # Apply fashion-specific enhancements
            enhanced_embeddings = self._apply_fashion_boost(texts, embeddings)
            
            return enhanced_embeddings
            
        except Exception as e:
            logger.error(f"Error encoding texts: {e}")
            raise
    
    def _apply_fashion_boost(self, texts: List[str], embeddings: np.ndarray) -> np.ndarray:
        """Apply fashion-specific vocabulary boosting to embeddings"""
        
        if not isinstance(texts, list):
            texts = [texts]
        
        enhanced_embeddings = embeddings.copy() if isinstance(embeddings, np.ndarray) else np.array(embeddings)
        
        for i, text in enumerate(texts):
            text_lower = text.lower()
            
            # Calculate fashion vocabulary relevance boost
            boost_factor = 1.0
            for fashion_term, weight in self.fashion_vocabulary.items():
                if fashion_term in text_lower:
                    boost_factor += (weight - 1.0) * 0.05
            
            # Apply boost (up to 20% enhancement)
            boost_factor = min(boost_factor, 1.2)
            
            if isinstance(enhanced_embeddings[i], np.ndarray):
                enhanced_embeddings[i] = enhanced_embeddings[i] * boost_factor
        
        return enhanced_embeddings
    
    def similarity(self, embeddings1: np.ndarray, embeddings2: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity between embeddings"""
        from sklearn.metrics.pairwise import cosine_similarity
        return cosine_similarity(embeddings1, embeddings2)


def get_fashion_embedding_model(model_type: str = "fashion-optimized") -> FashionEmbeddingModel:
    """Factory function to get fashion embedding model"""
    return FashionEmbeddingModel(model_type=model_type)
