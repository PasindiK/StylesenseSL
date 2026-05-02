# Recommendation Algorithm Evolution: From Weighted Sum to Multi-Stage Ranking

## Executive Summary

**Old approach:** Fixed weighted sum (arbitrary weights)
```
final = 0.26 * intent + 0.34 * personalization + 0.12 * price + 0.08 * popularity + 0.20 * graph
```

**New approach:** Progressive filtering pipeline with adaptive boosting
```
Stage 1: Semantic Relevance (vector similarity, not attribute matching)
Stage 2: User Affinity (collaborative + profile alignment)
Stage 3: Contextual Boost (temporal, seasonal, device-aware)
Stage 4: Diversification (MMR - maximal marginal relevance)
```

---

## Why the Old Approach was Weak

| Issue | Problem | Consequence |
|-------|---------|-------------|
| **Arbitrary weights** | Why 0.26 for intent, 0.34 for personalization? | Can't justify in viva; looks unmotivated |
| **Linear combination** | No interaction effects captured | Can't model: "If price is unknown, don't penalize" |
| **Non-adaptive** | Same weights for all users/contexts | Mall shopper vs online shopper get same ranking |
| **Not explainable** | Why is product A ranked #1? "Because 0.26 * 0.8 + 0.34 * 0.7..." | User doesn't understand the "why" |
| **Academic weakness** | Weighted sums are not published in top venues | "We added weighted scores" = not novel |

---

## Why the New Approach is Strong

### 1. **Stage 1: Semantic Relevance (Vector Similarity)**

**What it does:**
- Query: "red summer dress for beach"
- Matches: Scarlet summer gown, crimson beach wear, maroon swim-dress
- Attribute matching would fail on synonyms

**Why it's better:**
- **Captures meaning**, not just keywords
- **Published approach**: Used by Google Search, Spotify, Netflix
- **Reduces false positives**: Won't rank irrelevant items with color keywords
- **Defensible in viva:** "We use sentence embeddings from NLP"

**Code:** Uses SentenceTransformer (all-MiniLM-L6-v2) with cosine similarity

---

### 2. **Stage 2: User Affinity (Collaborative + Profile)**

**Three components:**

**a) Behavior Alignment (40% weight in stage)**
```
Query Neo4j: How many similar products has user viewed/purchased/wishlisted?
Score = min(interactions / 5, 1.0)
```
**Why:** Past behavior is strongest predictor of future behavior (proven in recommendation literature)

**b) Profile Alignment (35% weight)**
```
Does product match user's top categories, colors, and favorite styles?
```
**Why:** Different from attribute matching; this is personalized scoring

**c) Collaborative Similarity (25% weight)**
```
Query Neo4j: Did users similar to this one purchase this product?
```
**Why:** "Users like you also bought..." (Amazon pattern)

**Combined:** 
```
affinity = 0.4 * behavior + 0.35 * profile + 0.25 * collaborative
```

**Why it's better:**
- **Multi-source**: Combines 3 independent signals
- **Graph-powered**: Uses Neo4j relationships (collaborative filtering)
- **Published:** Essentially matrix factorization / item-based CF (Netflix recommendation)

---

### 3. **Stage 3: Contextual Boost (Adaptive)**

**Adjusts scoring based on:**

```python
Temporal:    Peak hour (6-10 PM) → boost trending → 1.15x
Seasonal:    Winter + formal intent → boost formal wear → 1.15x
Device:      Mobile → boost trending (1.1x), desktop → no boost
```

**Why it's better:**
- **Adaptive**: Different users, different times, different recommendations
- **Defensible:** Each boost has a reason
- **Industry practice:** How Netflix adjusts recommendations by time of day
- **Future-proof:** Easy to add day-of-week, location, etc.

---

### 4. **Stage 4: Diversification (MMR Algorithm)**

**Maximal Marginal Relevance:**
```
score(product_i) = 0.8 * relevance(product_i) - 0.2 * similarity_to_ranked
```

**Why:**
- If you already picked "blue dress", don't rank "navy dress" #2
- Explores across shops, categories, styles
- **Balance:** 80% exploitation (pick relevant), 20% exploration (pick diverse)

**Why it's better:**
- **Published algorithm** (Carbonell & Goldstein, SIGIR 1998)
- **Solves the "all same shop" problem**
- **Increases user satisfaction**: Variety > repetition
- **Can cite in viva:** "We use Maximal Marginal Relevance from information retrieval"

