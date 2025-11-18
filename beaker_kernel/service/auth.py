from functools import lru_cache

import base64
import boto3
import json
import requests
from traitlets import Unicode, Bool

from jupyter_server.auth.authorizer import Authorizer, AllowAllAuthorizer
from jupyter_server.auth.identity import IdentityProvider, User

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

class CognitoHeadersIdentityProvider(IdentityProvider):

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

            return User(
                username=username,
                name=user_attributes.get('name', username),
                display_name=user_attributes.get('given_name', username),
            )
        except Exception as e:
            self.log.warning(f"Failed to get cognito user info for {user_id}: {e}")
            return None


    async def get_user(self, handler) -> User|None:
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


class CognitoAppManagedIdentityHeadersProvider(IdentityProvider):

    app_user_id_header = Unicode(
        default_value="X-Beaker-User-Id",
        config=True,
        help="Header containing user ID (app-level auth)",
    )

    app_access_token_header = Unicode(
        default_value="X-Beaker-Access-Token",
        config=True,
        help="Header containing access token (app-level auth)",
    )

    app_id_token_header = Unicode(
        default_value="X-Beaker-Id-Token",
        config=True,
        help="Header containing ID token (app-level auth)",
    )

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

    verify_jwt_signature = Bool(
        default_value=True,
        config=True,
        help="Whether the jwt signature should be verified",
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
            
            return User(
                username=username,
                name=name,
                display_name=display_name,
            )
        
        # Fallback: create basic User from user_id if no token payload
        return User(
            username=user_id,
            name=user_id,
            display_name=user_id,
        )


    async def get_user(self, handler) -> User | None:
        """Main entry point - handles app-level authentication"""
        # Extract auth info from app-level headers
        user_id = handler.request.headers.get(self.app_user_id_header, None)
        jwt_data = handler.request.headers.get(self.app_id_token_header, None)

        # Verify and decode ID token if provided
        token_payload = None
        if jwt_data:
            if self.verify_jwt_signature:
                token_payload = self._verify_cognito_id_token(jwt_data)
                if token_payload is None:
                    # Verification failed and was required
                    return None
            else:
                # Verification disabled, but still decode to extract user info
                try:
                    if pyjwt:
                        token_payload = pyjwt.decode(jwt_data, options={"verify_signature": False})
                except Exception as e:
                    self.log.debug(f"Could not decode token (verification disabled): {e}")

        # If no user_id, try extracting from token payload
        if not user_id:
            if token_payload:
                user_id = token_payload.get('sub') or token_payload.get('username')
            elif jwt_data:
                user_id = self._get_user_id_from_token(jwt_data)

        # if no user_id from headers/jwt, check for token-based auth (for internal requests)
        # this allows beaker-kernel internal API calls to work with jupyter token
        # SECURITY: this fallback is safe because:
        # 1. BeakerHub requires authentication on all /api/ routes via JWTAuthMiddleware
        # 2. If authenticated, BeakerHub always sets X-Beaker-* headers (checked above)
        # 3. Token fallback only triggers when NO user headers present (internal kernel calls)
        if not user_id:
            # check if request has valid jupyter token (query param or Authorization header)
            token_from_query = handler.get_argument('token', None)
            token_from_header = None
            auth_header = handler.request.headers.get('Authorization', '')
            if auth_header.startswith('token ') or auth_header.startswith('Token '):
                token_from_header = auth_header.split(' ', 1)[1]

            provided_token = token_from_query or token_from_header
            if provided_token:
                # compare with configured jupyter token
                import os
                expected_token = os.environ.get('JUPYTER_TOKEN', '')
                if expected_token and provided_token == expected_token:
                    # create a system user for token-authenticated requests
                    return User(
                        username='system',
                        name='System',
                        display_name='System (Token Auth)',
                    )

            # no valid authentication found
            return None

        # Create user from token payload (self-contained, no pool access needed)
        user = self._get_user(user_id, token_payload)
        return user
