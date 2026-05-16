"""
خدمة الفاتورة الإلكترونية الرئيسية
E-Invoice Service - Main Business Logic
"""
import uuid
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from django.db import transaction
from django.contrib.contenttypes.models import ContentType

from .models import (
    CompanySettings,
    EInvoiceConfig,
    Certificate,
    EInvoiceLog,
)
from .xml_generator import XMLGenerator
from .signer import Signer
from .api_client import TaxAPIClient, create_api_client
from .qr_generator import QRGenerator

# Import Status for use in the service
LogStatus = EInvoiceLog.Status

logger = logging.getLogger(__name__)


class EInvoiceService:
    """
    خدمة الفاتورة الإلكترونية - واجهة العمليات الرئيسية
    
    الوظائف:
    - توليد XML
    - توقيع الوثيقة
    - رفع للضريبة
    - توليد QR Code
    """
    
    @staticmethod
    @transaction.atomic
    def submit_sales_invoice(
        sales_invoice,
        user,
        company_settings: Optional[CompanySettings] = None
    ) -> Dict[str, Any]:
        """
        إرسال فاتورة مبيعات للضريبة
        
        Args:
            sales_invoice: فاتورة المبيعات
            user: المستخدم
            company_settings: إعدادات الشركة (اختياري)
        
        Returns:
            dict: نتيجة العملية
        """
        try:
            # 1. التحقق من الإعدادات
            if not company_settings:
                company_settings = CompanySettings.objects.filter(is_active=True).first()
            
            if not company_settings:
                return {
                    'success': False,
                    'error': 'NO_COMPANY_SETTINGS',
                    'message': 'لم يتم إعداد بيانات الشركة'
                }
            
            e_invoice_config = EInvoiceConfig.objects.filter(
                company=company_settings,
                is_active=True
            ).first()
            
            if not e_invoice_config:
                return {
                    'success': False,
                    'error': 'NO_CONFIG',
                    'message': 'لم يتم إعداد إعدادات الفاتورة الإلكترونية'
                }
            
            # 2. توليد XML
            logger.info(f"Generating XML for invoice {sales_invoice.number}")
            xml_content = XMLGenerator.sales_to_eta_xml(
                sales_invoice=sales_invoice,
                company_settings=company_settings
            )
            
            # 3. توقيع XML
            certificate = Certificate.objects.filter(
                company=company_settings,
                is_active=True,
                is_default=True
            ).first()
            
            if not certificate:
                logger.warning("No certificate found - using unsigned submission")
                signed_xml = xml_content
            else:
                logger.info(f"Signing with certificate {certificate.name}")
                signer = Signer(
                    certificate_path=certificate.certificate_file.path,
                    password=certificate.password_encrypted
                )
                signed_xml = signer.sign_xml(xml_content)
            
            # 4. إنشاء سجل
            document_uuid = str(uuid.uuid4())
            
            log_entry = EInvoiceLog.objects.create(
                content_type=ContentType.objects.get_for_model(sales_invoice),
                object_id=sales_invoice.id,
                internal_id=sales_invoice.number,
                uuid=document_uuid,
                status=LogStatus.DRAFT,
                raw_request={'xml_preview': xml_content[:500]},
                created_by=user
            )
            
            # 5. رفع للضريبة
            api_client = create_api_client(e_invoice_config)
            
            logger.info(f"Submitting to Tax Authority API: {document_uuid}")
            api_response = api_client.submit_document(
                signed_xml=signed_xml,
                document_uuid=document_uuid
            )
            
            if api_response.get('success'):
                # 6. توليد QR Code
                qr_buffer = None
                if api_response.get('qr_code'):
                    qr_buffer = QRGenerator.generate_from_invoice(
                        sales_invoice=sales_invoice,
                        uuid=api_response.get('uuid', document_uuid),
                        company_settings=company_settings
                    )
                
                # 7. تحديث السجل
                log_entry.submission_id = api_response.get('submission_id')
                log_entry.uuid = api_response.get('uuid', document_uuid)
                log_entry.status = LogStatus(api_response.get('status', 'submitted'))
                log_entry.submitted_at = datetime.now()
                log_entry.raw_response = api_response.get('raw_response')
                log_entry.qr_code.save(
                    f'qr_{sales_invoice.number}.png',
                    qr_buffer if qr_buffer else BytesIO()
                )
                log_entry.save()
                
                logger.info(f"Invoice {sales_invoice.number} submitted successfully")
                
                return {
                    'success': True,
                    'submission_id': api_response.get('submission_id'),
                    'uuid': api_response.get('uuid'),
                    'internal_id': log_entry.internal_id,
                    'status': log_entry.status,
                    'qr_code': log_entry.qr_code.url if log_entry.qr_code else None,
                }
            else:
                # فشل الإرسال
                log_entry.status = LogStatus.INVALID
                log_entry.error_message = api_response.get('error_message', 'Unknown error')
                log_entry.raw_response = api_response
                log_entry.save()
                
                logger.error(f"Failed to submit invoice: {api_response.get('error_message')}")
                
                return {
                    'success': False,
                    'error': api_response.get('error', 'SUBMIT_FAILED'),
                    'message': api_response.get('error_message', 'فشل في الإرسال'),
                    'log_id': log_entry.id,
                }
                
        except Exception as e:
            logger.exception(f"Unexpected error in submit_sales_invoice: {e}")
            return {
                'success': False,
                'error': 'UNEXPECTED_ERROR',
                'message': str(e)
            }
    
    @staticmethod
    def get_invoice_status(log_entry: EInvoiceLog) -> Dict[str, Any]:
        """
        الاستعلام عن حالة الفاتورة
        """
        if not log_entry.uuid:
            return {
                'success': False,
                'message': 'لا يوجد UUID للاستعلام'
            }
        
        # Get company settings from the linked document
        company_settings = CompanySettings.objects.filter(is_active=True).first()
        if not company_settings:
            return {'success': False, 'message': 'لا توجد إعدادات للشركة'}
        
        e_invoice_config = EInvoiceConfig.objects.filter(
            company=company_settings,
            is_active=True
        ).first()
        
        if not e_invoice_config:
            return {'success': False, 'message': 'لا توجد إعدادات API'}
        
        api_client = create_api_client(e_invoice_config)
        return api_client.query_document(log_entry.uuid)
    
    @staticmethod
    @transaction.atomic
    def cancel_invoice(log_entry: EInvoiceLog, reason: str, user) -> Dict[str, Any]:
        """
        إلغاء فاتورة مرسلة
        """
        if not log_entry.uuid:
            return {
                'success': False,
                'message': 'لا يوجد UUID للإلغاء'
            }
        
        company_settings = CompanySettings.objects.filter(is_active=True).first()
        if not company_settings:
            return {'success': False, 'message': 'لا توجد إعدادات للشركة'}
        
        e_invoice_config = EInvoiceConfig.objects.filter(
            company=company_settings,
            is_active=True
        ).first()
        
        if not e_invoice_config:
            return {'success': False, 'message': 'لا توجد إعدادات API'}
        
        api_client = create_api_client(e_invoice_config)
        result = api_client.cancel_document(log_entry.uuid, reason)
        
        if result.get('success'):
            log_entry.status = LogStatus.CANCELLED
            log_entry.save()
        
        return result


# Import BytesIO for the service
from io import BytesIO