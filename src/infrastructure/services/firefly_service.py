"""Firefly III data-fetching service.

Wraps the Firefly III REST API with:
- Per-user credential lookup from user_integrations table
- 5-minute in-process cache per (user_id, endpoint, params)
- Graceful error handling — never raises, always returns a safe default

All public methods accept an optional ``user_id`` parameter so each user
can connect to their own Firefly III instance.
"""
import json
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
        # Keys are (user_id, endpoint, frozenset(params)), values are (expires_at, data)
        self._cache: dict[tuple, tuple[float, Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self, user_id: Optional[int] = None) -> tuple[Optional[str], Optional[str]]:
        """Return (base_url, token) for the given user, or (None, None).

        Looks up user_integrations first (per-user). Falls back to the
        legacy plugin_registry path for backward compatibility.
        """
        try:
            from src.infrastructure.database import get_connection
            conn = get_connection()

            # --- Per-user integration (new path) ---
            if user_id is not None:
                row = conn.execute(
                    "SELECT enabled, config_json FROM user_integrations "
                    "WHERE user_id = ? AND integration_name = 'firefly'",
                    (user_id,),
                ).fetchone()
                if row and row['enabled']:
                    config = json.loads(row['config_json'] or '{}')
                    from src.infrastructure.plugins.firefly_plugin import FireflyPlugin
                    base_url = FireflyPlugin._base_url(config.get('api_url', ''))
                    token = config.get('api_token', '')
                    if base_url and token:
                        return base_url, token

            # --- Legacy fallback (plugin_registry / app_settings) ---
            from src.infrastructure.plugins import plugin_registry
            stored = plugin_registry.get_config('firefly', user_id=user_id)
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

    def _cache_key(self, endpoint: str, params: Optional[dict], user_id: Optional[int] = None) -> tuple:
        frozen_params = frozenset((params or {}).items())
        return (user_id, endpoint, frozen_params)

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

    def _api_get(self, endpoint: str, params: Optional[dict] = None,
                 user_id: Optional[int] = None) -> Optional[dict]:
        """Make a GET request to the Firefly III API.

        Returns the parsed JSON body on HTTP 200, or None on any error.
        Results are cached for _CACHE_TTL seconds.
        """
        key = self._cache_key(endpoint, params, user_id)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        base_url, token = self._get_config(user_id)
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

    def _api_post(self, endpoint: str, payload: dict,
                  user_id: Optional[int] = None) -> Optional[dict]:
        """Make a POST request to the Firefly III API.

        Returns the parsed JSON body on HTTP 200/201, or None on error.
        Invalidates cached data for this user after a successful write.
        """
        base_url, token = self._get_config(user_id)
        if not base_url or not token:
            return None

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
            resp = requests.post(
                f'{base_url}/api/v1{endpoint}',
                headers=headers,
                json=payload,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                self.invalidate_cache(user_id)
                return resp.json()
            logger.warning(
                "Firefly API POST %s returned HTTP %s: %s",
                endpoint, resp.status_code, resp.text[:300],
            )
            return None
        except requests.RequestException:
            logger.warning("Firefly API POST failed for %s", endpoint, exc_info=True)
            return None

    def _api_delete(self, endpoint: str,
                    user_id: Optional[int] = None) -> bool:
        """Make a DELETE request. Returns True on success."""
        base_url, token = self._get_config(user_id)
        if not base_url or not token:
            return False

        try:
            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }
            resp = requests.delete(
                f'{base_url}/api/v1{endpoint}',
                headers=headers,
                timeout=15,
            )
            if resp.status_code in (200, 204):
                self.invalidate_cache(user_id)
                return True
            logger.warning(
                "Firefly API DELETE %s returned HTTP %s", endpoint, resp.status_code,
            )
            return False
        except requests.RequestException:
            logger.warning("Firefly API DELETE failed for %s", endpoint, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_transaction(
        self,
        description: str,
        amount: float,
        tx_type: str = 'withdrawal',
        source_name: Optional[str] = None,
        destination_name: Optional[str] = None,
        source_id: Optional[str] = None,
        destination_id: Optional[str] = None,
        category: Optional[str] = None,
        date_str: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Optional[dict]:
        """Create a transaction in Firefly III.

        Returns the created transaction data or None on failure.
        """
        tx: dict[str, Any] = {
            'type': tx_type,
            'description': description,
            'amount': str(round(abs(amount), 2)),
            'date': date_str or date.today().isoformat(),
        }
        if source_name:
            tx['source_name'] = source_name
        if source_id:
            tx['source_id'] = str(source_id)
        if destination_name:
            tx['destination_name'] = destination_name
        if destination_id:
            tx['destination_id'] = str(destination_id)
        if category:
            tx['category_name'] = category
        if notes:
            tx['notes'] = notes

        # Defaults: use default account for the user
        if tx_type == 'withdrawal' and not source_id and not source_name:
            config = self._get_default_account_id(user_id)
            if config:
                tx['source_id'] = config
        elif tx_type == 'deposit' and not destination_id and not destination_name:
            config = self._get_default_account_id(user_id)
            if config:
                tx['destination_id'] = config

        payload = {
            'error_if_duplicate_hash': False,
            'transactions': [tx],
        }

        result = self._api_post('/transactions', payload, user_id)
        if result and result.get('data'):
            attrs = result['data'].get('attributes', {})
            created_tx = attrs.get('transactions', [{}])[0]
            return {
                'id': result['data']['id'],
                'description': created_tx.get('description', description),
                'amount': float(created_tx.get('amount', amount)),
                'type': created_tx.get('type', tx_type),
                'date': (created_tx.get('date') or '')[:10],
                'category': created_tx.get('category_name', ''),
                'source': created_tx.get('source_name', ''),
                'destination': created_tx.get('destination_name', ''),
            }
        return None

    def delete_transaction(self, transaction_id: str,
                           user_id: Optional[int] = None) -> bool:
        """Delete a transaction by ID."""
        return self._api_delete(f'/transactions/{transaction_id}', user_id)

    def _get_default_account_id(self, user_id: Optional[int] = None) -> Optional[str]:
        """Return the default account ID from config, or None."""
        try:
            from src.infrastructure.database import get_connection
            conn = get_connection()
            if user_id is not None:
                row = conn.execute(
                    "SELECT config_json FROM user_integrations "
                    "WHERE user_id = ? AND integration_name = 'firefly'",
                    (user_id,),
                ).fetchone()
                if row:
                    config = json.loads(row['config_json'] or '{}')
                    aid = config.get('default_account_id')
                    if aid:
                        return str(aid)
        except Exception:
            pass
        return None

    def is_connected(self, user_id: Optional[int] = None) -> bool:
        """Return True if the Firefly plugin is enabled and credentials are present."""
        base_url, token = self._get_config(user_id)
        return bool(base_url and token)

    def invalidate_cache(self, user_id: Optional[int] = None) -> None:
        """Clear cache entries. If user_id given, only that user's entries."""
        if user_id is None:
            self._cache.clear()
        else:
            keys_to_delete = [k for k in self._cache if k[0] == user_id]
            for k in keys_to_delete:
                del self._cache[k]

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_accounts(self, user_id: Optional[int] = None) -> list:
        """Return all asset and liability accounts with balances."""
        accounts: list[dict] = []

        asset_data = self._api_get('/accounts', {'type': 'asset'}, user_id)
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

        liability_data = self._api_get('/accounts', {'type': 'liabilities'}, user_id)
        if liability_data:
            for a in liability_data.get('data', []):
                attrs = a.get('attributes', {})
                bal = abs(float(attrs.get('current_balance', 0)))
                if bal == 0:
                    continue
                accounts.append({
                    'id': a['id'],
                    'name': attrs.get('name', ''),
                    'type': 'liability',
                    'balance': -bal,
                    'currency_code': attrs.get('currency_code', 'USD'),
                    'currency_symbol': attrs.get('currency_symbol', '$'),
                })

        return accounts

    def get_transactions(self, days: int = 30, limit: int = 50,
                         user_id: Optional[int] = None) -> list:
        """Return recent transactions in descending date order."""
        start = (date.today() - timedelta(days=days)).isoformat()
        end = date.today().isoformat()
        data = self._api_get(
            '/transactions',
            {'start': start, 'end': end, 'limit': limit},
            user_id,
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

    def get_monthly_spending(self, user_id: Optional[int] = None) -> dict:
        """Return spending by category for the current calendar month."""
        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

        data = self._api_get(
            '/transactions',
            {'start': start, 'end': end, 'limit': 500, 'type': 'withdrawal'},
            user_id,
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

    def get_budgets(self, user_id: Optional[int] = None) -> list:
        """Return Firefly budgets that have a limit set for the current month."""
        today = date.today()
        start = today.replace(day=1).isoformat()
        end = today.isoformat()

        data = self._api_get('/budgets', user_id=user_id)
        if not data:
            return []

        budgets: list[dict] = []
        for b in data.get('data', []):
            attrs = b.get('attributes', {})
            budget_id = b['id']

            limits = self._api_get(
                f'/budgets/{budget_id}/limits',
                {'start': start, 'end': end},
                user_id,
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

    def get_default_currency(self, user_id: Optional[int] = None) -> dict:
        """Return the user's default currency as {"code": "USD", "symbol": "$"}."""
        about = self._api_get('/about', user_id=user_id)
        if about:
            raw = about.get('data', {})
            if isinstance(raw, dict):
                attrs = raw.get('attributes', {})
                code = attrs.get('default_currency', '')
                if code:
                    return {'code': code, 'symbol': ''}

        accounts = self.get_accounts(user_id)
        if accounts:
            return {
                'code': accounts[0]['currency_code'],
                'symbol': accounts[0]['currency_symbol'],
            }
        return {'code': 'USD', 'symbol': '$'}


# Module-level singleton — importable anywhere without re-instantiation
firefly_service = FireflyService()
