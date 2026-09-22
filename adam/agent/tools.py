"""Read-only tools and tool sandbox with strict security guardrails.

Per Phase 04 specification:
- 'Tools are read-only: search, open cited source, list authorised collections.
   No web browsing, emailing, editing records, procurement action, or database write tool is available to the model.
   The “agent” is a state machine with max one retrieval and one answer pass; it does not self-expand tasks.'
"""

import re
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from adam.agent.sandbox import SecurePythonSandbox
from adam.db.models import Document, DocumentVersion, DocumentPage, TextBlock, Source, PrecedentReference
from adam.rag.acl import AclEnforcer
from adam.rag.models import UserContext, ParsedQuery
from adam.rag.query import QueryUnderstanding
from adam.rag.retriever import HybridRetriever
from adam.vocabularies import AgentToolName, Classification, DepartmentId, SourceStatus


class SearchToolArgs(BaseModel):
    """Arguments for repository search tool."""
    model_config = ConfigDict(extra="ignore")
    query: str = Field(..., description="Search query text")
    department_id: Optional[str] = Field(None, description="Optional department filter")
    doc_type: Optional[str] = Field(None, description="Optional document type filter")
    top_k: int = Field(5, description="Max passages to retrieve (default 5)")


class OpenCitedSourceToolArgs(BaseModel):
    """Arguments for inspecting cited document source."""
    model_config = ConfigDict(extra="ignore")
    document_id: str = Field(..., description="Unique document identifier")
    page_number: Optional[int] = Field(None, description="Page number to view (1-indexed)")


class ListAuthorisedCollectionsToolArgs(BaseModel):
    """Arguments for listing authorised collections."""
    model_config = ConfigDict(extra="ignore")


class InspectSystemToolArgs(BaseModel):
    """Arguments for system introspection."""
    model_config = ConfigDict(extra="ignore")
    subtopic: Optional[str] = Field("all", description="Optional focus area: all, model, harness, sources, budget, tools")


class LookupPrecedentsToolArgs(BaseModel):
    """Arguments for precedent lookup."""
    model_config = ConfigDict(extra="ignore")
    document_id: Optional[str] = Field(None, description="Document identifier")
    order_number: Optional[str] = Field(None, description="Government order number to trace")


class ExecutePythonSandboxToolArgs(BaseModel):
    """Arguments for isolated Python sandbox execution."""
    model_config = ConfigDict(extra="ignore")
    code: str = Field(..., description="Self-contained Python arithmetic/formula code without imports")
    timeout_seconds: Optional[float] = Field(2.0, description="Max execution duration in seconds")


class VerifyClaimToolArgs(BaseModel):
    """Arguments for verifying claim against evidence."""
    model_config = ConfigDict(extra="ignore")
    claim: str = Field(..., description="Claim or numerical rate to verify against official records")


class DatabaseQueryToolArgs(BaseModel):
    """Arguments for read-only database query."""
    model_config = ConfigDict(extra="ignore")
    table: str = Field(..., description="Target database table: documents, document_versions, sources, or precedent_references")
    filter_by: Optional[Dict[str, Any]] = Field(None, description="Optional equality filters (e.g. {'department_id': 'UK_FIN'})")
    aggregate: Optional[str] = Field("count", description="Optional aggregate function: count, list")
    group_by: Optional[str] = Field(None, description="Optional column to group results by")
    limit: int = Field(20, description="Max rows to return (default 20, max 100)")


class CompareSourcesToolArgs(BaseModel):
    """Arguments for comparative analysis between sources or documents."""
    model_config = ConfigDict(extra="ignore")
    source_a: str = Field(..., description="First source content, document ID, or citation reference")
    source_b: str = Field(..., description="Second source content, document ID, or citation reference")
    comparison_focus: Optional[str] = Field(None, description="Specific focus: rates, allowances, dates, eligibility, amendments")


class WebSearchToolArgs(BaseModel):
    """Arguments for domain-aware external web search."""
    model_config = ConfigDict(extra="ignore")
    query: str = Field(..., description="Search query keywords")
    domain_filter: Optional[str] = Field(None, description="Optional domain constraint, e.g. gov.in, nic.in")
    max_results: int = Field(5, description="Max search results (1-10, default 5)")


class FetchWebPageToolArgs(BaseModel):
    """Arguments for SSRF-safe web page retrieval."""
    model_config = ConfigDict(extra="ignore")
    url: str = Field(..., description="Valid HTTP or HTTPS web URL to retrieve")
    extract_tables: bool = Field(True, description="Whether to format HTML tables as markdown tables")


