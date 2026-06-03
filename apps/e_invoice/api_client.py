import logging
import time
from typing import Optional, Dict, Any
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)


class TaxAPIClient:

    STATUS_MAP = {
        'SUBMITTED': 'submitted',
        'VALID': 'valid',
        'INVALID': 'invalid',
        'CANCELLED': 'cancelled',
        'CANCELLED_WITH_CORRECTION': 'cancelled_correct',
    }

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout

        self._token = None
        self._token_expiry = None

    def _get_auth_token(self) -> str:
        if self._token and self._token_expiry and time.time() < self._token_expiry:
            return self._token

        auth_url = f"{self.base_url}/auth/token"

        try:
            response = requests.post(
                auth_url,
                data={
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=self.timeout
            )

            response.raise_for_status()
            data = response.json()

            self._token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)
            self._token_expiry = time.time() + expires_in - 60

            logger.info("Successfully obtained auth token")
            return self._token

        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to ETA API - check network or base_url")
            raise ValueError("تعذر الاتصال بخادم مصلحة الضرائب. تحقق من الاتصال بالإنترنت ورابط API")
        except Exception as e:
            logger.error(f"Failed to obtain auth token: {e}")
            raise ValueError(f"فشل في المصادقة مع مصلحة الضرائب: {e}")

    def submit_document(
        self,
        signed_xml: str,
        document_uuid: str
    ) -> Dict[str, Any]:
        try:
            token = self._get_auth_token()

            url = f"{self.base_url}/api/v1.0/documents"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/xml',
                'Accept': 'application/json',
            }

            params = {
                'documentId': document_uuid,
                'type': 'JSON',
            }

            logger.info(f"Submitting document {document_uuid} to ETA")

            response = requests.post(
                url,
                params=params,
                data=signed_xml.encode('utf-8'),
                headers=headers,
                timeout=self.timeout
            )

            response.raise_for_status()
            result = response.json()

            logger.info(f"Document submitted successfully: {result.get('submissionId')}")

            return {
                'success': True,
                'submission_id': result.get('submissionId'),
                'internal_id': result.get('internalId'),
                'uuid': result.get('uuid'),
                'status': self.STATUS_MAP.get(result.get('status', 'SUBMITTED'), 'submitted'),
                'received_date': result.get('receivedDate'),
                'qr_code': result.get('qrCode'),
                'raw_response': result,
            }

        except requests.exceptions.Timeout:
            logger.error("API request timeout")
            return {
                'success': False,
                'error': 'timeout',
                'error_message': 'انتهت مهلة الاتصال بخادم مصلحة الضرائب',
            }

        except requests.exceptions.ConnectionError:
            logger.error("Connection failed to ETA API")
            return {
                'success': False,
                'error': 'connection_failed',
                'error_message': 'تعذر الاتصال بمصلحة الضرائب. تحقق من الاتصال بالإنترنت',
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {
                'success': False,
                'error': 'request_failed',
                'error_message': str(e),
            }

    def query_document(self, uuid: str) -> Dict[str, Any]:
        try:
            token = self._get_auth_token()

            url = f"{self.base_url}/api/v1.0/documents/{uuid}"

            headers = {
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }

            logger.info(f"Querying document {uuid}")

            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()

            return {
                'success': True,
                'status': self.STATUS_MAP.get(result.get('status', 'UNKNOWN'), 'unknown'),
                'validation_results': result.get('validationResults', []),
                'raw_response': result,
            }

        except Exception as e:
            logger.error(f"Query document failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def cancel_document(
        self,
        uuid: str,
        reason: str
    ) -> Dict[str, Any]:
        try:
            token = self._get_auth_token()

            url = f"{self.base_url}/api/v1.0/documents/{uuid}"

            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            }

            body = {
                'cancellationReason': reason,
            }

            response = requests.delete(
                url,
                json=body,
                headers=headers,
                timeout=self.timeout
            )

            response.raise_for_status()

            return {
                'success': True,
                'status': 'cancelled',
                'raw_response': response.json() if response.content else {},
            }

        except Exception as e:
            logger.error(f"Cancel document failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }


def create_api_client(config) -> TaxAPIClient:
    return TaxAPIClient(
        base_url=config.api_base_url,
        client_id=config.client_id,
        client_secret=config.decrypt_client_secret(),
        timeout=config.timeout_seconds
    )
