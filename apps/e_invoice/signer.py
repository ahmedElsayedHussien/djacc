import base64
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12

logger = logging.getLogger(__name__)


class Signer:

    def __init__(self, certificate_path: str, password: str):
        self.certificate_path = Path(certificate_path)
        self.password = password
        self._private_key = None
        self._certificate = None

        if not self.certificate_path.exists():
            raise FileNotFoundError(f"ملف الشهادة غير موجود: {certificate_path}")

        self._load_certificate()

    def _load_certificate(self):
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
        if not self._private_key:
            raise ValueError("الشهادة لم يتم تحميلها. يرجى التحقق من كلمة المرور ومسار الشهادة.")

        xml_hash = hashlib.sha256(xml_content.encode('utf-8')).digest()

        signature = self._private_key.sign(
            xml_hash,
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        signature_b64 = base64.b64encode(signature).decode('utf-8')

        signed_xml = self._add_signature_element(xml_content, signature_b64)

        logger.info("XML signed successfully")
        return signed_xml

    def _add_signature_element(self, xml_content: str, signature: str) -> str:
        # Full base64-encoded SHA-256 digest of the invoice content
        xml_hash = hashlib.sha256(xml_content.encode('utf-8')).digest()
        digest_value = base64.b64encode(xml_hash).decode('utf-8')

        # Full X509 certificate in DER format
        cert_der = self._certificate.public_bytes(serialization.Encoding.DER)
        cert_b64 = base64.b64encode(cert_der).decode('utf-8')

        signature_xml = f"""
        <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
                <CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
                <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
                <Reference URI="">
                    <DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
                    <DigestValue>{digest_value}</DigestValue>
                </Reference>
            </SignedInfo>
            <SignatureValue>{signature}</SignatureValue>
            <KeyInfo>
                <X509Data>
                    <X509Certificate>{cert_b64}</X509Certificate>
                </X509Data>
            </KeyInfo>
        </Signature>
        """

        if '</Invoice>' in xml_content:
            signed = xml_content.replace('</Invoice>', f'{signature_xml}</Invoice>')
        else:
            signed = xml_content + signature_xml

        return signed

    def validate_signature(self, signed_xml: str) -> bool:
        if not self._private_key:
            logger.warning("Cannot validate - certificate not loaded")
            return False

        try:
            match = re.search(r'<SignatureValue>(.*?)</SignatureValue>', signed_xml, re.DOTALL)
            if not match:
                return False

            signature_b64 = match.group(1)
            signature = base64.b64decode(signature_b64)

            content_without_sig = re.sub(
                r'<Signature.*?</Signature>',
                '',
                signed_xml,
                flags=re.DOTALL
            )

            content_hash = hashlib.sha256(content_without_sig.encode('utf-8')).digest()

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
        return self._private_key is not None

    @property
    def certificate_subject(self) -> Optional[str]:
        if self._certificate:
            return str(self._certificate.subject)
        return None