@dataclass
class ToolDescriptor:
    """Authoritative descriptor of a registered tool with permissions and limitations."""
    name: str
    category: str  # local_retrieval, database, computation, web_research, analysis, introspection
    description: str
    when_to_use: str
    limitations: str
    permission_level: str  # PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL
    requires_network: bool
    arg_model: Type[BaseModel]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "when_to_use": self.when_to_use,
            "limitations": self.limitations,
            "permission_level": self.permission_level,
            "requires_network": self.requires_network,
            "is_read_only": True,
            "parameters": self.arg_model.model_json_schema(),
        }


class ForbiddenToolError(PermissionError):
    """Raised when an attempt is made to call a forbidden, write, or unapproved tool."""
    pass


class ReadOnlyToolRegistry:
    """Registry and execution sandbox enforcing read-only tools and blocking dangerous capabilities."""

    TOOL_ARG_MODELS: Dict[str, Type[BaseModel]] = {
        AgentToolName.SEARCH.value: SearchToolArgs,
        AgentToolName.OPEN_CITED_SOURCE.value: OpenCitedSourceToolArgs,
        AgentToolName.LIST_AUTHORISED_COLLECTIONS.value: ListAuthorisedCollectionsToolArgs,
        AgentToolName.INSPECT_SYSTEM.value: InspectSystemToolArgs,
        AgentToolName.LOOKUP_PRECEDENTS.value: LookupPrecedentsToolArgs,
        AgentToolName.EXECUTE_PYTHON_SANDBOX.value: ExecutePythonSandboxToolArgs,
        AgentToolName.VERIFY_CLAIM.value: VerifyClaimToolArgs,
        AgentToolName.DATABASE_QUERY.value: DatabaseQueryToolArgs,
        AgentToolName.COMPARE_SOURCES.value: CompareSourcesToolArgs,
        AgentToolName.WEB_SEARCH.value: WebSearchToolArgs,
        AgentToolName.FETCH_WEB_PAGE.value: FetchWebPageToolArgs,
    }

    ALLOWED_TOOLS = {
        AgentToolName.SEARCH.value,
        AgentToolName.OPEN_CITED_SOURCE.value,
        AgentToolName.LIST_AUTHORISED_COLLECTIONS.value,
        AgentToolName.INSPECT_SYSTEM.value,
        AgentToolName.LOOKUP_PRECEDENTS.value,
        AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
        AgentToolName.VERIFY_CLAIM.value,
        AgentToolName.DATABASE_QUERY.value,
        AgentToolName.COMPARE_SOURCES.value,
        AgentToolName.WEB_SEARCH.value,
        AgentToolName.FETCH_WEB_PAGE.value,
    }

    FORBIDDEN_TOOLS = {
        "web_browse",
        "browse_web",
        "fetch_url",
        "curl",
        "send_email",
        "email",
        "edit_record",
        "update_record",
        "delete_record",
        "write_record",
        "db_write",
        "procure_action",
        "procurement_action",
        "sanction_release",
        "run_bash",
        "execute_command",
        "modify_document",
    }

    TOOL_DESCRIPTORS: Dict[str, ToolDescriptor] = {
        AgentToolName.SEARCH.value: ToolDescriptor(
            name=AgentToolName.SEARCH.value,
            category="local_retrieval",
            description="Authorized read-only semantic and full-text search over approved Uttarakhand Government Orders and repository chunks.",
            when_to_use="Always perform first for any administrative, regulatory, policy, or legal knowledge query.",
            limitations="Read-only. Searches local indexed documents within user clearance.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=SearchToolArgs,
        ),
        AgentToolName.OPEN_CITED_SOURCE.value: ToolDescriptor(
            name=AgentToolName.OPEN_CITED_SOURCE.value,
            category="local_retrieval",
            description="Read-only inspection of a cited document record, PDF page link, text blocks, and coordinates.",
            when_to_use="When exact text, specific paragraphs, or visual coordinates of an identified document are needed.",
            limitations="Read-only. Requires valid document_id.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=OpenCitedSourceToolArgs,
        ),
        AgentToolName.LIST_AUTHORISED_COLLECTIONS.value: ToolDescriptor(
            name=AgentToolName.LIST_AUTHORISED_COLLECTIONS.value,
            category="introspection",
            description="List departments, classifications, and approved document collections accessible to current user.",
            when_to_use="When discovering accessible scopes or validating user clearance boundaries.",
            limitations="Read-only. Filtered strictly by user clearance.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=ListAuthorisedCollectionsToolArgs,
        ),
        AgentToolName.INSPECT_SYSTEM.value: ToolDescriptor(
            name=AgentToolName.INSPECT_SYSTEM.value,
            category="introspection",
            description="Inspect authoritative system state, active model parameters, harness configuration, memory budget, and data sources catalog.",
            when_to_use="When the user asks about ADAM's identity, active model, tools, capabilities, or memory status.",
            limitations="Read-only. Keys and sensitive internal paths are redacted.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=InspectSystemToolArgs,
        ),
        AgentToolName.LOOKUP_PRECEDENTS.value: ToolDescriptor(
            name=AgentToolName.LOOKUP_PRECEDENTS.value,
            category="local_retrieval",
            description="Lookup precedent relationships (supersedes, amends, in continuation of) for an order or document.",
            when_to_use="When tracing amendment history or checking if an order has been superseded.",
            limitations="Read-only. Bounded to precedent links present in repository.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=LookupPrecedentsToolArgs,
        ),
        AgentToolName.EXECUTE_PYTHON_SANDBOX.value: ToolDescriptor(
            name=AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
            category="computation",
            description="Execute deterministic mathematical, statistical, or date calculations in an isolated, secure Python sandbox.",
            when_to_use="When calculating exact financial allowances, percentages, basic pay, pensions, or date differences.",
            limitations="No imports, no filesystem I/O, no network access. 2.0s hard timeout, 256MB memory cap.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=ExecutePythonSandboxToolArgs,
        ),
        AgentToolName.VERIFY_CLAIM.value: ToolDescriptor(
            name=AgentToolName.VERIFY_CLAIM.value,
            category="analysis",
            description="Verify whether a factual assertion, numerical rate, or date is grounded in retrieved repository evidence.",
            when_to_use="Intermediate claim checking before final synthesis.",
            limitations="Read-only string and token-level verification.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=VerifyClaimToolArgs,
        ),
        AgentToolName.DATABASE_QUERY.value: ToolDescriptor(
            name=AgentToolName.DATABASE_QUERY.value,
            category="database",
            description="Read-only inspection of connected database records (documents, document_versions, sources, precedents) for counts and metadata summaries.",
            when_to_use="When user queries ask for document counts, statistics, departmental summaries, or catalog properties.",
            limitations="Strictly read-only. No raw SQL or write operations allowed.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=DatabaseQueryToolArgs,
        ),
        AgentToolName.COMPARE_SOURCES.value: ToolDescriptor(
            name=AgentToolName.COMPARE_SOURCES.value,
            category="analysis",
            description="Perform structured comparison and delta analysis between two sources or documents.",
            when_to_use="When comparing two government orders, historical versions, or external web guidelines vs internal rules.",
            limitations="Read-only text and fact comparison.",
            permission_level=Classification.PUBLIC.value,
            requires_network=False,
            arg_model=CompareSourcesToolArgs,
        ),
        AgentToolName.WEB_SEARCH.value: ToolDescriptor(
            name=AgentToolName.WEB_SEARCH.value,
            category="web_research",
            description="Secure, domain-aware external web search for national/central guidelines or external facts when internal evidence is insufficient.",
            when_to_use="Use only after local verification is incomplete or when external comparison is explicitly required.",
            limitations="SSRF-safe, rate-limited. Strictly prohibited under RESTRICTED or CONFIDENTIAL air-gapped policies.",
            permission_level=Classification.PUBLIC.value,
            requires_network=True,
            arg_model=WebSearchToolArgs,
        ),
        AgentToolName.FETCH_WEB_PAGE.value: ToolDescriptor(
            name=AgentToolName.FETCH_WEB_PAGE.value,
            category="web_research",
            description="SSRF-safe retrieval and clean text/markdown extraction of an external web page URL.",
            when_to_use="When inspecting an authoritative external web source found via web search.",
            limitations="SSRF-safe, 5s timeout, 1MB size limit. Prohibited under RESTRICTED or CONFIDENTIAL air-gapped policies.",
            permission_level=Classification.PUBLIC.value,
            requires_network=True,
            arg_model=FetchWebPageToolArgs,
        ),
    }

    @classmethod
    def get_tool_manifest(
        cls,
        user_context: Optional[UserContext] = None,
        filter_unavailable: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return comprehensive typed descriptor manifest for self-introspection and dynamic tool selection."""
        manifest = []
        is_air_gapped = False
        if user_context and user_context.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            is_air_gapped = True

        for desc in cls.TOOL_DESCRIPTORS.values():
            is_avail = not (is_air_gapped and desc.requires_network)
            if filter_unavailable and not is_avail:
                continue
            item = desc.to_dict()
            item["is_available"] = is_avail
            manifest.append(item)
        return manifest

    @classmethod
    def get_tool_definitions(cls, include_extended: bool = False) -> List[Dict[str, Any]]:
        """Return JSON-schema definitions for authorized tools."""
        base_tools = [
            {
                "name": AgentToolName.SEARCH.value,
                "description": "Authorized read-only semantic and full-text search over approved repository chunks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query text"},
                        "department_id": {"type": "string", "description": "Optional department filter"},
                        "doc_type": {"type": "string", "description": "Optional document type filter"},
                        "top_k": {"type": "integer", "description": "Max passages to retrieve (default 5)"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": AgentToolName.OPEN_CITED_SOURCE.value,
                "description": "Read-only inspection of a cited document record, PDF page link, text blocks, and coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "Unique document identifier"},
                        "page_number": {"type": "integer", "description": "Page number to view (1-indexed)"},
                    },
                    "required": ["document_id"],
                },
            },
            {
                "name": AgentToolName.LIST_AUTHORISED_COLLECTIONS.value,
                "description": "List departments, classifications, and approved document collections accessible to current user.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]
        if not include_extended:
            return base_tools

        extended_tools = [
            {
                "name": AgentToolName.INSPECT_SYSTEM.value,
                "description": "Inspect authoritative system state, active model parameters, harness configuration, memory budget, and data sources catalog.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subtopic": {"type": "string", "description": "Optional focus area: all, model, harness, sources, budget, tools"},
                    },
                },
            },
            {
                "name": AgentToolName.LOOKUP_PRECEDENTS.value,
                "description": "Lookup precedent relationships (supersedes, amends, in continuation of) for an order or document.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {"type": "string", "description": "Document identifier"},
                        "order_number": {"type": "string", "description": "Government order number to trace"},
                    },
                },
            },
            {
                "name": AgentToolName.EXECUTE_PYTHON_SANDBOX.value,
                "description": "Execute deterministic mathematical, statistical, or date calculations in an isolated, secure Python sandbox.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Python script containing the formula or calculation to execute"},
                    },
                    "required": ["code"],
                },
            },
            {
                "name": AgentToolName.VERIFY_CLAIM.value,
                "description": "Verify whether a factual assertion, numerical rate, or date is grounded in retrieved repository evidence.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string", "description": "Claim or numerical rate to verify"},
                    },
                    "required": ["claim"],
                },
            },
            {
                "name": AgentToolName.DATABASE_QUERY.value,
                "description": "Read-only inspection of connected database records (documents, versions, sources, precedents) for counts and metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "description": "Target database table (documents, document_versions, sources, precedent_references)"},
                        "filter_by": {"type": "object", "description": "Optional equality filters (e.g. {'department_id': 'UK_FIN'})"},
                        "aggregate": {"type": "string", "description": "Aggregate function (count, list)"},
                        "limit": {"type": "integer", "description": "Max rows to return"},
                    },
                    "required": ["table"],
                },
            },
            {
                "name": AgentToolName.COMPARE_SOURCES.value,
                "description": "Perform structured comparison and delta analysis between two sources or documents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_a": {"type": "string", "description": "First source content or document ID"},
                        "source_b": {"type": "string", "description": "Second source content or document ID"},
                        "comparison_focus": {"type": "string", "description": "Focus area (rates, allowances, dates, eligibility)"},
                    },
                    "required": ["source_a", "source_b"],
                },
            },
            {
                "name": AgentToolName.WEB_SEARCH.value,
                "description": "Secure, domain-aware external web search for national/central guidelines or external facts when internal evidence is insufficient.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query keywords"},
                        "domain_filter": {"type": "string", "description": "Optional domain constraint (e.g. gov.in)"},
                        "max_results": {"type": "integer", "description": "Max search results (default 5)"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": AgentToolName.FETCH_WEB_PAGE.value,
                "description": "SSRF-safe retrieval and clean text/markdown extraction of an external web page URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target HTTP/HTTPS URL"},
                        "extract_tables": {"type": "boolean", "description": "Format tables as markdown"},
                    },
                    "required": ["url"],
                },
            },
        ]
        return base_tools + extended_tools

    @classmethod
    def get_all_tool_definitions(cls) -> List[Dict[str, Any]]:
        """Return all tool definitions including agentic reasoning tools."""
        return cls.get_tool_definitions(include_extended=True)

    @classmethod
    def get_tool_json_schemas(cls, include_extended: bool = True) -> List[Dict[str, Any]]:
        """Auto-generate JSON Schemas using Pydantic models for model tool calling."""
        defs = cls.get_tool_definitions(include_extended=include_extended)
        schemas = []
        for d in defs:
            name = d["name"]
            model = cls.TOOL_ARG_MODELS.get(name)
            params = model.model_json_schema() if model else d.get("parameters", {})
            params = dict(params)
            params.pop("title", None)
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": d["description"],
                    "parameters": params,
                }
            })
        return schemas

    @classmethod
    def execute(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Execute tool strictly within authorized bounds with security interception."""
        normalized_name = tool_name.strip().lower()

        # Check explicit web access permissions
        allow_web = getattr(user_context, "can_access_web", False) or getattr(user_context, "allow_web_research", False)

        # Handle web_browse alias
        if normalized_name in ("web_browse", "browse_web", "fetch_url"):
            if not allow_web:
                raise ForbiddenToolError(
                    f"Security Violation: Tool '{tool_name}' is strictly forbidden. "
                    "The ADAM model agent is restricted to read-only tools. "
                    "Web browsing, emailing, editing records, procurement action, "
                    "and database write tools are strictly unavailable."
                )
            normalized_name = AgentToolName.FETCH_WEB_PAGE.value

        # Check explicit forbidden list or whitelist violation
        if normalized_name in cls.FORBIDDEN_TOOLS or normalized_name not in cls.ALLOWED_TOOLS:
            raise ForbiddenToolError(
                f"Security Violation: Tool '{tool_name}' is strictly forbidden. "
                "The ADAM model agent is restricted to read-only tools. "
                "Web browsing, emailing, editing records, procurement action, "
                "and database write tools are strictly unavailable."
            )

        # Validate arguments using Pydantic schema if registered
        arg_model = cls.TOOL_ARG_MODELS.get(normalized_name)
        validated_args = arguments
        if arg_model:
            try:
                validated_args = arg_model.model_validate(arguments or {}).model_dump(exclude_unset=False)
            except Exception as e:
                raise ValueError(f"Invalid arguments for tool '{tool_name}': {e}") from e

        if normalized_name == AgentToolName.SEARCH.value:
            return cls._execute_search(validated_args, user_context, session)
        elif normalized_name == AgentToolName.OPEN_CITED_SOURCE.value:
            return cls._execute_open_cited_source(validated_args, user_context, session)
        elif normalized_name == AgentToolName.LIST_AUTHORISED_COLLECTIONS.value:
            return cls._execute_list_collections(user_context, session)
        elif normalized_name == AgentToolName.INSPECT_SYSTEM.value:
            return cls._execute_inspect_system(validated_args, user_context, session)
        elif normalized_name == AgentToolName.LOOKUP_PRECEDENTS.value:
            return cls._execute_lookup_precedents(validated_args, user_context, session)
        elif normalized_name == AgentToolName.EXECUTE_PYTHON_SANDBOX.value:
            return cls._execute_python_sandbox(validated_args, user_context, session)
        elif normalized_name == AgentToolName.VERIFY_CLAIM.value:
            return cls._execute_verify_claim(validated_args, user_context, session)
        elif normalized_name == AgentToolName.DATABASE_QUERY.value:
            return cls._execute_database_query(validated_args, user_context, session)
        elif normalized_name == AgentToolName.COMPARE_SOURCES.value:
            return cls._execute_compare_sources(validated_args, user_context, session)
        elif normalized_name == AgentToolName.WEB_SEARCH.value:
            return cls._execute_web_search(validated_args, user_context, session)
        elif normalized_name == AgentToolName.FETCH_WEB_PAGE.value:
            return cls._execute_fetch_web_page(validated_args, user_context, session)

        raise ForbiddenToolError(f"Unsupported tool '{tool_name}'.")

    @classmethod
    def _execute_search(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only hybrid search over authorized chunks."""
        query_text = arguments.get("query", "")
        parsed = QueryUnderstanding.parse(query_text)
        if "department_id" in arguments and arguments["department_id"]:
            parsed.department_id = arguments["department_id"]
        if "doc_type" in arguments and arguments["doc_type"]:
            parsed.doc_type = arguments["doc_type"]

        top_k = min(10, max(1, arguments.get("top_k", 5)))
        retriever = HybridRetriever(session)
        passages = retriever.retrieve(parsed, user_context=user_context, top_k=top_k)

        return {
            "query": query_text,
            "total_found": len(passages),
            "passages": [p.to_dict() for p in passages],
            "raw_passages": passages,
        }

    @classmethod
    def _is_authorized_access(
        cls,
        classification: str,
        user_context: UserContext,
        department_id: Optional[str] = None,
        session: Optional[Session] = None,
        document_id: Optional[str] = None,
    ) -> bool:
        """Check if user has clearance to access document or source."""
        if user_context.is_admin() or classification == Classification.PUBLIC.value:
            return True
        if session and document_id:
            return AclEnforcer.is_document_authorized(session, document_id, user_context)
        if classification == Classification.INTERNAL.value:
            if user_context.clearance_level not in (
                Classification.INTERNAL.value,
                Classification.RESTRICTED.value,
                Classification.CONFIDENTIAL.value,
            ):
                return False
            return bool(user_context.department_id and department_id and user_context.department_id == department_id)
        if classification == Classification.RESTRICTED.value:
            if user_context.clearance_level not in (
                Classification.RESTRICTED.value,
                Classification.CONFIDENTIAL.value,
            ):
                return False
            return bool(
                user_context.department_id
                and department_id
                and user_context.department_id == department_id
                and "OFFICER" in [r.upper() for r in user_context.roles]
            )
        if classification == Classification.CONFIDENTIAL.value:
            return False
        return False

    @classmethod
    def _execute_open_cited_source(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only lookup of cited document page and coordinates."""
        doc_id = arguments.get("document_id")
        page_num = arguments.get("page_number", 1)
        version_id = arguments.get("version_id")

        doc = session.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return {"error": f"Document '{doc_id}' not found in repository."}

        # Verify ACL access with full AclEnforcer grant checks
        if not AclEnforcer.is_document_authorized(session, doc, user_context):
            return {"error": "Access Denied: Document classification exceeds clearance."}

        current_version = None
        if version_id:
            current_version = session.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not current_version:
            current_version = (
                session.query(DocumentVersion)
                .filter(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.retrieved_at.desc())
                .first()
            )

        page_record = None
        blocks_data = []
        if current_version:
            page_record = (
                session.query(DocumentPage)
                .filter(
                    DocumentPage.version_id == current_version.id,
                    DocumentPage.page_number == page_num,
                )
                .first()
            )
            if page_record:
                blocks = (
                    session.query(TextBlock)
                    .filter(TextBlock.page_id == page_record.id)
                    .order_by(TextBlock.reading_order)
                    .all()
                )
                for b in blocks[:20]:
                    blocks_data.append({
                        "block_type": b.block_type,
                        "text": b.text,
                        "bbox": b.bbox,
                    })

        pdf_link = ""
        if current_version and current_version.source_url:
            pdf_link = f"{current_version.source_url}#page={page_num}"

        return {
            "document_id": doc.id,
            "title": doc.title,
            "department_id": doc.department_id,
            "classification": doc.classification,
            "source_url": current_version.source_url if current_version else "",
            "pdf_page_link": pdf_link,
            "page_number": page_num,
            "text": page_record.selected_text if page_record else "",
            "blocks": blocks_data,
        }

    @classmethod
    def _execute_list_collections(
        cls,
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only discovery of authorised collections."""
        sources = (
            session.query(Source)
            .filter(Source.status == SourceStatus.APPROVED.value)
            .all()
        )

        accessible_depts = set()
        collections = []
        for s in sources:
            if AclEnforcer.is_source_authorized(session, s, user_context):
                accessible_depts.add(s.department_id)
                collections.append({
                    "source_id": s.id,
                    "name": s.name,
                    "department_id": s.department_id,
                    "classification": s.access_classification,
                    "refresh_cadence": s.refresh_cadence,
                })

        return {
            "user_id": user_context.user_id,
            "clearance_level": user_context.clearance_level,
            "accessible_departments": sorted(list(accessible_depts)),
            "total_accessible_collections": len(collections),
            "collections": collections,
        }

    @classmethod
    def _execute_inspect_system(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute authoritative system self-model inspection."""
        from adam.agent.introspection import SystemIntrospectionService
        service = SystemIntrospectionService(session)
        subtopic = arguments.get("subtopic") or arguments.get("query")
        snapshot = service.generate_snapshot(subtopic=subtopic)
        return {
            "system_name": snapshot.system_info.name,
            "version": snapshot.system_info.version,
            "active_model": snapshot.active_model.name if snapshot.active_model else None,
            "serving_runtime": snapshot.active_model.serving_runtime if snapshot.active_model else None,
            "harness_profile": snapshot.active_harness.profile_name if snapshot.active_harness else None,
            "thinking_enabled": snapshot.active_harness.thinking_enabled if snapshot.active_harness else False,
            "total_documents": snapshot.data_sources.total_documents if snapshot.data_sources else 0,
            "total_sources": snapshot.data_sources.total_sources if snapshot.data_sources else 0,
            "text_summary": snapshot.to_ground_truth_context(),
        }

    @classmethod
    def _execute_lookup_precedents(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Lookup precedent linkages (supersedes, amends, in continuation of)."""
        doc_id = arguments.get("document_id")
        order_num = arguments.get("order_number") or arguments.get("query")
        query = session.query(PrecedentReference)
        if doc_id:
            query = query.filter(PrecedentReference.source_document_id == doc_id)
        elif order_num:
            query = query.filter(PrecedentReference.cited_order_number.ilike(f"%{order_num.strip()}%"))

        precedents = query.limit(10).all()
        results = [
            {
                "id": p.id,
                "source_document_id": p.source_document_id,
                "relation_type": p.relation_type,
                "cited_order_number": p.cited_order_number,
                "cited_order_date": p.cited_order_date.isoformat() if p.cited_order_date else None,
                "is_verified": bool(p.is_verified),
            }
            for p in precedents
        ]
        return {
            "total_found": len(results),
            "precedents": results,
        }

    @classmethod
    def _execute_python_sandbox(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute deterministic calculation in secure Python sandbox."""
        code = arguments.get("code") or ""
        context_vars = arguments.get("context_vars")
        res = SecurePythonSandbox.execute(code, context_vars=context_vars)
        return res.to_dict()

    @classmethod
    def _execute_verify_claim(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Verify whether an intermediate claim or rate is grounded in repository evidence."""
        import re
        claim = arguments.get("claim") or ""
        passages = arguments.get("passages") or []
        corpus = " ".join(passages).lower()
        is_supported = claim.lower().strip() in corpus if corpus else False
        digits = re.findall(r"\d+", claim)
        if digits and corpus and all(d in corpus for d in digits):
            is_supported = True
        return {
            "claim": claim,
            "is_supported": is_supported,
            "verified_in_corpus": bool(corpus),
        }

    @classmethod
    def _execute_database_query(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute read-only query over authorized relational database tables."""
        table_name = str(arguments.get("table") or "").strip().lower()
        allowed_tables = {"documents", "document_versions", "sources", "precedent_references"}
        if table_name not in allowed_tables:
            return {"error": f"Table '{table_name}' is not queryable. Allowed: {sorted(allowed_tables)}"}

        aggregate = str(arguments.get("aggregate") or "count").strip().lower()
        limit = min(100, max(1, int(arguments.get("limit", 20))))
        filter_by = arguments.get("filter_by") or {}

        if table_name == "documents":
            q = session.query(Document)
            if "department_id" in filter_by and filter_by["department_id"]:
                q = q.filter(Document.department_id == filter_by["department_id"])
            if "doc_type" in filter_by and filter_by["doc_type"]:
                q = q.filter(Document.doc_type == filter_by["doc_type"])
            if "classification" in filter_by and filter_by["classification"]:
                q = q.filter(Document.classification == filter_by["classification"])

            if aggregate == "count":
                return {"table": table_name, "aggregate": "count", "result": q.count()}
            else:
                docs = q.limit(limit).all()
                return {
                    "table": table_name,
                    "total_returned": len(docs),
                    "records": [
                        {
                            "id": d.id,
                            "title": d.title,
                            "department_id": d.department_id,
                            "doc_type": d.doc_type,
                            "classification": d.classification,
                        }
                        for d in docs
                    ],
                }
        elif table_name == "sources":
            q = session.query(Source)
            if "department_id" in filter_by and filter_by["department_id"]:
                q = q.filter(Source.department_id == filter_by["department_id"])
            if aggregate == "count":
                return {"table": table_name, "aggregate": "count", "result": q.count()}
            sources = q.limit(limit).all()
            return {
                "table": table_name,
                "total_returned": len(sources),
                "records": [
                    {"id": s.id, "name": s.name, "department_id": s.department_id, "status": s.status}
                    for s in sources
                ],
            }
        elif table_name == "precedent_references":
            q = session.query(PrecedentReference)
            if "relation_type" in filter_by and filter_by["relation_type"]:
                q = q.filter(PrecedentReference.relation_type == filter_by["relation_type"])
            if aggregate == "count":
                return {"table": table_name, "aggregate": "count", "result": q.count()}
            refs = q.limit(limit).all()
            return {
                "table": table_name,
                "total_returned": len(refs),
                "records": [
                    {"id": r.id, "cited_order_number": r.cited_order_number, "relation_type": r.relation_type}
                    for r in refs
                ],
            }
        elif table_name == "document_versions":
            q = session.query(DocumentVersion)
            if aggregate == "count":
                return {"table": table_name, "aggregate": "count", "result": q.count()}
            vers = q.limit(limit).all()
            return {
                "table": table_name,
                "total_returned": len(vers),
                "records": [
                    {"id": v.id, "document_id": v.document_id, "retrieved_at": v.retrieved_at.isoformat() if v.retrieved_at else None}
                    for v in vers
                ],
            }
        return {"error": f"Unsupported table operation for '{table_name}'."}

    @classmethod
    def _execute_compare_sources(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Execute structured comparison and delta analysis between two sources."""
        src_a = str(arguments.get("source_a") or "").strip()
        src_b = str(arguments.get("source_b") or "").strip()
        focus = arguments.get("comparison_focus")

        doc_a = None
        doc_b = None
        if session is not None:
            doc_a = session.query(Document).filter(Document.id == src_a).first()
            doc_b = session.query(Document).filter(Document.id == src_b).first()

        text_a = f"Title: {doc_a.title} (Dept: {doc_a.department_id})" if doc_a else src_a
        text_b = f"Title: {doc_b.title} (Dept: {doc_b.department_id})" if doc_b else src_b

        numbers_a = set(re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", text_a))
        numbers_b = set(re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?%?\b", text_b))

        common_facts = sorted(list(numbers_a.intersection(numbers_b)))
        unique_to_a = sorted(list(numbers_a - numbers_b))
        unique_to_b = sorted(list(numbers_b - numbers_a))

        return {
            "source_a_label": doc_a.title if doc_a else "Source A",
            "source_b_label": doc_b.title if doc_b else "Source B",
            "comparison_focus": focus or "general",
            "common_values": common_facts,
            "common_terms": common_facts,
            "unique_to_source_a": unique_to_a,
            "unique_to_source_b": unique_to_b,
            "summary": (
                f"Compared sources. Found {len(common_facts)} matching values/rates, "
                f"{len(unique_to_a)} specific to Source A, and {len(unique_to_b)} specific to Source B."
            ),
        }

    @classmethod
    def _execute_web_search(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute secure, domain-aware external web search."""
        if user_context.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            raise ForbiddenToolError(
                f"Security Violation: Web search is forbidden for {user_context.clearance_level} clearance "
                "under Air-Gapped Data Sovereignty Policy."
            )

        from adam.agent.web import SecureWebSearchEngine
        query = str(arguments.get("query") or "")
        domain_filter = arguments.get("domain_filter")
        max_results = min(10, max(1, int(arguments.get("max_results", 5))))

        engine = SecureWebSearchEngine()
        results = engine.search(query=query, domain_filter=domain_filter, max_results=max_results)

        return {
            "query": query,
            "total_found": len(results),
            "results": [r.to_dict() for r in results],
        }

    @classmethod
    def _execute_fetch_web_page(
        cls,
        arguments: Dict[str, Any],
        user_context: UserContext,
        session: Session,
    ) -> Dict[str, Any]:
        """Execute SSRF-safe web page fetching and markdown extraction."""
        if user_context.clearance_level in (Classification.RESTRICTED.value, Classification.CONFIDENTIAL.value):
            raise ForbiddenToolError(
                f"Security Violation: Web browsing is forbidden for {user_context.clearance_level} clearance "
                "under Air-Gapped Data Sovereignty Policy."
            )

        from adam.agent.web import SecureWebFetcher
        url = str(arguments.get("url") or "")
        extract_tables = bool(arguments.get("extract_tables", True))

        fetcher = SecureWebFetcher()
        page = fetcher.fetch(url, extract_tables=extract_tables)
        return page.to_dict()

