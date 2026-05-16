"""
عميل API مصلحة الضرائب المصرية
E-Invoice API Client
"""
import logging
import time
from typing import Optional, Dict, Any
from decimal import Decimal

logger = logging.getLogger(__name__)

# Try importing requests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests library not installed")


class TaxAPIClient:
    """
    عميل للتواصل مع API مصلحة الضرائب المصرية
    
   _supported endpoints:
    - Submit Document (POST /api/v1.0/documents)
    - Query Document (GET /api/v1.0/documents/{uuid})
    - Cancel Document (DELETE /api/v1.0/documents/{uuid})
    """
    
    # حالات الوثيقة من API
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
        """
        Initialize API client
        
        Args:
            base_url: رابط API الأساسي (مثال: https://api.eta.gov.eg)
            client_id: معرف العميل
            client_secret: سر العميل
            timeout: مهلة الانتظار بالثواني
        """
        self.base_url = base_url.rstrip('/')
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        
        self._token = None
        self._token_expiry = None
        
        if not REQUESTS_AVAILABLE:
            logger.warning("requests library not available - using mock mode")
    
    def _get_auth_token(self) -> str:
        """الحصول على token المصادقة"""
        
        if not REQUESTS_AVAILABLE:
            return "MOCK_TOKEN"
        
        # Check if we have a valid token
        if self._token and self._token_expiry and time.time() < self._token_expiry:
            return self._token
        
        # Request new token
        try:
            auth_url = f"{self.base_url}/auth/token"
            
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
            self._token_expiry = time.time() + expires_in - 60  # 60 second buffer
            
            logger.info("Successfully obtained auth token")
            return self._token
            
        except Exception as e:
            logger.error(f"Failed to obtain auth token: {e}")
            raise ValueError(f"فشل في المصادقة: {e}")
    
    def submit_document(
        self,
        signed_xml: str,
        document_uuid: str
    ) -> Dict[str, Any]:
        """
        رفع وثيقة للضريبة
        
        Args:
            signed_xml: XML الموقع
            document_uuid: معرف الوثيقة
        
        Returns:
            dict: الاستجابة من API
        """
        if not REQUESTS_AVAILABLE:
            return self._mock_submit_document(signed_xml, document_uuid)
        
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
                'error_message': 'انتهت مهلة الاتصال بالخادم',
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return {
                'success': False,
                'error': 'request_failed',
                'error_message': str(e),
            }
    
    def query_document(self, uuid: str) -> Dict[str, Any]:
        """
        الاستعلام عن حالة وثيقة
        
        Args:
            uuid: معرف UUID للوثيقة
        
        Returns:
            dict: بيانات الوثيقة
        """
        if not REQUESTS_AVAILABLE:
            return self._mock_query_document(uuid)
        
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
        """
        إلغاء وثيقة
        
        Args:
            uuid: معرف الوثيقة
            reason: سبب الإلغاء
        
        Returns:
            dict: نتيجة الإلغاء
        """
        if not REQUESTS_AVAILABLE:
            return {'success': True, 'status': 'cancelled'}
        
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
    
    # Mock methods for development/testing
    def _mock_submit_document(self, signed_xml: str, document_uuid: str) -> Dict[str, Any]:
        """محاكاة رفع وثيقة للاختبار"""
        logger.warning("Using mock submit - NOT FOR PRODUCTION")
        
        # Simulate processing delay
        import random
        time.sleep(0.5)
        
        return {
            'success': True,
            'submission_id': f'MOCK-SUB-{document_uuid}',
            'internal_id': f'INT-{random.randint(100000, 999999)}',
            'uuid': document_uuid,
            'status': 'valid',
            'received_date': '2026-05-08T12:00:00Z',
            'qr_code': f'MOCKQR-{document_uuid}',
            'raw_response': {
                'mock': True,
                'documentId': document_uuid,
            },
        }
    
    def _mock_query_document(self, uuid: str) -> Dict[str, Any]:
        """محاكاة الاستعلام"""
        return {
            'success': True,
            'status': 'valid',
            'validation_results': [],
            'raw_response': {'mock': True},
        }


def create_api_client(config) -> TaxAPIClient:
    """
    Factory function to create API client from EInvoiceConfig
    """
    return TaxAPIClient(
        base_url=config.api_base_url,
        client_id=config.client_id,
        client_secret=config.client_secret,
        timeout=config.timeout_seconds
    )