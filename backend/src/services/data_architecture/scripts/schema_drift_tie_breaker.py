"""
Tie-Breaking Strategies for Schema Drift Decision Policy
Handles scenarios where 2+ actions have the same highest score
"""
from typing import List, Dict, Tuple, Any
from enum import Enum
import random


class TieBreakingStrategy(Enum):
    """Strategy to use when multiple actions have same score"""
    PRIORITY_ORDER = "priority_order"      # Use predefined action priority
    RISK_MINIMIZATION = "risk_minimization"  # Choose safest action
    RANDOM = "random"                       # Random selection (good for exploration)
    CONFIDENCE_MARGIN = "confidence_margin"  # Require margin between scores
    WEIGHTED_BALLOT = "weighted_ballot"     # Weight by historical success rate


class ActionTieBreaker:
    """
    Handles tie-breaking when multiple actions have the same score
    """
    
    # Action priority (higher = safer/more conservative)
    ACTION_PRIORITY = {
        "require_human_approval": 0,        # Most conservative - always escalate if tied
        "rollback_previous_schema": 1,      # Very conservative - rollback
        "quarantine_data": 2,               # Conservative - quarantine
        "create_new_schema_version": 3,     # Moderate - create new version
        "auto_merge_schema": 4,             # Moderate - merge schema
    }
    
    # Risk levels for each action
    ACTION_RISK = {
        "require_human_approval": 0,        # No risk - just escalates
        "rollback_previous_schema": 1,      # Low risk - reverts to known good
        "quarantine_data": 2,               # Medium risk - data unavailable
        "create_new_schema_version": 3,     # Higher risk - new unknown version
        "auto_merge_schema": 4,             # Highest risk - auto-accepts changes
    }
    
    # Historical success rate (0.0 to 1.0) - updated from logs
    ACTION_SUCCESS_RATE = {
        "require_human_approval": 1.0,
        "rollback_previous_schema": 0.95,
        "quarantine_data": 0.88,
        "create_new_schema_version": 0.75,
        "auto_merge_schema": 0.68,
    }
    
    def __init__(self, strategy: TieBreakingStrategy = TieBreakingStrategy.PRIORITY_ORDER, 
                 confidence_margin: float = 0.05, seed: int = None):
        """
        Args:
            strategy: Which tie-breaking strategy to use
            confidence_margin: For CONFIDENCE_MARGIN strategy, require this score difference
            seed: Random seed for reproducibility
        """
        self.strategy = strategy
        self.confidence_margin = confidence_margin
        if seed is not None:
            random.seed(seed)
    
    def resolve_tie(self, 
                   actions_with_scores: List[Tuple[str, float]], 
                   context: Dict[str, Any] = None) -> Tuple[str, float, str]:
        """
        Resolve tie when multiple actions have highest score
        
        Args:
            actions_with_scores: List of (action_name, score) tuples
            context: Additional context about the drift (diff, table_name, etc.)
        
        Returns:
            (selected_action, score, reason_for_selection)
        """
        if not actions_with_scores:
            return None, 0.0, "No actions available"
        
        # Check for actual tie (same highest score)
        max_score = max(score for _, score in actions_with_scores)
        tied_actions = [(action, score) for action, score in actions_with_scores 
                       if score == max_score]
        
        # No tie - single winner
        if len(tied_actions) == 1:
            action, score = tied_actions[0]
            return action, score, "Single highest score (no tie)"
        
        # Handle tie based on strategy
        if self.strategy == TieBreakingStrategy.PRIORITY_ORDER:
            return self._priority_order_tie_break(tied_actions)
        
        elif self.strategy == TieBreakingStrategy.RISK_MINIMIZATION:
            return self._risk_minimization_tie_break(tied_actions)
        
        elif self.strategy == TieBreakingStrategy.RANDOM:
            return self._random_tie_break(tied_actions)
        
        elif self.strategy == TieBreakingStrategy.CONFIDENCE_MARGIN:
            return self._confidence_margin_tie_break(actions_with_scores)
        
        elif self.strategy == TieBreakingStrategy.WEIGHTED_BALLOT:
            return self._weighted_ballot_tie_break(tied_actions, context)
        
        else:
            # Fallback to priority order
            return self._priority_order_tie_break(tied_actions)
    
    def _priority_order_tie_break(self, tied_actions: List[Tuple[str, float]]) -> Tuple[str, float, str]:
        """
        Strategy 1: Use predefined action priority (safest first)
        
        Best for: Production systems where safety > performance
        """
        # Sort by priority (lower number = higher priority)
        sorted_actions = sorted(tied_actions, 
                              key=lambda x: self.ACTION_PRIORITY.get(x[0], 999))
        
        selected_action, score = sorted_actions[0]
        tied_action_names = [a[0] for a in tied_actions]
        reason = f"Tie between {len(tied_actions)} actions: {tied_action_names}. Selected by priority: {selected_action}"
        
        return selected_action, score, reason
    
    def _risk_minimization_tie_break(self, tied_actions: List[Tuple[str, float]]) -> Tuple[str, float, str]:
        """
        Strategy 2: Choose action with lowest risk
        
        Best for: Conservative environments where safety is paramount
        """
        sorted_actions = sorted(tied_actions, 
                              key=lambda x: self.ACTION_RISK.get(x[0], 999))
        
        selected_action, score = sorted_actions[0]
        tied_action_names = [a[0] for a in tied_actions]
        reason = f"Tie between {len(tied_actions)} actions: {tied_action_names}. Selected lowest-risk: {selected_action}"
        
        return selected_action, score, reason
    
    def _random_tie_break(self, tied_actions: List[Tuple[str, float]]) -> Tuple[str, float, str]:
        """
        Strategy 3: Random selection among tied actions
        
        Best for: A/B testing or exploration of alternative strategies
        """
        selected_action, score = random.choice(tied_actions)
        tied_action_names = [a[0] for a in tied_actions]
        reason = f"Tie between {len(tied_actions)} actions: {tied_action_names}. Randomly selected: {selected_action}"
        
        return selected_action, score, reason
    
    def _confidence_margin_tie_break(self, 
                                    actions_with_scores: List[Tuple[str, float]]) -> Tuple[str, float, str]:
        """
        Strategy 4: Require confidence margin between top scores
        
        If no single action is clearly better (score difference < margin),
        escalate to human review
        
        Best for: Situations where confidence level matters
        """
        sorted_actions = sorted(actions_with_scores, key=lambda x: x[1], reverse=True)
        
        top_action, top_score = sorted_actions[0]
        second_action, second_score = sorted_actions[1] if len(sorted_actions) > 1 else (None, 0)
        
        margin = top_score - second_score if second_score else top_score
        
        if margin >= self.confidence_margin:
            reason = f"Top score ({top_action}: {top_score:.3f}) has sufficient margin over runner-up ({margin:.3f})"
            return top_action, top_score, reason
        else:
            reason = f"Insufficient confidence margin ({margin:.3f} < {self.confidence_margin}). Escalating to human review."
            return "require_human_approval", 0.5, reason
    
    def _weighted_ballot_tie_break(self, 
                                  tied_actions: List[Tuple[str, float]], 
                                  context: Dict[str, Any] = None) -> Tuple[str, float, str]:
        """
        Strategy 5: Weight by historical success rate
        
        Select action with best historical success rate when scores tied
        
        Best for: Production where track record matters
        """
        # Weight each tied action by its historical success rate
        weighted_actions = []
        for action, score in tied_actions:
            success_rate = self.ACTION_SUCCESS_RATE.get(action, 0.5)
            weighted_score = score * success_rate  # Adjust score by success rate
            weighted_actions.append((action, score, weighted_score))
        
        # Sort by weighted score
        sorted_actions = sorted(weighted_actions, key=lambda x: x[2], reverse=True)
        
        selected_action, original_score, weighted_score = sorted_actions[0]
        tied_action_names = [a[0] for a in tied_actions]
        success_rate = self.ACTION_SUCCESS_RATE.get(selected_action, 0.5)
        
        reason = f"Tie between {len(tied_actions)} actions: {tied_action_names}. " \
                f"Selected by success rate: {selected_action} (rate: {success_rate:.2%}, weighted_score: {weighted_score:.3f})"
        
        return selected_action, original_score, reason
    
    def update_success_rate(self, action: str, succeeded: bool, new_rate: float = None):
        """
        Update historical success rate for an action
        
        Args:
            action: Action name
            succeeded: Whether the action succeeded
            new_rate: If provided, directly set new success rate
        """
        if new_rate is not None:
            self.ACTION_SUCCESS_RATE[action] = max(0.0, min(1.0, new_rate))
        else:
            # Update with exponential moving average
            current = self.ACTION_SUCCESS_RATE.get(action, 0.5)
            alpha = 0.3  # Smoothing factor
            new_val = succeeded + alpha * current + (1 - alpha) * (not succeeded)
            self.ACTION_SUCCESS_RATE[action] = new_val
    
    def explain_tie(self, actions_with_scores: List[Tuple[str, float]]) -> Dict[str, Any]:
        """
        Provide detailed explanation of tie scenario
        """
        max_score = max(score for _, score in actions_with_scores) if actions_with_scores else 0
        tied = [(action, score) for action, score in actions_with_scores if score == max_score]
        
        explanation = {
            "tied_actions": tied,
            "tie_count": len(tied),
            "highest_score": max_score,
            "strategy_used": self.strategy.value,
            "action_details": {}
        }
        
        # Detail each tied action
        for action, score in tied:
            explanation["action_details"][action] = {
                "score": score,
                "priority": self.ACTION_PRIORITY.get(action, None),
                "risk_level": self.ACTION_RISK.get(action, None),
                "success_rate": self.ACTION_SUCCESS_RATE.get(action, None),
            }
        
        return explanation


# Example usage in schema_drift.py
def resolve_policy_action_tie(actions_with_scores: List[Tuple[str, float]], 
                             strategy: TieBreakingStrategy = TieBreakingStrategy.PRIORITY_ORDER,
                             context: Dict[str, Any] = None) -> Tuple[str, float, str]:
    """
    Convenience function to resolve ties in policy decisions
    
    Usage in handle_schema_drift():
        if len(tied_actions) > 1:
            chosen_action, score, reason = resolve_policy_action_tie(tied_actions)
    """
    tie_breaker = ActionTieBreaker(strategy=strategy)
    return tie_breaker.resolve_tie(actions_with_scores, context)
