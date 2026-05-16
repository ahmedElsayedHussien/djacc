"""
توقيع الفاتورة الإلكترونية بالتوقيع الرقمي
Using P12 certificate with cryptography library
"""
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing cryptography, fallback to simpler method
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import pkcs12
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning("cryptography library not installed. Using placeholder signing.")


class Signer:
    """
    موقيع رقمي للـ XML باستخدام شهادة P12
    """
    
    def __init__(self, certificate_path: str, password: str):
        """
        Initialize signer with certificate
        
        Args:
            certificate_path: مسار ملف الشهادة (P12)
            password: كلمة مرور الشهادة
        """
        self.certificate_path = Path(certificate_path)
        self.password = password
        self._private_key = None
        self._certificate = None
        
        if CRYPTO_AVAILABLE and self.certificate_path.exists():
            self._load_certificate()
    
    def _load_certificate(self):
        """Load P12 certificate and extract private key"""
        try:
            with open(self.certificate_path, 'rb') as cert_file:
                cert_data = cert_file.read()
            
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                cert_data,
                self.password.encode(),
                backend=default_backend()
            )
            
            self._private_key = private_key
            self._certificate = certificate
            
            logger.info(f"Certificate loaded successfully: {self._certificate.subject}")
            
        except Exception as e:
            logger.error(f"Failed to load certificate: {e}")
            raise ValueError(f"فشل في تحميل الشهادة: {e}")
    
    def sign_xml(self, xml_content: str) -> str:
        """
        توقيع XML وإضافته كملحق Signature
        
        Args:
            xml_content: محتوى XML للمرفق
        
        Returns:
            str: XML موقع
        """
        if not CRYPTO_AVAILABLE:
            return self._placeholder_signature(xml_content)
        
        if not self._private_key:
            raise ValueError("الشهادة لم يتم تحميلها. يرجى التحقق من كلمة المرور ومسار الشهادة.")
        
        # Calculate SHA256 hash of XML
        xml_hash = hashlib.sha256(xml_content.encode('utf-8')).digest()
        
        # Sign the hash
        signature = self._private_key.sign(
            xml_hash,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        
        # Encode signature to base64
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        # Build signed XML with embedded signature
        signed_xml = self._add_signature_element(xml_content, signature_b64)
        
        logger.info("XML signed successfully")
        return signed_xml
    
    def _add_signature_element(self, xml_content: str, signature: str) -> str:
        """Add Signature element to XML"""
        
        signature_xml = f"""
        <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
                <CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
                <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                <Reference URI="">
                    <DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <DigestValue>{signature[:44]}...</DigestValue>
                </Reference>
            </SignedInfo>
            <SignatureValue>{signature}</SignatureValue>
            <KeyInfo>
                <X509Data>
                    <X509Certificate>{base64.b64encode(self._certificate.public_bytes(
                        encoding=serialization.Encoding.DER,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo
                    )).decode()}</X509Certificate>
                </X509Data>
            </KeyInfo>
        </Signature>
        """
        
        # Insert before closing Invoice tag
        if '</Invoice>' in xml_content:
            signed = xml_content.replace('</Invoice>', f'{signature_xml}</Invoice>')
        else:
            signed = xml_content + signature_xml
        
        return signed
    
    def _placeholder_signature(self, xml_content: str) -> str:
        """
        Placeholder signature when cryptography is not available
        Used for development/testing
        """
        logger.warning("Using placeholder signature - NOT FOR PRODUCTION")
        
        # Create a simple hash-based "signature"
        xml_hash = hashlib.sha256(xml_content.encode('utf-8')).hexdigest()[:16]
        
        signature_xml = f"""
        <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
                <CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
                <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
            </SignedInfo>
            <SignatureValue>PLACEHOLDER-{xml_hash}</SignatureValue>
            <KeyInfo>
                <KeyName>Development Signature</KeyName>
            </KeyInfo>
        </Signature>
        """
        
        if '</Invoice>' in xml_content:
            return xml_content.replace('</Invoice>', f'{signature_xml}</Invoice>')
        return xml_content + signature_xml
    
    def validate_signature(self, signed_xml: str) -> bool:
        """
        التحقق من التوقيع الرقمي
        
        Args:
            signed_xml: XML الموقع
        
        Returns:
            bool: True if valid
        """
        if not CRYPTO_AVAILABLE or not self._private_key:
            logger.warning("Cannot validate - cryptography not available")
            return False
        
        try:
            # Extract signature value
            import re
            match = re.search(r'<SignatureValue>(.*?)</SignatureValue>', signed_xml, re.DOTALL)
            if not match:
                return False
            
            signature_b64 = match.group(1)
            signature = base64.b64decode(signature_b64)
            
            # Extract XML content without signature for verification
            import re
            content_without_sig = re.sub(
                r'<Signature.*?</Signature>',
                '',
                signed_xml,
                flags=re.DOTALL
            )
            
            # Calculate hash of content
            content_hash = hashlib.sha256(content_without_sig.encode('utf-8')).digest()
            
            # Verify signature
            self._certificate.public_key().verify(
                signature,
                content_hash,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            
            logger.info("Signature validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Signature validation failed: {e}")
            return False
    
    @property
    def is_loaded(self) -> bool:
        """Check if certificate is loaded"""
        return self._private_key is not None
    
    @property
    def certificate_subject(self) -> Optional[str]:
        """Get certificate subject name"""
        if self._certificate:
            return str(self._certificate.subject)
        return None