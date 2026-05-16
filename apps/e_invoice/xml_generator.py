"""
مولد XML للفاتورة الإلكترونية المصرية (ETA)
根据 Egyptian Tax Authority specifications
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class XMLGenerator:
    """
    مولد XML للفاتورة الإلكترونية - يعتمد على مواصفات ETA 2024
    """

    # أنواع الوثائق حسب ETA
    DOCUMENT_TYPE = {
        'invoice': 'I',
        'credit_note': 'C',
        'debit_note': 'D',
    }

    # أنواع الدفع
    PAYMENT_TYPE = {
        'cash': 'CASH',
        'credit': 'DEFERRED',
        'cheque': 'CHEQUE',
        'bank': 'BANK',
    }

    @staticmethod
    def sales_to_eta_xml(
        sales_invoice,
        company_settings,
        include_taxes: bool = True
    ) -> str:
        """
        يحول SalesInvoice إلى XML بطريق ETA
        
        Args:
            sales_invoice: نموذج الفاتورة من المبيعات
            company_settings: إعدادات الشركة من CompanySettings
            include_taxes: تضمين الضرائب
        
        Returns:
            str: XML string مطابق لمواصفات ETA
        """
        from apps.sales.models import SalesInvoiceLine
        
        lines = sales_invoice.lines.all()
        
        # بناء XML
        xml_parts = []
        
        # Header
        xml_parts.append('<?xml version="1.0" encoding="UTF-8"?>')
        xml_parts.append('<Invoice xmlns="urn:eta:invoice:v1.0">')
        
        # Header Section
        xml_parts.append('<Header>')
        xml_parts.append(f'<DocumentType>{XMLGenerator.DOCUMENT_TYPE['invoice']}</DocumentType>')
        xml_parts.append(f'<DocumentTypeVersion>1.0</DocumentTypeVersion>')
        xml_parts.append(f'<CompanyName>{XMLGenerator._escape_xml(company_settings.company_name_ar)}</CompanyName>')
        xml_parts.append(f'<CompanyNameCode>{company_settings.tax_id}</CompanyNameCode>')
        xml_parts.append(f'<RegistrationNumber>{company_settings.commercial_register}</RegistrationNumber>')
        xml_parts.append(f'<DateAndTimeOfIssuance>{sales_invoice.date.isoformat()}</DateAndTimeOfIssuance>')
        xml_parts.append(f'<DateAndTimeOfDelivery>{sales_invoice.date.isoformat()}</DateAndTimeOfDelivery>')
        xml_parts.append(f'<BranchCode>{company_settings.branch_code}</BranchCode>')
        
        #Seller - Buyer Section
        xml_parts.append('<Seller>')
        xml_parts.append(f'<CompanyName>{XMLGenerator._escape_xml(company_settings.company_name_ar)}</CompanyName>')
        xml_parts.append(f'<CompanyNameCode>{company_settings.tax_id}</CompanyNameCode>')
        xml_parts.append(f'<RegistrationNumber>{company_settings.commercial_register}</RegistrationNumber>')
        xml_parts.append(f'<RegistrationNumberCode>{company_settings.VAT_number}</RegistrationNumberCode>')
        xml_parts.append(f'<Address>')
        xml_parts.append(f'<Country>EG</Country>')
        xml_parts.append(f'<Address>{XMLGenerator._escape_xml(company_settings.address)}</Address>')
        xml_parts.append(f'<Governorate>{XMLGenerator._escape_xml(company_settings.governorate)}</Governorate>')
        xml_parts.append(f'<RegionCity>{XMLGenerator._escape_xml(company_settings.region_city)}</RegionCity>')
        xml_parts.append(f'</Address>')
        xml_parts.append(f'<PhoneNumber>{company_settings.phone}</PhoneNumber>')
        xml_parts.append(f'<Email>{company_settings.email}</Email>')
        xml_parts.append('</Seller>')
        
        # Buyer
        xml_parts.append('<Buyer>')
        xml_parts.append(f'<CompanyName>{XMLGenerator._escape_xml(sales_invoice.customer.name)}</CompanyName>')
        # Tax ID for buyer if available
        if sales_invoice.customer.tax_number:
            xml_parts.append(f'<CompanyNameCode>{sales_invoice.customer.tax_number}</CompanyNameCode>')
        else:
            xml_parts.append(f'<CompanyNameCode>NA</CompanyNameCode>')
        xml_parts.append(f'<RegistrationNumber>NA</RegistrationNumber>')
        xml_parts.append('</Buyer>')
        
        xml_parts.append('</Header>')
        
        # Invoice Lines
        xml_parts.append('<InvoiceLines>')
        
        for idx, line in enumerate(lines, 1):
            xml_parts.append('<InvoiceLine>')
            xml_parts.append(f'<SequenceNumber>{idx}</SequenceNumber>')
            xml_parts.append(f'<ItemCode>{line.item.code}</ItemCode>')
            xml_parts.append(f'<ItemName>{XMLGenerator._escape_xml(line.item.name)}</ItemName>')
            xml_parts.append(f'<UnitType>{line.unit.code if line.unit else 'EA'}</UnitType>')
            xml_parts.append(f'<Quantity>{XMLGenerator._format_decimal(line.quantity)}</Quantity>')
            xml_parts.append(f'<UnitValue>')
            xml_parts.append(f'<CurrencySoldAmount>{XMLGenerator._format_decimal(line.unit_price)}</CurrencySoldAmount>')
            xml_parts.append(f'<CurrencyCode>EGP</CurrencyCode>')
            xml_parts.append(f'<ExchangeRate>1</ExchangeRate>')
            xml_parts.append(f'</UnitValue>')
            
            # Discount
            if line.discount_percent and line.discount_percent > 0:
                discount_rate = XMLGenerator._format_decimal(line.discount_percent)
                discount_amount = XMLGenerator._format_decimal(
                    (line.quantity * line.unit_price) * (line.discount_percent / 100)
                )
                xml_parts.append(f'<Discount>')
                xml_parts.append(f'<DiscountRate>{discount_rate}</DiscountRate>')
                xml_parts.append(f'<DiscountAmount>{discount_amount}</DiscountAmount>')
                xml_parts.append(f'</Discount>')
            
            # Taxable Items
            xml_parts.append(f'<TaxableItems>')
            
            # Tax Type 1
            if line.tax_type:
                xml_parts.append(f'<TaxableItem>')
                xml_parts.append(f'<TaxType>{line.tax_type.category.upper()}</TaxType>')
                xml_parts.append(f'<TaxAmount>{XMLGenerator._format_decimal(line.tax_percent / 100 * line.quantity * line.unit_price)}</TaxAmount>')
                xml_parts.append(f'<TaxRate>{XMLGenerator._format_decimal(line.tax_percent)}</TaxRate>')
                xml_parts.append(f'</TaxableItem>')
            
            # Tax Type 2
            if line.tax_type2:
                xml_parts.append(f'<TaxableItem>')
                xml_parts.append(f'<TaxType>{line.tax_type2.category.upper()}</TaxType>')
                xml_parts.append(f'<TaxAmount>{XMLGenerator._format_decimal(line.tax_percent2 / 100 * line.quantity * line.unit_price)}</TaxAmount>')
                xml_parts.append(f'<TaxRate>{XMLGenerator._format_decimal(line.tax_percent2)}</TaxRate>')
                xml_parts.append(f'</TaxableItem>')
            
            xml_parts.append(f'</TaxableItems>')
            
            # Sales Total
            sales_total = line.quantity * line.unit_price
            if line.discount_percent and line.discount_percent > 0:
                sales_total -= (line.quantity * line.unit_price) * (line.discount_percent / 100)
            
            xml_parts.append(f'<SalesTotal>{XMLGenerator._format_decimal(sales_total)}</SalesTotal>')
            xml_parts.append(f'<NetTotal>{XMLGenerator._format_decimal(sales_total)}</NetTotal>')
            xml_parts.append(f'<Total>{XMLGenerator._format_decimal(line.total)}</Total>')
            
            xml_parts.append('</InvoiceLine>')
        
        xml_parts.append('</InvoiceLines>')
        
        # Taxes Section
        xml_parts.append('<TaxesTotals>')
        
        # Collect taxes
        tax_summary = {}
        for line in lines:
            if line.tax_type:
                rate = float(line.tax_percent)
                tax_amount = float(line.quantity * line.unit_price) * (rate / 100)
                if rate not in tax_summary:
                    tax_summary[rate] = 0
                tax_summary[rate] += tax_amount
        
        for rate, amount in tax_summary.items():
            xml_parts.append('<TotalTax>')
            xml_parts.append(f'<TaxType>VAT</TaxType>')
            xml_parts.append(f'<TaxRate>{rate}</TaxRate>')
            xml_parts.append(f'<TaxAmount>{XMLGenerator._format_decimal(amount)}</TaxAmount>')
            xml_parts.append('</TotalTax>')
        
        xml_parts.append('</TaxesTotals>')
        
        # Totals Section
        xml_parts.append('<Totals>')
        xml_parts.append(f'<NetTotal>{XMLGenerator._format_decimal(sales_invoice.subtotal - sales_invoice.discount_amount)}</NetTotal>')
        xml_parts.append(f'<TotalDiscount>{XMLGenerator._format_decimal(sales_invoice.discount_amount)}</TotalDiscount>')
        xml_parts.append(f'<TotalTax>{XMLGenerator._format_decimal(sales_invoice.tax_amount)}</TotalTax>')
        xml_parts.append(f'<GrandTotal>{XMLGenerator._format_decimal(sales_invoice.total)}</GrandTotal>')
        xml_parts.append('</Totals>')
        
        # Payment Section
        xml_parts.append('<Payment>')
        xml_parts.append(f'<PaymentMethod>{XMLGenerator.PAYMENT_TYPE.get(sales_invoice.payment_type, 'CASH')}</PaymentMethod>')
        xml_parts.append('</Payment>')
        
        # Footer
        xml_parts.append('</Invoice>')
        
        return '\n'.join(xml_parts)

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape special XML characters"""
        if not text:
            return ''
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))

    @staticmethod
    def _format_decimal(value) -> str:
        """Format decimal for XML (max 4 decimal places, no trailing zeros)"""
        if value is None:
            return '0'
        if isinstance(value, Decimal):
            value = float(value)
        return f'{value:.4f}'.rstrip('0').rstrip('.')