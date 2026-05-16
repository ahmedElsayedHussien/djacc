"""
مولد QR Code للفاتورة الإلكترونية
"""
import logging
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing qrcode
try:
    import qrcode
    import qrcode.image.svg
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logger.warning("qrcode library not installed")


class QRGenerator:
    """
    مولد QR Code للفاتورة الإلكترونية
    
    مواصفات QR Code according to ETA:
    - Contains: Company Name, Tax ID, Date, Total, Tax Amount
    - Format: Plain text or JSON
    """
    
    @staticmethod
    def generate_qr_data(
        company_name: str,
        tax_id: str,
        invoice_date: str,
        total: float,
        tax_amount: float,
        uuid: str
    ) -> str:
        """
        بناء بيانات QR Code
        
        Args:
            company_name: اسم الشركة
            tax_id: الرقم الضريبي
            invoice_date: تاريخ الفاتورة
            total: الإجمالي
            tax_amount: مبلغ الضريبة
            uuid: معرف UUID
        
        Returns:
            str: بيانات QR
        """
        # Format according to ETA specification
        qr_data = (
            f"{company_name}|"
            f"{tax_id}|"
            f"{invoice_date}|"
            f"{total:.2f}|"
            f"{tax_amount:.2f}|"
            f"{uuid}"
        )
        
        return qr_data
    
    @staticmethod
    def generate_qr_image(
        qr_data: str,
        box_size: int = 10,
        border: int = 4,
        fill_color: str = 'black',
        back_color: str = 'white'
    ) -> Optional[BytesIO]:
        """
        توليد صورة QR Code
        
        Args:
            qr_data: بيانات QR
            box_size: حجم الصندوق
            border: الهامش
            fill_color: لون الرمز
            back_color: لون الخلفية
        
        Returns:
            BytesIO: صورة QR
        """
        if not QRCODE_AVAILABLE:
            logger.warning("qrcode not available - returning None")
            return None
        
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=box_size,
                border=border,
            )
            
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(
                fill_color=fill_color,
                back_color=back_color
            )
            
            # Save to buffer
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            logger.info("QR Code generated successfully")
            return buffer
            
        except Exception as e:
            logger.error(f"Failed to generate QR Code: {e}")
            return None
    
    @staticmethod
    def generate_qr_svg(
        qr_data: str,
        box_size: int = 10
    ) -> Optional[str]:
        """
        توليد QR Code كـ SVG
        
        Args:
            qr_data: بيانات QR
            box_size: حجم الصندوق
        
        Returns:
            str: SVG string
        """
        if not QRCODE_AVAILABLE:
            return None
        
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=box_size,
                border=1,
            )
            
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            # Generate SVG
            from qrcode.image.svg import SvgImage
            img = qr.make_image(image_factory=SvgImage)
            
            # Save to string
            buffer = BytesIO()
            img.save(buffer)
            buffer.seek(0)
            
            return buffer.read().decode('utf-8')
            
        except Exception as e:
            logger.error(f"Failed to generate QR SVG: {e}")
            return None
    
    @staticmethod
    def generate_from_invoice(
        sales_invoice,
        uuid: str,
        company_settings
    ) -> Optional[BytesIO]:
        """
        توليد QR مباشرة من SalesInvoice
        
        Args:
            sales_invoice: الفاتورة
            uuid: معرف UUID من الضريبة
            company_settings: إعدادات الشركة
        
        Returns:
            BytesIO: صورة QR
        """
        qr_data = QRGenerator.generate_qr_data(
            company_name=company_settings.company_name_ar,
            tax_id=company_settings.tax_id,
            invoice_date=sales_invoice.date.isoformat(),
            total=float(sales_invoice.total),
            tax_amount=float(sales_invoice.tax_amount),
            uuid=uuid
        )
        
        return QRGenerator.generate_qr_image(qr_data)
    
    @staticmethod
    def validate_qr_data(qr_data: str) -> bool:
        """
        التحقق من صحة بيانات QR
        
        Args:
            qr_data: بيانات QR
        
        Returns:
            bool: True if valid format
        """
        try:
            parts = qr_data.split('|')
            return len(parts) == 6
        except Exception:
            return False