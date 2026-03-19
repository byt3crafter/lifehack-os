"""ChatGPT OAuth provider.

Uses the OAuth sess_... token as a Bearer token against the standard
OpenAI completions API (https://api.openai.com/v1).  This is identical
in behaviour to OpenAIProvider except that the credentials come from the
OAuth flow rather than a manually-entered API key.
"""
import os

from .openai_provider import OpenAIProvider


class ChatGPTOAuthProvider(OpenAIProvider):
    """OpenAI-compatible provider authenticated via the ChatGPT OAuth flow.

    The ``sess_...`` access token issued by the PKCE flow is accepted by the
    standard OpenAI REST API as a Bearer token, so we can re-use the full
    OpenAIProvider implementation without change — we only need to swap out
    where the credentials come from.
    """

    def __init__(self):
        # OAuth token stored by the /auth/openai/callback route
        self.api_key = (
            self._get_setting('openai_oauth_token')
            or os.environ.get('OPENAI_OAUTH_TOKEN', '')
        )
        # Always use the official OpenAI endpoint for this provider
        self.base_url = 'https://api.openai.com/v1'
        # Default model — users can override via the standard settings key
        self.model = (
            self._get_setting('ai_openai_model')
            or os.environ.get('OPENAI_MODEL', 'gpt-4o')
        )

    def is_available(self) -> bool:
        return bool(self.api_key)
