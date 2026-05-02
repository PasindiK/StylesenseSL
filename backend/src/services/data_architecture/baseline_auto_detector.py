"""
Baseline Auto-Detection Engine
Intelligently matches uploaded datasets to their corresponding baseline schemas
"""

from typing import Dict, List, Any, Set, Tuple
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class BaselineAutoDetector:
    """
    Intelligent system to automatically detect which baseline schema 
    a newly uploaded dataset belongs to.
    
    Uses multiple matching strategies:
    1. Primary key detection (strongest signal)
    2. Characteristic column matching
    3. Column count similarity
    4. Data type pattern matching
    """
    
    # Define known baselines with their characteristics
    BASELINE_DEFINITIONS = {
        "users": {
            "primary_key": "user_id",
            "unique_identifiers": ["user_id"],
            "characteristic_columns": ["user_id", "name", "email", "phone", "shipping_address", "signup_ts", "is_active"],
            "expected_column_count": 7,
            "expected_row_range": (100, 10000),
            "description": "User profile and account data",
            "file_pattern": ["user", "users", "customer", "customers", "account"]
        },
        
        "products": {
            "primary_key": "product_id",
            "unique_identifiers": ["product_id"],
            "characteristic_columns": ["product_id", "shop_id", "name", "category", "color", "fabric", "price_LKR", "style_tags"],
            "expected_column_count": 14,
            "expected_row_range": (500, 50000),
            "description": "Product catalog and inventory data",
            "file_pattern": ["product", "products", "catalog", "item", "items"]
        },
        
        "transactions": {
            "primary_key": "item_id",
            "unique_identifiers": ["item_id", "transaction_id"],
            "characteristic_columns": ["item_id", "user_id", "product_id", "amount", "payment_method", "transaction_date"],
            "expected_column_count": 6,
            "expected_row_range": (100, 100000),
            "description": "Transaction, order, and purchase data",
            "file_pattern": ["transaction", "transactions", "order", "orders", "purchase", "sale"]
        },
        
        "shops": {
            "primary_key": "shop_id",
            "unique_identifiers": ["shop_id"],
            "characteristic_columns": ["shop_id", "shop_name", "location", "country", "contact_info"],
            "expected_column_count": 9,
            "expected_row_range": (10, 500),
            "description": "Shop and vendor information",
            "file_pattern": ["shop", "shops", "store", "stores", "vendor", "vendors"]
        },
        
        "trends": {
            "primary_key": "trend_id",
            "unique_identifiers": ["trend_id"],
            "characteristic_columns": ["trend_id", "trend_name", "category", "trend_season", "popularity_score"],
            "expected_column_count": 8,
            "expected_row_range": (50, 1000),
            "description": "Fashion trend data and seasonal information",
            "file_pattern": ["trend", "trends", "fashion", "style", "season"]
        }
    }
    
    
    def detect_baseline(self, df: pd.DataFrame, filename: str = None) -> Dict[str, Any]:
        """
        Detect which baseline schema the uploaded dataset matches.
        
        Args:
            df: Uploaded DataFrame
            filename: Optional filename for additional context
        
        Returns:
            Dictionary with detection results including:
            - detected_baseline: Name of best matching baseline
            - confidence: Confidence score (0-1)
            - alternatives: List of alternative baselines
            - matched_columns: Columns that matched the baseline
            - reasoning: Human-readable explanation
            - recommendation: Action to take
        """
        
        uploaded_columns = set(df.columns)
        uploaded_columns_lower = set(col.lower() for col in df.columns)
        uploaded_count = len(df.columns)
        uploaded_rows = len(df)
        
        logger.info(f"[BASELINE AUTO-DETECT] Analyzing dataset: {len(uploaded_columns)} columns, {uploaded_rows} rows")
        if filename:
            logger.info(f"[BASELINE AUTO-DETECT] Filename: {filename}")
        
        # Score each baseline
        scores = {}
        match_details = {}
        
        for baseline_name, baseline_info in self.BASELINE_DEFINITIONS.items():
            score, details = self._calculate_match_score(
                uploaded_columns=uploaded_columns,
                uploaded_columns_lower=uploaded_columns_lower,
                uploaded_count=uploaded_count,
                uploaded_rows=uploaded_rows,
                filename=filename,
                baseline_info=baseline_info
            )
            scores[baseline_name] = score
            match_details[baseline_name] = details
            
            logger.info(f"[BASELINE AUTO-DETECT] {baseline_name}: score={score:.3f}, details={details}")
        
        # Get ranked results
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_match = sorted_scores[0][0]
        best_confidence = sorted_scores[0][1]
        best_details = match_details[best_match]
        
        # Generate response
        detection_result = {
            "detected_baseline": best_match,
            "confidence": round(best_confidence, 3),
            "alternatives": [
                {
                    "baseline": name,
                    "confidence": round(score, 3)
                }
                for name, score in sorted_scores[1:3]  # Top 2 alternatives
            ],
            "matched_columns": best_details["matched_columns"],
            "analysis": {
                "primary_key_found": best_details["primary_key_found"],
                "characteristic_columns_matched": best_details["char_cols_matched"],
                "column_count_similarity": best_details["col_count_similarity"],
                "row_count_plausible": best_details["row_count_plausible"],
                "filename_similarity": best_details["filename_similarity"]
            },
            "reasoning": self._generate_reasoning(
                best_match,
                best_confidence,
                best_details,
                self.BASELINE_DEFINITIONS[best_match]
            ),
            "recommendation": self._get_recommendation(best_confidence)
        }
        
        logger.info(f"[BASELINE AUTO-DETECT] Final Result: {best_match} (confidence={best_confidence:.3f})")
        
        return detection_result
    
    
    def _calculate_match_score(
        self,
        uploaded_columns: Set[str],
        uploaded_columns_lower: Set[str],
        uploaded_count: int,
        uploaded_rows: int,
        filename: str,
        baseline_info: Dict[str, Any]
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Calculate how well uploaded dataset matches this baseline.
        Uses multiple scoring factors.
        """
        score = 0.0
        details = {
            "primary_key_found": False,
            "char_cols_matched": 0,
            "col_count_similarity": 0,
            "row_count_plausible": False,
            "filename_similarity": 0,
            "matched_columns": []
        }
        
        # 1. PRIMARY KEY MATCH (50% weight) - Strongest signal
        primary_key = baseline_info["primary_key"]
        primary_key_lower = primary_key.lower()
        if primary_key in uploaded_columns or primary_key_lower in uploaded_columns_lower:
            score += 0.50
            details["primary_key_found"] = True
        
        # 2. CHARACTERISTIC COLUMNS (25% weight)
        char_cols = baseline_info["characteristic_columns"]
        char_cols_lower = [col.lower() for col in char_cols]
        matched_char_cols = [
            col for col in uploaded_columns 
            if col.lower() in char_cols_lower
        ]
        details["matched_columns"] = matched_char_cols
        details["char_cols_matched"] = len(matched_char_cols)
        
        char_score = min(0.25, (len(matched_char_cols) / len(char_cols)) * 0.25)
        score += char_score
        
        # 3. COLUMN COUNT SIMILARITY (15% weight)
        expected_count = baseline_info["expected_column_count"]
        col_count_diff = abs(uploaded_count - expected_count)
        
        if col_count_diff == 0:
            col_count_score = 0.15
        elif col_count_diff <= 2:
            col_count_score = 0.10
        elif col_count_diff <= 5:
            col_count_score = 0.05
        else:
            col_count_score = 0.0
        
        score += col_count_score
        details["col_count_similarity"] = col_count_score
        
        # 4. ROW COUNT PLAUSIBILITY (5% weight)
        min_rows, max_rows = baseline_info["expected_row_range"]
        if min_rows <= uploaded_rows <= max_rows:
            score += 0.05
            details["row_count_plausible"] = True
        elif uploaded_rows < min_rows * 0.5 or uploaded_rows > max_rows * 2:
            score -= 0.02  # Penalize very implausible row counts
        
        # 5. FILENAME SIMILARITY (5% weight)
        if filename:
            filename_lower = filename.lower()
            for pattern in baseline_info["file_pattern"]:
                if pattern in filename_lower:
                    score += 0.05
                    details["filename_similarity"] = 0.05
                    break
        
        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        
        return score, details
    
    
    def _generate_reasoning(
        self,
        baseline_name: str,
        confidence: float,
        details: Dict[str, Any],
        baseline_info: Dict[str, Any]
    ) -> str:
        """Generate human-readable explanation of the detection."""
        
        reasons = []
        
        # Primary key
        if details["primary_key_found"]:
            reasons.append(f"Primary key '{baseline_info['primary_key']}' detected")
        
        # Characteristic columns
        if details["matched_columns"]:
            matched_list = ", ".join(details["matched_columns"][:3])
            if len(details["matched_columns"]) > 3:
                matched_list += f", ... (+{len(details['matched_columns']) - 3} more)"
            reasons.append(f"Matched {len(details['matched_columns'])} characteristic columns: {matched_list}")
        
        # Column count
        if details["col_count_similarity"] > 0:
            reasons.append(f"Column count ({details['matched_columns'].__len__()}) similar to expected ({baseline_info['expected_column_count']})")
        
        # Row count
        if details["row_count_plausible"]:
            min_rows, max_rows = baseline_info["expected_row_range"]
            reasons.append(f"Row count ({len(details['matched_columns'])}) within expected range ({min_rows}-{max_rows})")
        
        # Filename
        if details["filename_similarity"] > 0:
            reasons.append("Filename contains dataset type keyword")
        
        reasoning = " → ".join(reasons) if reasons else "Partial match based on available data"
        
        # Add confidence level interpretation
        if confidence >= 0.90:
            reasoning += " (Very high confidence)"
        elif confidence >= 0.75:
            reasoning += " (High confidence)"
        elif confidence >= 0.60:
            reasoning += " (Moderate confidence)"
        else:
            reasoning += " (Low confidence - manual selection recommended)"
        
        return reasoning
    
    
    def _get_recommendation(self, confidence: float) -> Dict[str, Any]:
        """Get recommendation based on confidence level."""
        
        if confidence >= 0.90:
            return {
                "action": "AUTO_SELECT",
                "user_action_required": False,
                "message": "Baseline auto-detected with high confidence",
                "allow_override": True
            }
        
        elif confidence >= 0.70:
            return {
                "action": "CONFIRM_SELECTION",
                "user_action_required": True,
                "message": "Baseline detected with moderate confidence - Please confirm or select alternative",
                "allow_override": True
            }
        
        else:
            return {
                "action": "MANUAL_SELECT",
                "user_action_required": True,
                "message": "Confidence too low - Please manually select the correct baseline",
                "allow_override": True
            }


# ============================================================================
# API ENDPOINT INTEGRATION
# ============================================================================

"""
Add this to api_server/main.py:

@app.post('/api/drift/auto-detect-baseline')
async def auto_detect_baseline(upload_file: UploadFile = File(...)):
    '''
    Auto-detect which baseline schema the uploaded file matches.
    Returns detection result with confidence, alternatives, and reasoning.
    '''
    try:
        file_bytes = await upload_file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        
        import pandas as pd
        import io
        uploaded_df = pd.read_csv(io.BytesIO(file_bytes), low_memory=False)
        
        detector = BaselineAutoDetector()
        detection_result = detector.detect_baseline(uploaded_df, filename=upload_file.filename)
        
        return {
            "generated_at": _utc_iso_now(),
            "detection": detection_result,
            "next_step": f"Use baseline '{detection_result['detected_baseline']}' for schema drift validation"
        }
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Baseline auto-detection failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
"""


# ============================================================================
# FRONTEND INTEGRATION
# ============================================================================

"""
FRONTEND WORKFLOW:

1. User uploads CSV file
   ↓
2. Frontend calls: POST /api/drift/auto-detect-baseline
   ↓
3. Backend returns:
   {
     "detection": {
       "detected_baseline": "products",
       "confidence": 0.95,
       "alternatives": [...]
       "reasoning": "..."
       "recommendation": {"action": "AUTO_SELECT", ...}
     }
   }
   ↓
4. Based on recommendation:
   
   IF action == "AUTO_SELECT":
     - Show: "✅ Detected: PRODUCTS (95% confident)"
     - Auto-fill baseline selector
     - Show "Continue" button
   
   IF action == "CONFIRM_SELECTION":
     - Show: "⚠️ Detected: PRODUCTS (78% confident)"
     - Show matched columns and reasoning
     - Show alternatives
     - Allow confirm or select different
   
   IF action == "MANUAL_SELECT":
     - Show: "❓ Detection inconclusive (45% confident)"
     - Show all baselines equally
     - REQUIRE user to select
     - Show why detection failed
   
   ↓
5. User confirms baseline
   ↓
6. Call: POST /api/drift/live-validate-upload
   with baseline_dataset_id = detected or user-selected baseline
"""
