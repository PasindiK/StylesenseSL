"""Deduplication service to track shown products per user and avoid duplicate recommendations."""
import logging
from typing import Dict, List, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Tracks which products have been shown to users to prevent duplicates in recommendations."""
    
    def __init__(self, session_timeout_minutes: int = 60):
        """Initialize deduplication service.
        
        Args:
            session_timeout_minutes: How long to remember shown products (default 60 minutes)
        """
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        # Format: {user_id: {'products': set(product_ids), 'last_updated': datetime}}
        self.user_shown_products: Dict[str, Dict] = {}
        logger.info(f"Deduplication service initialized (session timeout: {session_timeout_minutes}m)")
    
    def track_shown(self, user_id: str, product_ids: List[str]) -> None:
        """Track that these products have been shown to a user.
        
        Args:
            user_id: User identifier
            product_ids: List of product IDs that were shown
        """
        if not user_id or not product_ids:
            return
        
        user_key = str(user_id)
        
        # Initialize user session if needed
        if user_key not in self.user_shown_products:
            self.user_shown_products[user_key] = {
                'products': set(),
                'last_updated': datetime.now()
            }
        
        # Add products to the set (case-insensitive by converting to string)
        for pid in product_ids:
            self.user_shown_products[user_key]['products'].add(str(pid))
        
        # Update timestamp
        self.user_shown_products[user_key]['last_updated'] = datetime.now()
        
        logger.debug(f"Tracked {len(product_ids)} products for user {user_id}")
    
    def get_shown_products(self, user_id: str) -> Set[str]:
        """Get all product IDs that have been shown to a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Set of product IDs that have been shown (empty set if no session)
        """
        user_key = str(user_id)
        
        if user_key not in self.user_shown_products:
            return set()
        
        session = self.user_shown_products[user_key]
        
        # Check if session has expired
        if datetime.now() - session['last_updated'] > self.session_timeout:
            # Session expired, clear it
            del self.user_shown_products[user_key]
            logger.debug(f"Session expired for user {user_id}")
            return set()
        
        return session['products'].copy()
    
    def filter_new_products(self, user_id: str, product_ids: List[str]) -> List[str]:
        """Filter out products that have already been shown to a user.
        
        Args:
            user_id: User identifier
            product_ids: List of candidate product IDs
            
        Returns:
            Filtered list containing only new products not previously shown
        """
        shown = self.get_shown_products(user_id)
        product_ids_str = [str(pid) for pid in product_ids]
        return [pid for pid in product_ids_str if pid not in shown]
    
    def clear_user_session(self, user_id: str) -> None:
        """Clear all shown products for a user (e.g., when starting a new conversation).
        
        Args:
            user_id: User identifier
        """
        user_key = str(user_id)
        if user_key in self.user_shown_products:
            del self.user_shown_products[user_key]
            logger.debug(f"Cleared session for user {user_id}")
    
    def cleanup_expired_sessions(self) -> None:
        """Remove expired sessions from memory."""
        now = datetime.now()
        expired_users = [
            user_id for user_id, session in self.user_shown_products.items()
            if now - session['last_updated'] > self.session_timeout
        ]
        
        for user_id in expired_users:
            del self.user_shown_products[user_id]
        
        if expired_users:
            logger.info(f"Cleaned up {len(expired_users)} expired sessions")
    
    def get_stats(self, user_id: str) -> Dict:
        """Get statistics for a user's session.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict with session stats
        """
        user_key = str(user_id)
        
        if user_key not in self.user_shown_products:
            return {
                'user_id': user_id,
                'shown_product_count': 0,
                'session_exists': False
            }
        
        session = self.user_shown_products[user_key]
        return {
            'user_id': user_id,
            'shown_product_count': len(session['products']),
            'session_exists': True,
            'last_updated': session['last_updated'].isoformat()
        }
    
    def reset_all(self) -> None:
        """Clear all sessions (for testing)."""
        self.user_shown_products.clear()
        logger.info("All sessions cleared")


# Global instance
_dedup_service = None


def get_deduplication_service() -> DeduplicationService:
    """Get or create the global deduplication service."""
    global _dedup_service
    if _dedup_service is None:
        _dedup_service = DeduplicationService()
    return _dedup_service
