"""Firefly III data-fetching service.

Wraps the Firefly III REST API with:
- Connection-check guard (returns empty data if plugin is not enabled)
- 5-minute in-process cache per endpoint + params
- Graceful error handling — never raises, always returns a safe default
"""
import logging
import time
from datetime import date, timedelta
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # 5 minutes


class FireflyService:
    """Stateless-style service that fetches from the Firefly III REST API."""

    def __init__(self) -> None:
        # Keys are (endpoint, frozenset(params.items())), values are (expires_at, data)
        self._cache: dict[tuple, tuple[float, Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self) -> tuple[Optional[str], Optional[str]]:
        """Return (base_url, token) from the plugin registry, or (None, None)."""
        try:
            from src.infrastructure.plugins import plugin_registry
            stored = plugin_registry.get_config('firefly')
            if not stored.get('enabled'):
                return None, None
            config = stored.get('config', {})
            from src.infrastructure.plugins.firefly_plugin import FireflyPlugin
            base_url = FireflyPlugin._base_url(config.get('api_url', ''))
            token = config.get('api_token', '')
            if not base_url or not token:
                return None, None
            return base_url, token
        except Exception:
            logger.debug("Failed to load Firefly config", exc_info=True)
            return None, None

    def _cache_key(self, endpoint: str, params: Optional[dict]) -> tuple:
        frozen_params = frozenset((params or {}).items())
        return (endpoint, frozen_params)

    def _cache_get(self, key: tuple) -> Any:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, data = entry
        if time.monotonic() > expires_at:
            del self._cache[key]
            return None
        return data

    def _cache_set(self, key: tuple, data: Any) -> None:
        self._cache[key] = (time.monotonic() + _CACHE_TTL, data)

    def _api_get(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """Make a GET request to the Firefly III API.

        Returns the parsed JSON body on HTTP 200, or None on any error.
        Results are cached for _CACHE_TTL seconds.
        """
        key = self._cache_key(endpoint, params)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        base_url, token = self._get_config()
        if not base_url or not token:
            return None

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }
            resp = requests.get(
                f'{base_url}/api/v1{endpoint}',
                headers=headers,
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._cache_set(key, data)
                return data
            logger.warning(
                "Firefly API %s returned HTTP %s", endpoint, resp.status_code
            )
            return None
        except requests.RequestException:
            logger.warning("Firefly API request failed for %s", endpoint, exc_info=True)
            return None

    def is_connected(self) -> bool:
        """Return True if the Firefly plugin is enabled and credentials are present."""
        base_url, token = self._get_config()
        return bool(base_url and token)

    def invalidate_cache(self) -> None:
        """Clear the entire in-process cache (useful after writes)."""
        self._cache.clear()

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_accounts(self) -> list:
        """Return all asset and liability accounts with balances.

        Each entry::

            {
                "id": "1",
                "name": "Checking",
                "type": "asset" | "liability",
                "balance": 1234.56,
                "currency_code": "USD",
                "currency_symbol": "$",
            }
        """
        accounts: list[dict] = []

        asset_data = self._api_get('/accounts', {'type': 'asset'})
        if asset_data:
            for a in asset_data.get('data', []):
                attrs = a.get('attributes', {})
                accounts.append({
                    'id': a['id'],
                    'name': attrs.get('name', ''),
                    'type': attrs.get('type', 'asset'),
                    'balance': float(attrs.get('current_balance', 0)),
                    'currency_code': attrs.get('currency_code', 'USD'),
                    'currency_symbol': attrs.get('currency_symbol', '$'),
                })

        liability_data = self._api_get('/accounts', {'type': 'liabilities'})
        if liability_data:
            for a in liability_data.get('data', []):
                attrs = a.get('attributes', {})
                accounts.append({
                    'id': a['id'],
                    'name': attrs.get('name', ''),
                    'type': 'liability',
                    # Liabilities are shown as negative to reflect net-worth impact
                    'balance': -abs(float(attrs.get('current_balance', 0))),
                    'currency_code': attrs.get('currency_code', 'USD'),
                    'currency_symbol': attrs.get('currency_symbol', '$'),
                })

        return accounts

    def get_transactions(self, days: int = 30, limit: int = 50) -> list:
        """Return recent transactions in descending date order.

        Args:
            days:  How many days back to look.
            limit: Maximum number of transactions to return.

        Each entry::

            {
                "id": "42",
                "date": "2026-03-15",
                "description": "Grocery run",
                "amount": 87.40,
                "type": "withdrawal",
                "category": "Food",
                "source": "Checking",
                "destination": "SuperMart",
                "currency_code": "USD",
                "currency_symbol": "$",
            }
        """
        start = (date.today() - timedelta(days=days)).isoformat()
        end = date.today().isoformat()
        data = self._api_get(
            '/transactions',
            {'start': start, 'end': end, 'limit': limit},
        )
        if not data:
            return []

        txns: list[dict] = []
        for t in data.get('data', []):
            attrs = t.get('attributes', {})
            tx = attrs.get('transactions', [{}])[0]
            txns.append({
                'id': t['id'],
                'date': (tx.get('date') or '')[:10],
                'description': tx.get('description', ''),
                'amount': float(tx.get('amount', 0)),
                'type': tx.get('type', 'withdrawal'),
                'category': tx.get('category_name') or '',
                'source': tx.get('source_name') or '',
                'destination': tx.get('destination_name') or '',
                'currency_code': tx.get('currency_code', 'USD'),
                'currency_symbol': tx.get('currency_symbol', '$'),
            })
        return txns

    def get_monthly_spending(self) -> dict:
        """Return spending by category for the current calendar month.

        Returns::

            {
                "categories": {"Food": 487.00, "Transport": 120.50, ...},
                "total": 2237.50,
                "currency": "USD",
            }
        """
        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

        data = self._api_get(
            '/transactions',
            {'start': start, 'end': end, 'limit': 500, 'type': 'withdrawal'},
        )
        if not data:
            return {'categories': {}, 'total': 0.0, 'currency': 'USD'}

        categories: dict[str, float] = {}
        total = 0.0
        currency = 'USD'

        for t in data.get('data', []):
            tx = t.get('attributes', {}).get('transactions', [{}])[0]
            cat = tx.get('category_name') or 'Uncategorized'
            amount = abs(float(tx.get('amount', 0)))
            currency = tx.get('currency_code', currency)
            categories[cat] = round(categories.get(cat, 0.0) + amount, 2)
            total += amount

        return {
            'categories': categories,
            'total': round(total, 2),
            'currency': currency,
        }

    def get_budgets(self) -> list:
        """Return Firefly budgets that have a limit set for the current month.

        Each entry::

            {
                "id": "3",
                "name": "Food",
                "limit": 600.00,
                "spent": 487.00,
            }
        """
        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

        data = self._api_get('/budgets')
        if not data:
            return []

        budgets: list[dict] = []
        for b in data.get('data', []):
            attrs = b.get('attributes', {})
            budget_id = b['id']

            limits = self._api_get(
                f'/budgets/{budget_id}/limits',
                {'start': start, 'end': end},
            )
            limit_amount = 0.0
            spent = 0.0
            if limits and limits.get('data'):
                for lim in limits['data']:
                    la = lim.get('attributes', {})
                    limit_amount += float(la.get('amount', 0))
                    spent += abs(float(la.get('spent', 0)))

            if limit_amount > 0:
                budgets.append({
                    'id': budget_id,
                    'name': attrs.get('name', ''),
                    'limit': round(limit_amount, 2),
                    'spent': round(spent, 2),
                })

        return budgets

    def get_default_currency(self) -> dict:
        """Return the user's default currency as {"code": "USD", "symbol": "$"}.

        Falls back to the first account's currency if the /about endpoint does
        not expose it (older Firefly III versions).
        """
        about = self._api_get('/about')
        if about:
            raw = about.get('data', {})
            if isinstance(raw, dict):
                attrs = raw.get('attributes', {})
                code = attrs.get('default_currency', '')
                if code:
                    return {'code': code, 'symbol': ''}

        accounts = self.get_accounts()
        if accounts:
            return {
                'code': accounts[0]['currency_code'],
                'symbol': accounts[0]['currency_symbol'],
            }
        return {'code': 'USD', 'symbol': '$'}


# Module-level singleton — importable anywhere without re-instantiation
firefly_service = FireflyService()