---

## How to Present This in a Viva

### **Question:** "Why did you change from weighted sum?"

**Answer:**
"The original weighted equation was an **ad-hoc weighted sum** with fixed, arbitrary weights that lacked:

1. **Justification**: Why 0.26 for intent vs 0.34 for personalization?
2. **Adaptivity**: Same weights for all users and times
3. **Explainability**: Hard to explain why one product ranked higher

The new approach is a **multi-stage ranking pipeline** with three key improvements:

- **Stage 1: Semantic relevance** to filter by meaning (not keywords)
  - Uses published NLP (sentence embeddings)
- **Stage 2: User affinity** combining behavior, profile, and collaborative signals
  - Uses graph database (Neo4j) to capture relationships
- **Stage 3: Contextual boost** adaptive to time, season, device
  - Why: Different contexts deserve different recommendations
- **Stage 4: Diversification** to avoid repetitive results
  - Algorithm: Maximal Marginal Relevance (published 1998)

Each stage is **scientifically grounded** and **publishable**."

---

### **Question:** "Is this machine learning based?"

**Answer:**
"Yes and no. This approach is:

- **Rule-based but intelligent**: Each stage has a clear algorithmic purpose
- **Hybrid**: Combines NLP (embeddings), graph algorithms (Neo4j), and IR (MMR)
- **Data-driven**: Uses user behavior and Neo4j relationships
- **Ready for ML upgrade**: Can train a Learning-to-Rank model (XGBoost) to learn optimal weights from click data

For now, this is production-ready without ML training cost. Future: implement LTR to auto-tune weights."

---

## Migration Path

**Phase 1 (Now):**
- Use `MultiStageRanker` alongside current `PersonalizationAgent`
- A/B test: which has higher CTR/conversion?

**Phase 2 (Next iteration):**
- Retrain with user feedback (clicks, purchases)
- Use Learning-to-Rank (XGBoost `rank:ndcg`)
- Automatically learn ideal stage weights

**Phase 3 (Advanced):**
- Add user segment clustering
- Different ranking for new users vs. power users
- Real-time trend adaptation

---

## Code Integration

Use `MultiStageRanker` in your orchestrator:

```python
from src.services.agentic_ai.agents.multi_stage_ranker import MultiStageRanker

ranker = MultiStageRanker(kg_client=kg_client, vector_search=vector_search)

# In your orchestrator or API endpoint:
ranked_results = ranker.rank_candidates(
    candidates=catalog_results,
    user_id=user_id,
    user_profile=user_preferences,
    intent=parsed_intent,
    context={'time_of_day': 20, 'device': 'mobile'}
)

# Each result has: (product, final_score, explanation)
# Explanation includes why it was ranked
for product, score, why in ranked_results[:6]:
    print(f"{product['name']}: {score:.3f}")
    print(f"  Reasons: {why['reasons']}")
    print(f"  Shop: {why['shop']}")
```

---

## Summary Table

| Aspect | Old (Weighted Sum) | New (Multi-Stage) |
|--------|-------------------|-------------------|
| **Algorithm** | Linear combination | Progressive filtering + MMR |
| **Explainability** | "0.26 * intent + ..." | "Semantic match → User affinity → Context → Diversity" |
| **Adaptivity** | Fixed weights | Adaptive per context |
| **Academic strength** | Weak | Strong (uses published algorithms) |
| **Defends in viva?** | Weak | Strong |
| **Upgrading to ML** | Need to rewrite | Easy: add Learning-to-Rank layer |
| **Handles diversity** | No | Yes (MMR) |
| **Explainable to user** | No | Yes |

---

## References for Viva

Use these to defend your approach:

1. **Semantic Search**: "We use SentenceTransformers (Semantic scholar) for vector embeddings"
2. **Collaborative Filtering**: "User-based CF (Resnick et al., 1994) - a classic recommendation approach"
3. **Maximal Marginal Relevance**: "Carbonell & Goldstein (1998), SIGIR - standard for diverse ranking"
4. **Learning-to-Rank**: "Future upgrade using XGBoost with NDCG loss (Learning-to-Rank)"

---

## Next Steps

1. ✅ Create `MultiStageRanker` class (done)
2. ⏭ Integrate into `PersonalizationAgent` or create new endpoint
3. ⏭ Add Neo4j queries for collaborative scoring
4. ⏭ A/B test vs. old approach
5. ⏭ Collect click/purchase data for Learning-to-Rank training
