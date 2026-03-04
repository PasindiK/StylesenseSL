import pandas as pd
from scripts.logger import setup_logger

logger = setup_logger(__name__)

class DataQualityValidator:
    """Validate data quality for each dataset and return structured results"""
    
    def __init__(self, dataframe, table_name):
        self.df = dataframe
        self.table_name = table_name
        self.hard_failures = []
        self.soft_warnings = []

    # -------------------------------------------------------------------------
    def check_completeness(self, column, threshold=0.99, hard=True):
        """Check if column has enough non-null values"""
        non_null_count = self.df[column].notna().sum()
        total_count = len(self.df)
        completeness_ratio = non_null_count / total_count if total_count > 0 else 0
        
        status = "PASS" if completeness_ratio >= threshold else "FAIL"
        message = f"{status} | Completeness ({column}): {completeness_ratio:.2%} (threshold: {threshold:.2%})"
        print(message)
        logger.info(message)
        
        if completeness_ratio < threshold:
            if hard:
                self.hard_failures.append(f"{column} completeness below threshold: {completeness_ratio:.2%}")
                logger.error(f"Hard failure: {column} has {total_count - non_null_count} missing values")
            else:
                self.soft_warnings.append(f"{column} completeness below soft threshold: {completeness_ratio:.2%}")
                logger.warning(f"Soft warning: {column} has {total_count - non_null_count} missing values")
        
        return completeness_ratio >= threshold

    # -------------------------------------------------------------------------
    def check_uniqueness(self, column, hard=False):
        """Check uniqueness of column values"""
        total_count = len(self.df)
        unique_count = self.df[column].nunique()
        duplicate_count = total_count - unique_count
        
        if duplicate_count > 0:
            message = f"WARNING | Uniqueness ({column}): {duplicate_count} duplicates found"
            print(message)
            logger.warning(message)
            if hard:
                self.hard_failures.append(f"{column} has {duplicate_count} duplicate values")
            else:
                self.soft_warnings.append(f"{column} has {duplicate_count} duplicate values")
            return False
        else:
            message = f"PASS | Uniqueness ({column}): All values unique"
            print(message)
            logger.info(message)
            return True

    # -------------------------------------------------------------------------
    def check_validity(self, column, valid_values, hard=False):
        """Check if column values are in valid set"""
        invalid_records = self.df[~self.df[column].isin(valid_values)]
        invalid_count = len(invalid_records)
        total_count = len(self.df)
        validity_ratio = (total_count - invalid_count) / total_count if total_count > 0 else 0
        
        status = "PASS" if validity_ratio >= 0.99 else "FAIL"
        message = f"{status} | Validity ({column}): {validity_ratio:.2%} valid | {invalid_count} invalid records"
        print(message)
        logger.info(message)
        
        if invalid_count > 0:
            msg = f"{column} has invalid values: {invalid_records[column].unique()}"
            if hard:
                self.hard_failures.append(msg)
                logger.error(f"Hard failure: {msg}")
            else:
                self.soft_warnings.append(msg)
                logger.warning(f"Soft warning: {msg}")
        
        return validity_ratio >= 0.99

    # -------------------------------------------------------------------------
    def check_range(self, column, min_val, max_val, hard=False):
        """Check if numeric column is within range"""
        out_of_range = self.df[(self.df[column] < min_val) | (self.df[column] > max_val)]
        out_of_range_count = len(out_of_range)
        
        status = "PASS" if out_of_range_count == 0 else "WARNING"
        message = f"{status} | Range ({column}): {out_of_range_count} values outside [{min_val}, {max_val}]"
        print(message)
        logger.info(message)
        
        if out_of_range_count > 0:
            msg = f"{column} has {out_of_range_count} values out of range [{min_val}, {max_val}]"
            if hard:
                self.hard_failures.append(msg)
                logger.error(f"Hard failure: {msg}")
            else:
                self.soft_warnings.append(msg)
                logger.warning(f"Soft warning: {msg}")
        
        return out_of_range_count == 0

    # -------------------------------------------------------------------------
    # TABLE-SPECIFIC CHECKS
    # -------------------------------------------------------------------------
    def run_product_checks(self):
        self.check_completeness('product_id', 1.0, hard=True)
        self.check_completeness('price_LKR', 0.99, hard=True)
        self.check_completeness('category', 0.99, hard=False)
        self.check_uniqueness('product_id', hard=True)
        self.check_validity('category', [
            'BEACH WEAR', 'COATS', 'T-SHIRTS', 'CARDIGANS', 'BLAZERS',
            'SWEATSHIRTS', 'JOGGERS & PANTS', 'CHINOS', 'DENIM JACKETS'
        ], hard=False)
        self.check_range('price_LKR', 0, 100000, hard=True)
        self.check_range('stock_count', 0, 1000, hard=False)
        return self.summary()

    def run_users_checks(self):
        self.check_completeness('user_id', 1.0, hard=True)
        self.check_completeness('email', 0.99, hard=False)
        self.check_completeness('name', 0.99, hard=False)
        self.check_uniqueness('user_id', hard=True)
        self.check_uniqueness('email', hard=False)
        return self.summary()

    def run_transactions_checks(self):
        self.check_completeness('transaction_id', 1.0, hard=True)
        self.check_completeness('final_amount', 0.99, hard=True)
        self.check_uniqueness('transaction_id', hard=True)
        self.check_range('quantity', 1, 100, hard=False)
        self.check_range('final_amount', 0, 1000000, hard=False)
        self.check_validity('transaction_status', [
            'Completed', 'Pending', 'Failed', 'Cancelled', 'Returned'
        ], hard=False)
        self.check_validity('payment_method', [
            'Credit Card', 'Debit Card', 'Bank Transfer', 'COD', 'Digital Wallet'
        ], hard=False)
        return self.summary()

    # -------------------------------------------------------------------------
    # SUMMARY OUTPUT
    # -------------------------------------------------------------------------
    def summary(self):
        """Return structured result"""
        total_issues = len(self.hard_failures) + len(self.soft_warnings)
        success_rate = 1 - len(self.hard_failures) / max(1, total_issues)
        return {
            "hard_failures": self.hard_failures,
            "soft_warnings": self.soft_warnings,
            "is_acceptable": len(self.hard_failures) == 0
        }

    # -------------------------------------------------------------------------
    # RUN CHECKS BASED ON TABLE NAME
    # -------------------------------------------------------------------------
    def run_checks(self):
        if self.table_name.lower() == "products":
            return self.run_product_checks()
        elif self.table_name.lower() == "users":
            return self.run_users_checks()
        elif self.table_name.lower() == "transactions":
            return self.run_transactions_checks()
        else:
            logger.warning(f"No specific DQ checks defined for {self.table_name}, running generic completeness")
            for col in self.df.columns:
                self.check_completeness(col, 0.99, hard=False)
            return self.summary()
