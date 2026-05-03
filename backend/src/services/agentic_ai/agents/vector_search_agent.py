"""Vector Search Agent using sentence embeddings for semantic product search."""
import logging
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
import os
import hashlib
from pathlib import Path

try:
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    cosine_similarity = None  # type: ignore[assignment]

try:
    from sentence_transformers import SentenceTransformer

    VECTOR_SEARCH_AVAILABLE = True
except (ImportError, OSError, RuntimeError):
    # OSError: common on Windows when torch DLLs fail to load (c10.dll).
    SentenceTransformer = None  # type: ignore[misc,assignment]
    VECTOR_SEARCH_AVAILABLE = False

logger = logging.getLogger(__name__)

# Fashion model imports (optional enhancement)
try:
    from src.services.agentic_ai.agents.fashion_embedding_model import get_fashion_embedding_model
    FASHION_MODEL_AVAILABLE = True
except ImportError:
    FASHION_MODEL_AVAILABLE = False


class VectorSearchAgent:
    """Semantic product search using sentence embeddings and scikit-learn."""
    
    CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "embeddings_cache"
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', use_fashion_model: bool = False):
        """Initialize vector search agent.
        
        Args:
            model_name: Sentence transformer model (default: all-MiniLM-L6-v2)
                       - Fast and good quality
                       - 384 dimensions
                       - Works offline
            use_fashion_model: Use fashion-optimized embeddings (experimental)
        """
        # Ensure cache directory exists
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self.use_fashion_model = use_fashion_model and FASHION_MODEL_AVAILABLE
        
        if not VECTOR_SEARCH_AVAILABLE:
            logger.warning("Vector search dependencies not installed. Install: pip install sentence-transformers scikit-learn")
            self.enabled = False
            return
        
        try:
            # Initialize embedding model
            if self.use_fashion_model:
                logger.info("🎨 Using FASHION-OPTIMIZED embeddings with vocabulary boost")
                self.model = get_fashion_embedding_model(model_type="fashion-optimized")
            else:
                # Initialize sentence transformer model
                logger.info(f"Loading sentence transformer model: {model_name}")
                self.model = SentenceTransformer(model_name)
            
            # In-memory storage
            self.products_df = None
            self.product_embeddings = None
            self.product_ids = None
            self.enabled = True
            logger.info("Vector search agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector search: {e}")
            self.enabled = False
    
    def _get_cache_path(self, products_df: pd.DataFrame) -> Tuple[Path, str]:
        """Generate cache file path based on product data hash.
        
        Returns:
            Tuple of (cache_path, data_hash)
        """
        # Create hash from product IDs and names to detect data changes
        product_key = '|'.join(products_df['product_id'].astype(str).values[:100])  # First 100 for speed
        data_hash = hashlib.md5(product_key.encode()).hexdigest()
        cache_path = self.CACHE_DIR / f"embeddings_{data_hash}.npy"
        product_ids_path = self.CACHE_DIR / f"product_ids_{data_hash}.npy"
        
        return cache_path, product_ids_path, data_hash
    
    def index_products(self, products_df: pd.DataFrame) -> bool:
        """Index all products with embeddings (with persistent caching).
        
        Args:
            products_df: DataFrame with columns: product_id, name, description, category, etc.
        
        Returns:
            True if indexing successful
        """
        if not self.enabled:
            logger.warning("Vector search not enabled, skipping indexing")
            return False
        
        try:
            self.products_df = products_df.copy()
            logger.info(f"Indexing {len(products_df)} products...")
            
            # Check if embeddings are cached
            cache_path, product_ids_path, data_hash = self._get_cache_path(products_df)
            
            if cache_path.exists() and product_ids_path.exists():
                logger.info(f"✅ Loading cached embeddings from disk (hash: {data_hash})")
                try:
                    self.product_embeddings = np.load(cache_path)
                    self.product_ids = np.load(product_ids_path)
                    
                    # Verify cache integrity
                    if len(self.product_ids) == len(products_df):
                        logger.info(f"✅ Loaded {len(self.product_ids)} embeddings from cache (instant startup!)")
                        return True
                    else:
                        logger.warning(f"Cache size mismatch ({len(self.product_ids)} vs {len(products_df)}), regenerating...")
                except Exception as e:
                    logger.warning(f"Cache load failed: {e}, regenerating...")
            
            # Generate embeddings (slower path - first run or cache invalid)
            logger.info("⏳ Generating product embeddings (this takes ~30 seconds)...")
            
            # Create rich text representation for each product
            documents = []
            for idx, product in products_df.iterrows():
                text_parts = [
                    str(product.get('name', '')),
                    str(product.get('description', '')),
                    str(product.get('category', '')),
                    str(product.get('color', '')),
                ]
                
                # Add style tags if available
                style_tags = product.get('normalized_style_tags') or product.get('style_tags')
                if style_tags:
                    if isinstance(style_tags, list):
                        text_parts.extend([str(tag) for tag in style_tags])
                    else:
                        text_parts.append(str(style_tags))
                
                document = ' '.join(filter(None, text_parts))
                documents.append(document)
            
            # Generate embeddings in batches
            embeddings = self.model.encode(documents, show_progress_bar=True, batch_size=32)
            self.product_embeddings = np.array(embeddings)
            self.product_ids = products_df['product_id'].values
            
            # Save to cache for next startup
            logger.info(f"💾 Caching embeddings to disk...")
            np.save(cache_path, self.product_embeddings)
            np.save(product_ids_path, self.product_ids)
            logger.info(f"✅ Embeddings cached at {cache_path}")
            
            logger.info(f"Successfully indexed {len(self.product_ids)} products with embeddings")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index products: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        category: Optional[str] = None,
        color: Optional[str] = None,
        max_price: Optional[float] = None,
        min_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """Semantic search for products using vector similarity.
        
        Args:
            query: Natural language search query
            top_k: Number of results to return
            category: Filter by category
            color: Filter by color
            max_price: Maximum price filter
            min_price: Minimum price filter
        
        Returns:
            List of product matches with similarity scores
        """
        if not self.enabled or self.product_embeddings is None:
            logger.warning("Vector search not available or products not indexed")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.model.encode(query, show_progress_bar=False)
            query_embedding = np.array(query_embedding).reshape(1, -1)
            
            # Calculate cosine similarity with all products
            similarities = cosine_similarity(query_embedding, self.product_embeddings)[0]
            
            # Get top matches with their indices
            top_indices = np.argsort(similarities)[::-1][:top_k * 3]  # Get more to filter
            
            # Apply filters and format results
            matches = []
            for idx in top_indices:
                if len(matches) >= top_k:
                    break
                
                product = self.products_df.iloc[idx]
                
                # Apply price filters
                price = float(product.get('price') or product.get('price_LKR') or 0)
                if min_price is not None and price < min_price:
                    continue
                if max_price is not None and price > max_price:
                    continue
                
                # Apply category filter
                if category and str(product.get('category', '')).lower() != str(category).lower():
                    continue
                
                # Apply color filter
                if color and str(product.get('color', '')).lower() != str(color).lower():
                    continue
                
                match = {
                    'product_id': str(product['product_id']),
                    'similarity_score': float(similarities[idx]),
                    'metadata': {
                        'name': str(product.get('name', '')),
                        'category': str(product.get('category', '')),
                        'color': str(product.get('color', '')),
                        'price': price,
                        'shop_id': str(product.get('shop_id', '')),
                    }
                }
                matches.append(match)
            
            logger.info(f"Vector search for '{query}' returned {len(matches)} results")
            return matches
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_similar_products(self, product_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Find similar products to a given product.
        
        Args:
            product_id: Product ID to find similar items for
            top_k: Number of similar products to return
        
        Returns:
            List of similar products with scores
        """
        if not self.enabled or self.product_embeddings is None:
            return []
        
        try:
            # Find the product's embedding
            product_idx = np.where(self.product_ids == product_id)[0]
            if len(product_idx) == 0:
                logger.warning(f"Product {product_id} not found in vector index")
                return []
            
            product_idx = product_idx[0]
            embedding = self.product_embeddings[product_idx:product_idx+1]
            
            # Calculate similarity to all products
            similarities = cosine_similarity(embedding, self.product_embeddings)[0]
            
            # Get top matches (excluding self)
            top_indices = np.argsort(similarities)[::-1][:top_k + 1]
            
            matches = []
            for idx in top_indices:
                # Skip the product itself
                if idx == product_idx:
                    continue
                
                product = self.products_df.iloc[idx]
                match = {
                    'product_id': str(product['product_id']),
                    'similarity_score': float(similarities[idx]),
                    'metadata': {
                        'name': str(product.get('name', '')),
                        'category': str(product.get('category', '')),
                        'price': float(product.get('price') or product.get('price_LKR') or 0),
                    }
                }
                matches.append(match)
                
                if len(matches) >= top_k:
                    break
            
            logger.info(f"Found {len(matches)} similar products for {product_id}")
            return matches
            
        except Exception as e:
            logger.error(f"Failed to find similar products: {e}")
            import traceback
            traceback.print_exc()
            return []
