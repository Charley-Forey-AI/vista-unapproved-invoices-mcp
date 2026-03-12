"""Pydantic models for Vista API request and response payloads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VistaModel(BaseModel):
    """Shared base model for Vista payloads."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class QueryFilter(VistaModel):
    field: str
    operator: str
    values: list[str] = Field(default_factory=list)


class QueryRequest(VistaModel):
    filters: list[QueryFilter] = Field(default_factory=list)


class EnterpriseItem(VistaModel):
    id: int
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    name: str | None = None
    created_by_user_id: UUID | None = Field(default=None, alias="createdByUserId")
    created_date_time: datetime | None = Field(default=None, alias="createdDateTime")
    customer_id: str | None = Field(default=None, alias="customerId")
    deleted_by_user_id: UUID | None = Field(default=None, alias="deletedByUserId")
    deleted_date_time: datetime | None = Field(default=None, alias="deletedDateTime")
    event_id: UUID | None = Field(default=None, alias="eventId")
    event_timestamp: datetime | None = Field(default=None, alias="eventTimestamp")
    event_type: str | None = Field(default=None, alias="eventType")
    header_image_id: int | None = Field(default=None, alias="headerImageId")
    header_image_url: str | None = Field(default=None, alias="headerImageUrl")
    status: int | None = None
    store_and_forward_enabled: bool | None = Field(default=None, alias="storeAndForwardEnabled")
    updated_date_time: datetime | None = Field(default=None, alias="updatedDateTime")
    updated_by_user_id: UUID | None = Field(default=None, alias="updatedByUserId")


class EnterpriseGetResponse(VistaModel):
    item: EnterpriseItem | None = None


class EnterpriseListResponse(VistaModel):
    items: list[EnterpriseItem] = Field(default_factory=list)
    page_size: int | None = Field(default=None, alias="pageSize")
    current_page: int | None = Field(default=None, alias="currentPage")


class UnapprovedInvoiceFile(VistaModel):
    id: UUID | None = None
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    unapproved_invoice_id: UUID | None = Field(default=None, alias="unapprovedInvoiceId")
    file_name: str | None = Field(default=None, alias="fileName")
    container_name: str | None = Field(default=None, alias="containerName")


class UnapprovedInvoiceCreateItem(VistaModel):
    company_id: UUID = Field(alias="companyId")
    entered_by: str = Field(alias="enteredBy")
    files: list[UnapprovedInvoiceFile] = Field(default_factory=list)
    invoice_number: str = Field(alias="invoiceNumber")
    invoice_amount: float = Field(alias="invoiceAmount")
    invoice_date: datetime = Field(alias="invoiceDate")
    invoice_description: str | None = Field(default=None, alias="invoiceDescription")
    month_year: datetime = Field(alias="monthYear")
    purchase_order_id: UUID | None = Field(default=None, alias="purchaseOrderId")
    subcontract_id: UUID | None = Field(default=None, alias="subcontractId")
    sales_tax: float | None = Field(default=None, alias="salesTax")
    value_added_tax: float | None = Field(default=None, alias="valueAddedTax")
    vendor_alternate_address_id: UUID | None = Field(default=None, alias="vendorAlternateAddressId")
    vendor_id: UUID = Field(alias="vendorId")


class UnapprovedInvoiceCreateRequest(VistaModel):
    items: list[UnapprovedInvoiceCreateItem] = Field(default_factory=list)


class UnapprovedInvoiceItem(VistaModel):
    id: UUID
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    company_id: UUID | None = Field(default=None, alias="companyId")
    company_code: str | None = Field(default=None, alias="companyCode")
    entered_by: str | None = Field(default=None, alias="enteredBy")
    enterprise_id: int | None = Field(default=None, alias="enterpriseId")
    files: list[UnapprovedInvoiceFile] = Field(default_factory=list)
    batch_code: str | None = Field(default=None, alias="batchCode")
    invoice_number: str | None = Field(default=None, alias="invoiceNumber")
    invoice_amount: float | None = Field(default=None, alias="invoiceAmount")
    invoice_date: datetime | None = Field(default=None, alias="invoiceDate")
    invoice_description: str | None = Field(default=None, alias="invoiceDescription")
    month_year: datetime | None = Field(default=None, alias="monthYear")
    purchase_order_id: UUID | None = Field(default=None, alias="purchaseOrderId")
    sales_tax: float | None = Field(default=None, alias="salesTax")
    subcontract_id: UUID | None = Field(default=None, alias="subcontractId")
    value_added_tax: float | None = Field(default=None, alias="valueAddedTax")
    vendor_id: UUID | None = Field(default=None, alias="vendorId")
    vendor_alternate_address_id: UUID | None = Field(default=None, alias="vendorAlternateAddressId")


