"""
Conversation Memory Manager
Tracks user queries and results within a session to enable context-aware responses
"""
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Manages conversation history for context-aware responses"""
    
    def __init__(self, timeout_minutes: int = 30):
        """
        Initialize conversation memory
        
        Args:
            timeout_minutes: Session timeout in minutes
        """
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.timeout = timedelta(minutes=timeout_minutes)
    
    def get_or_create_session(self, user_id: str) -> Dict[str, Any]:
        """Get or create a session for user"""
        now = datetime.now()
        
        if user_id not in self.sessions:
            self.sessions[user_id] = {
                'created_at': now,
                'last_activity': now,
                'query_history': [],
                'result_cache': {},
                'last_search_results': [],
                'last_query': None,
            }
        
        session = self.sessions[user_id]
        
        # Check timeout
        if now - session['last_activity'] > self.timeout:
            logger.info(f"Session for user {user_id} expired, creating new one")
            self.sessions[user_id] = {
                'created_at': now,
                'last_activity': now,
                'query_history': [],
                'result_cache': {},
                'last_search_results': [],
                'last_query': None,
            }
            session = self.sessions[user_id]
        else:
            session['last_activity'] = now
        
        return session
    
    def add_query(self, user_id: str, query: str) -> None:
        """Record a query in conversation history"""
        session = self.get_or_create_session(user_id)
        session['query_history'].append({
            'query': query,
            'timestamp': datetime.now(),
        })
        session['last_query'] = query
        logger.info(f"[MEMORY] Added query for {user_id}: '{query}'")
    
    def add_results(self, user_id: str, products: List[Dict], query: str = None) -> None:
        """Cache search results"""
        session = self.get_or_create_session(user_id)
        
        if query is None:
            query = session['last_query'] or 'unknown'
        
        session['last_search_results'] = products
        session['result_cache'][query] = {
            'products': products,
            'timestamp': datetime.now(),
            'count': len(products),
        }
        logger.info(f"[MEMORY] Cached {len(products)} results for query: '{query}'")
    
    def get_last_results(self, user_id: str) -> List[Dict]:
        """Get the last search results"""
        session = self.get_or_create_session(user_id)
        return session['last_search_results']
    
    def get_nth_result(self, user_id: str, index: int) -> Optional[Dict]:
        """
        Get nth result from last search (for "add first one", "second one", etc)
        
        Args:
            user_id: User ID
            index: 0-based index (0 = first, 1 = second, etc)
        
        Returns:
            Product dict or None
        """
        results = self.get_last_results(user_id)
        if 0 <= index < len(results):
            product = results[index]
            logger.info(f"[MEMORY] Retrieving result #{index+1}: {product.get('name', 'Unknown')}")
            return product
        
        logger.warning(f"[MEMORY] Index {index} out of range (have {len(results)} results)")
        return None
    
    def get_context(self, user_id: str) -> Dict[str, Any]:
        """Get full conversation context"""
        session = self.get_or_create_session(user_id)
        return {
            'last_query': session['last_query'],
            'last_results_count': len(session['last_search_results']),
            'query_count': len(session['query_history']),
            'session_duration': (datetime.now() - session['created_at']).seconds / 60,
        }
    
    def parse_ordinal(self, query: str) -> Optional[int]:
        """
        Parse ordinal references like 'first', 'second', 'third', etc
        
        Args:
            query: User query text
        
        Returns:
            0-based index or None
        """
        ordinals = {
            'first': 0, 'second': 1, 'third': 2, 'fourth': 3, 'fifth': 4,
            'sixth': 5, 'seventh': 6, 'eighth': 7, 'ninth': 8, 'tenth': 9,
            '1st': 0, '2nd': 1, '3rd': 2, '4th': 3, '5th': 4,
            '6th': 5, '7th': 6, '8th': 7, '9th': 8, '10th': 9,
        }
        
        query_lower = query.lower()
        for ordinal, index in ordinals.items():
            if ordinal in query_lower:
                logger.info(f"[MEMORY] Detected ordinal: '{ordinal}' → index {index}")
                return index
        
        return None
    
    def is_reference_query(self, query: str) -> bool:
        """
        Check if query is a reference to previous results
        
        Examples:
            - "add first one to cart"
            - "show second one"
            - "buy the third item"
        
        Returns:
            True if query references previous results
        """
        reference_patterns = [
            'add', 'buy', 'show', 'get', 'pick', 'select', 'first', 'second',
            'third', 'one', 'item', '1st', '2nd', '3rd'
        ]
        
        query_lower = query.lower()
        return any(pattern in query_lower for pattern in reference_patterns) and \
               not any(keyword in query_lower for keyword in ['new', 'different', 'other', 'instead'])
    
    def clear_session(self, user_id: str) -> None:
        """Clear session for user"""
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info(f"[MEMORY] Cleared session for {user_id}")


# Global instance
conversation_memory = ConversationMemory(timeout_minutes=30)


def get_conversation_memory() -> ConversationMemory:
    """Get global conversation memory instance"""
    return conversation_memory
