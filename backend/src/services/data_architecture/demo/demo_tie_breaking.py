"""
Demo: Schema Drift Tie-Breaking Strategies

Shows how each strategy handles the same tie scenario
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.schema_drift_tie_breaker import ActionTieBreaker, TieBreakingStrategy


def demo_tie_breaking():
    """Demonstrate all 5 tie-breaking strategies"""
    
    print("\n" + "="*70)
    print("SCHEMA DRIFT DECISION TIE-BREAKING DEMO".center(70))
    print("="*70)
    
    # Scenario: 2 actions with identical scores
    tied_actions = [
        ("auto_merge_schema", 0.75),
        ("create_new_schema_version", 0.75),
        ("quarantine_data", 0.70),
    ]
    
    print(f"\n📊 SCENARIO:")
    print(f"   Table: transactions")
    print(f"   Detected: New column 'customer_segment' (string type)")
    print(f"\n   Policy scores:")
    for action, score in tied_actions:
        print(f"      • {action}: {score}")
    print(f"\n   🔴 PROBLEM: 2 actions tied at 0.75 - which to choose?")
    
    # Demo each strategy
    strategies = [
        TieBreakingStrategy.PRIORITY_ORDER,
        TieBreakingStrategy.RISK_MINIMIZATION,
        TieBreakingStrategy.RANDOM,
        TieBreakingStrategy.CONFIDENCE_MARGIN,
        TieBreakingStrategy.WEIGHTED_BALLOT,
    ]
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\n\n{'─'*70}")
        print(f"STRATEGY {i}: {strategy.value.upper().replace('_', ' ')}")
        print(f"{'─'*70}")
        
        if strategy == TieBreakingStrategy.CONFIDENCE_MARGIN:
            # Special case: show with different margins
            for margin in [0.01, 0.05, 0.10]:
                tie_breaker = ActionTieBreaker(
                    strategy=strategy,
                    confidence_margin=margin
                )
                action, score, reason = tie_breaker.resolve_tie(tied_actions)
                
                print(f"\n   With confidence_margin={margin}:")
                print(f"   Selected: {action}")
                print(f"   Score: {score}")
                print(f"   Reason: {reason}")
        else:
            tie_breaker = ActionTieBreaker(strategy=strategy)
            action, score, reason = tie_breaker.resolve_tie(tied_actions)
            
            print(f"\n   Selected: {action}")
            print(f"   Score: {score}")
            print(f"   Reason: {reason}")
            
            # Show details
            explanation = tie_breaker.explain_tie([(a, s) for a, s in tied_actions if s == max(s for _, s in tied_actions)])
            print(f"\n   Details:")
            for action_name, details in explanation.get("action_details", {}).items():
                print(f"      {action_name}:")
                print(f"         Score: {details['score']}")
                if details.get('priority') is not None:
                    print(f"         Priority: {details['priority']}")
                if details.get('risk_level') is not None:
                    print(f"         Risk Level: {details['risk_level']}")
                if details.get('success_rate') is not None:
                    print(f"         Success Rate: {details['success_rate']:.1%}")


def demo_tie_breaking_complex():
    """Demonstrate tie-breaking with more complex scenario"""
    
    print("\n\n" + "="*70)
    print("COMPLEX SCENARIO: 3-WAY TIE".center(70))
    print("="*70)
    
    tied_actions = [
        ("auto_merge_schema", 0.82),
        ("create_new_schema_version", 0.82),
        ("quarantine_data", 0.82),
        ("rollback_previous_schema", 0.75),
    ]
    
    print(f"\n📊 SCENARIO:")
    print(f"   Table: user_events")
    print(f"   Detected: 3 new columns, 2 dtype changes, 1 missing column")
    print(f"\n   Policy scores:")
    for action, score in tied_actions:
        marker = "🔴" if score == 0.82 else ""
        print(f"      • {action}: {score} {marker}")
    print(f"\n   🔴 PROBLEM: 3 actions all score 0.82 - impossible to choose!")
    
    # Test each strategy
    strategies = [
        ("PRIORITY_ORDER (safest wins)", TieBreakingStrategy.PRIORITY_ORDER),
        ("RISK_MINIMIZATION (lowest risk)", TieBreakingStrategy.RISK_MINIMIZATION),
        ("WEIGHTED_BALLOT (best track record)", TieBreakingStrategy.WEIGHTED_BALLOT),
    ]
    
    for name, strategy in strategies:
        print(f"\n   Using {name}:")
        tie_breaker = ActionTieBreaker(strategy=strategy)
        action, score, reason = tie_breaker.resolve_tie(tied_actions)
        print(f"      → {action}")
        print(f"      → Score: {score}")


def demo_success_rate_updates():
    """Demonstrate updating success rates"""
    
    print("\n\n" + "="*70)
    print("SUCCESS RATE LEARNING".center(70))
    print("="*70)
    
    tie_breaker = ActionTieBreaker(strategy=TieBreakingStrategy.WEIGHTED_BALLOT)
    
    print(f"\n📊 Initial success rates:")
    for action, rate in tie_breaker.ACTION_SUCCESS_RATE.items():
        print(f"   • {action}: {rate:.1%}")
    
    # Simulate 5 decisions
    print(f"\n📝 Simulating 5 decisions:")
    decisions = [
        ("auto_merge_schema", True),      # Success
        ("auto_merge_schema", False),     # Failure
        ("create_new_schema_version", True),
        ("rollback_previous_schema", True),
        ("auto_merge_schema", True),      # Success
    ]
    
    for action, succeeded in decisions:
        tie_breaker.update_success_rate(action, succeeded)
        new_rate = tie_breaker.ACTION_SUCCESS_RATE[action]
        status = "✓" if succeeded else "✗"
        print(f"   {status} {action} → new rate: {new_rate:.1%}")
    
    print(f"\n📊 Updated success rates:")
    for action, rate in sorted(tie_breaker.ACTION_SUCCESS_RATE.items(), 
                              key=lambda x: x[1], reverse=True):
        print(f"   • {action}: {rate:.1%}")


def main():
    demo_tie_breaking()
    demo_tie_breaking_complex()
    demo_success_rate_updates()
    
    print("\n\n" + "="*70)
    print("DEMO COMPLETE".center(70))
    print("="*70)
    print("\nKey Takeaways:")
    print("  1. Always have a tie-breaking strategy ready")
    print("  2. PRIORITY_ORDER is safe for most production systems")
    print("  3. WEIGHTED_BALLOT learns from your history")
    print("  4. CONFIDENCE_MARGIN ensures only confident decisions")
    print("\nNext: Check docs/SCHEMA_DRIFT_TIE_BREAKING.md for full guide")
    print()


if __name__ == '__main__':
    main()
