from functools import lru_cache

import base64
import boto3
import json
import requests
import os
from traitlets import Unicode, Bool

from jupyter_server.auth.authorizer import Authorizer, AllowAllAuthorizer

from . import BeakerIdentityProvider, BeakerUser

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

try:
    from botocore.exceptions import ClientError
except ImportError:
    ClientError = None

class CognitoHeadersIdentityProvider(BeakerIdentityProvider):

    cognito_jwt_header = Unicode(
        default_value="X-Amzn-Oidc-Data",
        config=True,
        help="Header containing the cognito JWT encoded grants",
    )

    cognito_identity_header = Unicode(
        default_value="X-Amzn-Oidc-Identity",
        config=True,
        help="Header containing the cognito user identity",
    )

    cognito_accesstoken_header = Unicode(
        default_value="X-Amzn-Oidc-Accesstoken",
        config=True,
        help="Header containing the cognito active access token",
    )

    user_pool_id = Unicode(
        default_value="",
        config=True,
        help="AWS Cognito User Pool ID",
    )

    verify_jwt_signature = Bool(
        default_value=True,
        config=True,
        help="Whether the jwt signature from cognito should be verified",
    )


    @lru_cache
    def _get_elb_key(self, region: str, kid: str) -> str:
        key_url = f"https://public-keys.auth.elb.{region}.amazonaws.com/{kid}"
        pubkey = requests.get(key_url).text
        return pubkey


    @lru_cache
    def _verify_jwt(self, jwt_data: str):
        if pyjwt is not None:
            header, body = [json.loads(base64.b64decode(f).decode('utf-8')) for f in jwt_data.split('.')[0:2]]
            self.log.warning(header)
            self.log.warning(body)
            signer: str = header.get("signer")
            region = signer.split(':')[3]
            kid: str = header.get("kid")
            pubkey = self._get_elb_key(region, kid)
            payload = pyjwt.decode(jwt_data, key=pubkey, algorithms=["ES256", "RS256"])
            self.log.warning(payload)
            return payload


    @lru_cache
    def _get_user(self, user_id, access_token):
        # Access token is provided as an argument to ensure that auth info is refetched (misses cache) if the access token changes.
        try:
            cognito_client = boto3.client('cognito-idp')
            response = cognito_client.admin_get_user(
                UserPoolId=self.user_pool_id,
                Username=user_id
            )

            user_attributes = {attr['Name']: attr['Value'] for attr in response.get('UserAttributes', [])}
            username = user_attributes.get('preferred_username') or user_attributes.get('email') or user_id

            return BeakerUser(
                username=username,
                name=user_attributes.get('name', username),
                display_name=user_attributes.get('given_name', username),
            )
        except Exception as e:
            self.log.warning(f"Failed to get cognito user info for {user_id}: {e}")
            return None


    async def get_user(self, handler) -> BeakerUser|None:
        jwt_data: str = handler.request.headers.get(self.cognito_jwt_header, None)
        user_id: str = handler.request.headers.get(self.cognito_identity_header, None)
        access_token: str = handler.request.headers.get(self.cognito_accesstoken_header, None)

        match pyjwt, self.verify_jwt_signature, jwt_data:
            case (None, _, _):
                self.log.warning("Unable to verify JWT signature as package 'pyjwt' is not installed.")
            case (_, _, None):
                self.log.warning("Unable to verify JWT signature as it is not found.")
            case (_, False, _):
                self.log.info("Skipping checking JWT signature due to configuration.")
            case (_, True, str()):
                try:
                    self._verify_jwt(jwt_data)
                except pyjwt.exceptions.InvalidTokenError as e:
                    self.log.warning(f"Error attempting to verify JWT token: {e}")
                    return None

        if not user_id or not access_token:
            return None

        user = self._get_user(user_id, access_token)
        return user


