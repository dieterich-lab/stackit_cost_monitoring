from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import json
from pathlib import Path
import uuid
from typing import Optional

import jwt
import requests
from pydantic import BaseModel

AUTH_CACHE_EXPIRATION = timedelta(minutes=10)
STACKIT_TOKEN_URL = 'https://service-account.api.stackit.cloud/token'


class _StackItRawCredentials(BaseModel):
    iss: str
    sub: str
    aud: str
    kid: str
    private_key: str


@dataclass
class _StackItBearerCredentials:
    token: str
    expiry: datetime


class AuthException(Exception):
    pass


class Auth:
    def __init__(self, sa_key_json_path: Path):
        self.sa_key_json_path = sa_key_json_path
        self._raw_credential_cache: Optional[_StackItRawCredentials] = None
        self._token_cache: Optional[_StackItBearerCredentials] = None

    def _get_raw_credentials(self) -> _StackItRawCredentials:
        try:
            if self._raw_credential_cache is None:
                with open(self.sa_key_json_path, 'r') as f:
                    credentials_data = json.load(f)['credentials']
                    self._raw_credential_cache = _StackItRawCredentials(
                        iss=credentials_data['iss'],
                        sub=credentials_data['sub'],
                        aud=credentials_data['aud'],
                        kid=credentials_data['kid'],
                        private_key=credentials_data['privateKey']
                    )
            return self._raw_credential_cache
        except Exception as e:
            error_context = f"Failed to load credentials from {self.sa_key_json_path}"
            raise AuthException(f"{error_context}: {e}")

    def _generate_jwt_token(self) -> str:
        credentials = self._get_raw_credentials()
        now = datetime.now(timezone.utc)

        payload = {
            'iss': credentials.iss,
            'sub': credentials.sub,
            'aud': credentials.aud,
            'iat': now,
            'exp': now + AUTH_CACHE_EXPIRATION,
            'jti': str(uuid.uuid4())
        }

        token = jwt.encode(
            payload,
            credentials.private_key,
            algorithm='RS512',
            headers={'kid': credentials.kid}
        )
        return token

    def _get_token_data(self) -> _StackItBearerCredentials:
        error_context = f"Failed to acquire bearer token from {STACKIT_TOKEN_URL}"
        jwt_token = self._generate_jwt_token()
        try:
            response = requests.post(
                STACKIT_TOKEN_URL,
                data={
                    'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
                    'assertion': jwt_token
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            response.raise_for_status()
        except Exception as e:
            raise AuthException(f"{error_context}: {e}")
        return _StackItBearerCredentials(
            token=response.json()['access_token'],
            expiry=datetime.now(timezone.utc) + AUTH_CACHE_EXPIRATION
        )

    def get_bearer_token(self) -> str:
        """Get a bearer token from StackIT."""
        if self._token_cache is None or self._token_cache.expiry < datetime.now(timezone.utc):
            self._token_cache = self._get_token_data()
        return self._token_cache.token
