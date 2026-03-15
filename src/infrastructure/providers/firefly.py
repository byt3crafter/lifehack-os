"""Firefly III provider for personal finance integration."""
import subprocess
import json
from typing import List, Optional, Dict
from datetime import datetime, date
from dataclasses import dataclass


@dataclass
class FireflyAccount:
    """Firefly III account representation."""
    id: str
    name: str
    type: str  # asset, expense, revenue
    balance: float
    currency: str = "MUR"


@dataclass
class FireflyTransaction:
    """Firefly III transaction representation."""
    id: str
    description: str
    amount: float
    type: str  # withdrawal, deposit, transfer
    date: date
    category: str = ""
    source_account: str = ""
    destination_account: str = ""


@dataclass
class FireflyConfig:
    """Firefly III configuration."""
    enabled: bool = False
    helper_path: str = "/home/d0v1k/clawd/skills/firefly/firefly.sh"
    default_account_id: str = "381"  # Savings Regular Account


class FireflyProvider:
    """
    Firefly III integration via firefly.sh helper.
    
    Provides access to accounts, transactions, and budgets.
    """
    
    provider_name = "firefly"
    
    def __init__(self, config: Optional[FireflyConfig] = None):
        self.config = config or FireflyConfig()
    
    def _run_helper(self, *args) -> Optional[str]:
        """Run firefly.sh helper command."""
        try:
            result = subprocess.run(
                [self.config.helper_path, *args],
                capture_output=True, text=True, timeout=30
            )
            return result.stdout if result.returncode == 0 else None
        except Exception:
            return None
    
    def test_connection(self) -> bool:
        """Test if firefly helper is available and working."""
        output = self._run_helper("accounts")
        return output is not None and len(output) > 0
    
    def get_accounts(self) -> List[FireflyAccount]:
        """Get all accounts."""
        output = self._run_helper("accounts", "--json")
        if not output:
            return []
        
        try:
            data = json.loads(output)
            return [
                FireflyAccount(
                    id=str(a.get("id", "")),
                    name=a.get("attributes", {}).get("name", ""),
                    type=a.get("attributes", {}).get("type", ""),
                    balance=float(a.get("attributes", {}).get("current_balance", 0)),
                    currency=a.get("attributes", {}).get("currency_code", "MUR")
                )
                for a in data.get("data", [])
            ]
        except (json.JSONDecodeError, KeyError):
            return []
    
    def get_balance(self, account_id: Optional[str] = None) -> Optional[float]:
        """Get account balance."""
        aid = account_id or self.config.default_account_id
        output = self._run_helper("balance", aid)
        if not output:
            return None
        
        try:
            # Parse "Balance: 123,456.78 MUR" format
            for line in output.strip().split("\n"):
                if "Balance" in line or aid in line:
                    # Extract number
                    parts = line.replace(",", "").split()
                    for p in parts:
                        try:
                            return float(p)
                        except ValueError:
                            continue
        except Exception:
            pass
        return None
    
    def get_recent_transactions(self, limit: int = 10) -> List[FireflyTransaction]:
        """Get recent transactions."""
        output = self._run_helper("transactions", "--json", "--limit", str(limit))
        if not output:
            return []
        
        try:
            data = json.loads(output)
            transactions = []
            for t in data.get("data", [])[:limit]:
                attrs = t.get("attributes", {})
                tx = attrs.get("transactions", [{}])[0]
                
                transactions.append(FireflyTransaction(
                    id=str(t.get("id", "")),
                    description=tx.get("description", ""),
                    amount=float(tx.get("amount", 0)),
                    type=tx.get("type", "withdrawal"),
                    date=date.fromisoformat(tx.get("date", "")[:10]) if tx.get("date") else date.today(),
                    category=tx.get("category_name", ""),
                    source_account=tx.get("source_name", ""),
                    destination_account=tx.get("destination_name", "")
                ))
            return transactions
        except (json.JSONDecodeError, KeyError, ValueError):
            return []
    
    def add_withdrawal(self, amount: float, description: str, 
                      account_id: Optional[str] = None,
                      category: Optional[str] = None) -> bool:
        """Add a withdrawal transaction."""
        aid = account_id or self.config.default_account_id
        args = ["withdraw", str(amount), description, aid]
        if category:
            args.append(category)
        
        output = self._run_helper(*args)
        return output is not None
    
    def add_deposit(self, amount: float, description: str,
                   account_id: Optional[str] = None) -> bool:
        """Add a deposit transaction."""
        aid = account_id or self.config.default_account_id
        output = self._run_helper("deposit", str(amount), description, aid)
        return output is not None
    
    def get_spending_summary(self, days: int = 30) -> Dict[str, float]:
        """Get spending by category for the last N days."""
        output = self._run_helper("spending", "--days", str(days), "--json")
        if not output:
            return {}
        
        try:
            data = json.loads(output)
            return {
                cat: float(amount)
                for cat, amount in data.items()
            }
        except (json.JSONDecodeError, ValueError):
            return {}
    
    def get_budget_status(self) -> Dict[str, dict]:
        """Get budget status (spent vs limit)."""
        output = self._run_helper("budgets", "--json")
        if not output:
            return {}
        
        try:
            data = json.loads(output)
            return {
                b.get("name", ""): {
                    "limit": float(b.get("limit", 0)),
                    "spent": float(b.get("spent", 0)),
                    "remaining": float(b.get("limit", 0)) - float(b.get("spent", 0))
                }
                for b in data.get("data", [])
            }
        except (json.JSONDecodeError, ValueError):
            return {}