# TODO remove Headers from class name. Not now since we're using this name in BeakerHub.
class CognitoAppManagedIdentityHeadersProvider(BeakerIdentityProvider):
    """
    Identity provider for app-managed authentication via cookies.
    Reads JWT tokens from httpOnly cookies set by auth.
    Supports automatic token refresh using refresh tokens when access/id tokens expire.
    """

    user_pool_id = Unicode(
        default_value="",
        config=True,
        help="AWS Cognito User Pool ID (required if verify_jwt_signature=True - used to fetch JWKS and verify issuer. Not needed if verification is disabled)",
    )

    cognito_region = Unicode(
        default_value="",
        config=True,
        help="AWS Cognito Region (optional, auto-detected from user_pool_id if not set)",
    )

    cognito_client_id = Unicode(
        default_value="",
        config=True,
        help="AWS Cognito Client ID (required for token refresh)",
    )

    verify_jwt_signature = Bool(
        default_value=True,
        config=True,
        help="Whether the jwt signature should be verified",
    )

    enable_token_refresh = Bool(
        default_value=True,
        config=True,
        help="Whether to automatically refresh expired tokens using refresh token",
    )

    fqdn = Unicode(
        default_value="",
        config=True,
        help="Fully qualified domain name (e.g., 'labs.beakerhub.com'). Used to determine if __Host- cookie prefix should be used.",
    )

    def _is_localhost(self) -> bool:
        """Check if FQDN is localhost or 127.0.0.1"""
        fqdn = self.fqdn.lower() if self.fqdn else ""
        return "localhost" in fqdn or "127.0.0.1" in fqdn

    def _get_cookie_prefix(self) -> str:
        """
        Get cookie prefix based on environment.

        Returns '__Host-' for production (non-localhost) environments.
        Returns empty string for localhost.

        The __Host- prefix provides enhanced security:
        - Prevents cookie injection from subdomains
        - Requires secure=True (HTTPS)
        - Requires path="/"
        """
        return "" if self._is_localhost() else "__Host-"

    def _get_cookie(self, handler, key: str) -> str | None:
        """
        Get cookie value with automatic __Host- prefix handling.

        Args:
            handler: Tornado request handler
            key: Cookie name (without prefix, e.g., 'access_token')

        Returns:
            Cookie value or None if not found
        """
        prefix = self._get_cookie_prefix()
        cookie_name = f"{prefix}{key}"

        try:
            # Try using get_cookie method (newer Tornado versions)
            value = handler.get_cookie(cookie_name)
            return value
        except Exception as e:
            # Fallback for older Tornado versions
            cookie_obj = handler.request.cookies.get(cookie_name)
            value = cookie_obj.value if cookie_obj else None
            return value

    def _set_cookie(self, handler, key: str, value: str, max_age: int = 3600) -> None:
        """
        Set cookie with automatic __Host- prefix handling and security settings.

        Args:
            handler: Tornado request handler
            key: Cookie name (without prefix, e.g., 'access_token')
            value: Cookie value (the JWT token)
            max_age: Cookie expiration in seconds (default: 1 hour)
        """
        prefix = self._get_cookie_prefix()
        cookie_name = f"{prefix}{key}"
        is_localhost = self._is_localhost()

        handler.set_cookie(
            name=cookie_name,
            value=value,
            expires_days=None,  # Use max_age instead
            domain=None,  # Required for __Host- prefix
            path="/",  # Required for __Host- prefix
            secure=not is_localhost,  # HTTPS only in production
            httponly=True,  # JavaScript cannot access
            samesite="Strict",  # CSRF protection
            max_age=max_age,
        )

    @lru_cache
    def _get_cognito_jwks(self, user_pool_id: str, region: str) -> dict:
        """Fetch JWKS from Cognito well-known endpoint"""
        jwks_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
        response = requests.get(jwks_url)
        response.raise_for_status()
        return response.json()

    def _get_cognito_region(self) -> str:
        """Get Cognito region from config or default to us-east-1"""
        if self.cognito_region:
            return self.cognito_region

        # Default to us-east-1 if not set
        return "us-east-1"

    def _refresh_tokens(self, refresh_token: str) -> tuple[str | None, str | None, dict | None]:
        """
        Refresh access and id tokens using refresh token.

        Args:
            refresh_token: The refresh token from cookies

        Returns:
            Tuple of (new_access_token, new_id_token, user_info) or (None, None, None) on failure
        """
        if not self.enable_token_refresh:
            self.log.debug("Token refresh is disabled")
            return None, None, None

        if not self.cognito_client_id:
            self.log.warning("Cannot refresh tokens: cognito_client_id not configured")
            return None, None, None

        if ClientError is None:
            self.log.warning("Cannot refresh tokens: botocore not installed")
            return None, None, None

        try:
            self.log.info("Attempting to refresh tokens with Cognito")
            region = self._get_cognito_region()
            cognito_client = boto3.client('cognito-idp', region_name=region)

            auth_response = cognito_client.initiate_auth(
                ClientId=self.cognito_client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )

            auth_result = auth_response.get('AuthenticationResult', {})
            new_access_token = auth_result.get('AccessToken')
            new_id_token = auth_result.get('IdToken')

            if not new_access_token or not new_id_token:
                self.log.error("Cognito refresh did not return new tokens")
                return None, None, None

            self.log.info("Token refresh: Cognito returned new tokens, validating them")

            # Verify the new tokens
            id_token_payload = None
            if self.verify_jwt_signature:
                id_token_payload = self._verify_cognito_id_token(new_id_token)
                if id_token_payload is None:
                    self.log.error("Token refresh: new ID token validation failed")
                    return None, None, None
            else:
                # If verification disabled, still decode to extract user info
                try:
                    if pyjwt:
                        id_token_payload = pyjwt.decode(new_id_token, options={"verify_signature": False})
                except Exception as e:
                    self.log.error(f"Token refresh: failed to decode new ID token: {e}")
                    return None, None, None

            # Extract user info from new ID token
            user_info = {
                "sub": id_token_payload.get("sub"),
                "email": id_token_payload.get("email"),
                "cognito_username": id_token_payload.get("cognito:username"),
            }

            self.log.info(f"Token refresh successful for user: {user_info.get('email')}")
            return new_access_token, new_id_token, user_info

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            self.log.error(f"Cognito refresh failed - {error_code}: {error_message}")
            return None, None, None
        except Exception as e:
            self.log.error(f"Unexpected error during token refresh: {type(e).__name__} - {str(e)}")
            return None, None, None

    def _verify_cognito_id_token(self, jwt_data: str) -> dict | None:
        """Verify Cognito ID token using JWKS"""
        if not self.user_pool_id:
            if self.verify_jwt_signature:
                self.log.warning("Cannot verify Cognito ID token: user_pool_id not set")
            return None

        if pyjwt is None:
            if self.verify_jwt_signature:
                self.log.warning("Cannot verify Cognito ID token: pyjwt not installed")
            return None

        try:
            # Decode header to get kid
            header_data = jwt_data.split('.')[0]
            header = json.loads(base64.urlsafe_b64decode(header_data + '==').decode('utf-8'))
            kid = header.get('kid')

            if not kid:
                self.log.warning("JWT header missing 'kid' claim")
                return None

            # Get region
            region = self._get_cognito_region()

            # Fetch JWKS
            try:
                jwks = self._get_cognito_jwks(self.user_pool_id, region)
            except Exception as e:
                self.log.error(f"Failed to fetch Cognito JWKS: {e}")
                if self.verify_jwt_signature:
                    return None
                # If verification disabled, decode without verification
                return pyjwt.decode(jwt_data, options={"verify_signature": False})

            # Find the key with matching kid
            public_key = None
            for key in jwks.get('keys', []):
                if key.get('kid') == kid:
                    # Convert JWK to PEM format for pyjwt
                    from cryptography.hazmat.primitives.asymmetric import rsa
                    from cryptography.hazmat.backends import default_backend
                    import cryptography.hazmat.primitives.serialization as serialization

                    # Extract RSA components from JWK
                    n = int.from_bytes(base64.urlsafe_b64decode(key['n'] + '=='), 'big')
                    e = int.from_bytes(base64.urlsafe_b64decode(key['e'] + '=='), 'big')

                    # Build RSA public key
                    public_key = rsa.RSAPublicNumbers(e, n).public_key(default_backend())
                    break

            if not public_key:
                self.log.warning(f"No matching key found for kid: {kid}")
                if self.verify_jwt_signature:
                    return None
                return pyjwt.decode(jwt_data, options={"verify_signature": False})

            # Verify and decode token
            if self.verify_jwt_signature:
                # Get expected issuer and audience
                expected_issuer = f"https://cognito-idp.{region}.amazonaws.com/{self.user_pool_id}"
                # Decode without verification first to get audience
                unverified = pyjwt.decode(jwt_data, options={"verify_signature": False})
                expected_audience = unverified.get('aud') or self.user_pool_id

                payload = pyjwt.decode(
                    jwt_data,
                    public_key,
                    algorithms=["RS256"],
                    issuer=expected_issuer,
                    audience=expected_audience,
                )
            else:
                payload = pyjwt.decode(jwt_data, options={"verify_signature": False})

            return payload

        except pyjwt.exceptions.InvalidTokenError as e:
            self.log.warning(f"Invalid Cognito ID token: {e}")
            if self.verify_jwt_signature:
                return None
            # If verification disabled, try to decode anyway
            try:
                return pyjwt.decode(jwt_data, options={"verify_signature": False})
            except:
                return None
        except Exception as e:
            self.log.error(f"Error verifying Cognito ID token: {e}")
            if self.verify_jwt_signature:
                return None
            try:
                return pyjwt.decode(jwt_data, options={"verify_signature": False})
            except:
                return None

    def _get_user_id_from_token(self, jwt_data: str) -> str | None:
        """Extract user_id from JWT claims"""
        if not jwt_data or pyjwt is None:
            return None
        try:
            # Decode without verification to get claims
            payload = pyjwt.decode(jwt_data, options={"verify_signature": False})
            # Cognito ID tokens typically have 'sub' claim for user ID
            return payload.get('sub') or payload.get('username')
        except Exception as e:
            self.log.debug(f"Could not extract user_id from token: {e}")
            return None



    def _get_user(self, user_id: str, token_payload: dict | None = None):
        """
        Create User from user_id and optional token payload.
        Token payload contains self-contained user info from Cognito ID token.
        No pool access needed - tokens are self-contained.
        """
        # If we have token payload, extract user info from it
        if token_payload:
            username = (
                token_payload.get('preferred_username') or
                token_payload.get('email') or
                token_payload.get('sub') or
                user_id
            )
            name = token_payload.get('name') or username
            display_name = token_payload.get('given_name') or token_payload.get('name') or username

            return BeakerUser(
                username=username,
                name=name,
                display_name=display_name,
            )

        # Fallback: create basic User from user_id if no token payload
        return BeakerUser(
            username=user_id,
            name=user_id,
            display_name=user_id,
        )


    async def get_user(self, handler) -> BeakerUser | None:
        """
        Main entry point - handles app-level authentication via cookies.
        Automatically refreshes expired tokens using refresh token if available.
        """
        # Read JWT tokens from cookies with __Host- prefix support
        id_token = self._get_cookie(handler, 'id_token')
        access_token = self._get_cookie(handler, 'access_token')
        refresh_token = self._get_cookie(handler, 'refresh_token')

        jwt_data = id_token
        user_id = None  # will be extracted from jwt_data

        # Verify and decode ID token if provided
        token_payload = None
        token_expired = False

        # Check if tokens are missing (cookies expired due to max_age) or invalid
        if not id_token or not access_token:
            # Tokens missing - cookies likely expired
            self.log.debug("Access or ID token missing (cookies may have expired)")
            token_expired = True
        elif jwt_data:
            # Tokens present - verify them
            if self.verify_jwt_signature:
                token_payload = self._verify_cognito_id_token(jwt_data)
                if token_payload is None:
                    # Verification failed - might be expired
                    self.log.debug("ID token verification failed, might be expired")
                    token_expired = True
            else:
                # Verification disabled, but still decode to extract user info
                try:
                    if pyjwt:
                        token_payload = pyjwt.decode(jwt_data, options={"verify_signature": False})
                except Exception as e:
                    self.log.debug(f"Could not decode token (verification disabled): {e}")
                    token_expired = True

        # If tokens are missing/expired and we have a refresh token, try to refresh
        if token_expired and refresh_token and self.enable_token_refresh:
            self.log.info("Attempting automatic token refresh")
            new_access_token, new_id_token, user_info = self._refresh_tokens(refresh_token)

            if new_access_token and new_id_token and user_info:
                self.log.info(f"Token refresh successful for user: {user_info.get('email')}")

                # Update cookies with new tokens
                # Access and ID tokens typically expire in 1 hour
                self._set_cookie(handler, 'access_token', new_access_token, max_age=3600)
                self._set_cookie(handler, 'id_token', new_id_token, max_age=3600)

                # Create user from refreshed token info
                user_id = user_info.get('sub')

                # Decode the new ID token to get full payload
                try:
                    if pyjwt:
                        token_payload = pyjwt.decode(new_id_token, options={"verify_signature": False})
                except Exception as e:
                    self.log.warning(f"Could not decode refreshed token: {e}")
                    token_payload = None

                # Create user with refreshed data
                user = self._get_user(user_id, token_payload)
                return user
            else:
                self.log.warning("Token refresh failed - refresh token invalid or expired")
                return None

        # If no valid token payload and no refresh attempted, fail auth
        if not token_payload:
            self.log.debug("No valid token payload available - authentication failed")
            return None

        # Extract user_id from token payload
        if not user_id:
            user_id = token_payload.get('sub') or token_payload.get('username')

        if not user_id:
            self.log.debug("Could not extract user_id from token")
            return None

        # Create user from token payload (self-contained, no pool access needed)
        user = self._get_user(user_id, token_payload)
        self.log.info(f"Authentication successful for user: {user.username}")
        return user