class UnapprovedInvoiceActionResult(VistaModel):
    status_code: str | None = Field(default=None, alias="statusCode")
    action: str | None = None
    message: str | None = None
    item: UnapprovedInvoiceItem | None = None


class UnapprovedInvoiceCreateResponse(VistaModel):
    items: list[UnapprovedInvoiceActionResult] = Field(default_factory=list)


class UnapprovedInvoiceGetResponse(VistaModel):
    item: UnapprovedInvoiceItem | None = None


class UnapprovedInvoiceQueryResponse(VistaModel):
    items: list[UnapprovedInvoiceItem] = Field(default_factory=list)
    page_size: int | None = Field(default=None, alias="pageSize")
    current_page: int | None = Field(default=None, alias="currentPage")


class ProjectContractItem(VistaModel):
    id: UUID
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    architect: str | None = None
    company: str | None = None
    contract_code: str | None = Field(default=None, alias="contractCode")
    contract_type: str | None = Field(default=None, alias="contractType")
    cost_center_code: str | None = Field(default=None, alias="costCenterCode")
    customer_id: UUID | None = Field(default=None, alias="customerId")
    department: str | None = None
    description: str | None = None
    enterprise_id: int | None = Field(default=None, alias="enterpriseId")
    status: str | None = None
    start_date: datetime | None = Field(default=None, alias="startDate")


class ProjectItem(VistaModel):
    id: UUID
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    source_id: int | None = Field(default=None, alias="sourceId")
    company_id: UUID | None = Field(default=None, alias="companyId")
    company_code: str | None = Field(default=None, alias="companyCode")
    job: str | None = None
    description: str | None = None
    job_state: str | None = Field(default=None, alias="jobState")
    contracts: list[ProjectContractItem] = Field(default_factory=list)


class ProjectGetResponse(VistaModel):
    item: ProjectItem | None = None


class ProjectListResponse(VistaModel):
    items: list[ProjectItem] = Field(default_factory=list)
    page_size: int | None = Field(default=None, alias="pageSize")
    current_page: int | None = Field(default=None, alias="currentPage")


class VendorAlternateAddress(VistaModel):
    id: UUID
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    address1: str | None = None
    address2: str | None = None
    alternate_address_code: str | None = Field(default=None, alias="alternateAddressCode")
    city: str | None = None
    description: str | None = None
    enterprise_id: int | None = Field(default=None, alias="enterpriseId")
    fax: str | None = None
    notes: str | None = None
    phone: str | None = None
    postal_code: str | None = Field(default=None, alias="postalCode")
    state: str | None = None
    vendor_id: UUID | None = Field(default=None, alias="vendorId")


class VendorItem(VistaModel):
    id: UUID
    deleted: bool | None = None
    last_update_date_utc: datetime | None = Field(default=None, alias="lastUpdateDateUtc")
    enterprise_id: int | None = Field(default=None, alias="enterpriseId")
    name: str | None = None
    status: int | None = None
    type: str | None = None
    vendor_code: str | None = Field(default=None, alias="vendorCode")
    vendor_group: int | None = Field(default=None, alias="vendorGroup")
    last_invoice_date: datetime | None = Field(default=None, alias="lastInvoiceDate")
    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = Field(default=None, alias="postalCode")
    phone: str | None = None
    email: str | None = None
    fax: str | None = None
    alternate_addresses: list[VendorAlternateAddress] = Field(default_factory=list, alias="alternateAddresses")


class VendorGetResponse(VistaModel):
    item: VendorItem | None = None


class VendorListResponse(VistaModel):
    items: list[VendorItem] = Field(default_factory=list)
    page_size: int | None = Field(default=None, alias="pageSize")
    current_page: int | None = Field(default=None, alias="currentPage")


class HealthResponse(VistaModel):
    data: dict[str, Any] = Field(default_factory=dict, alias="Data")
    description: str | None = Field(default=None, alias="Description")
    duration: str | None = Field(default=None, alias="Duration")
    exception: dict[str, Any] | None = Field(default=None, alias="Exception")
    status: Any = Field(default=None, alias="Status")
    tags: dict[str, Any] = Field(default_factory=dict, alias="Tags")
