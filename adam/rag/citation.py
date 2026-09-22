"""Citation construction and currency banner management adhering to the Phase 03 citation contract.

Per Phase 03 specification:
- 'Each answer citation exposes document title, department, GO/gazette number if known,
   version/hash, issue date, page, section, source URL, retrieval timestamp and a link to
   the original PDF page. A citation is a source pointer, not a claim of legal validity.'
- 'For amendments/repeals, show a currency banner: "Applicable status not conclusively determined"
   unless the corpus has an approved relationship and effective-date record. Never infer supersession
   from similar language alone.'
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from adam.rag.models import Citation, EvidencePassage, EvidencePacket


class CitationBuilder:
    """Constructs formal citations adhering to the ADAM citation contract."""

    LEGAL_DISCLAIMER = "A citation is a source pointer, not a claim of legal validity."
    DEFAULT_UNCERTAIN_BANNER = "Applicable status not conclusively determined"

    @classmethod
    def build_citation(
        cls,
        passage: EvidencePassage,
        currency_banner: Optional[str] = None,
    ) -> Citation:
        """Construct a Citation instance from an EvidencePassage."""
        # PDF page link: standard web PDF page anchor #page=N
        pdf_page_link = ""
        if passage.source_url:
            pdf_page_link = f"{passage.source_url}#page={passage.page_start}"

        issue_date_str = passage.order_date.isoformat() if passage.order_date else None

        # Sample primary bbox if available
        bbox = passage.bbox_list[0] if (passage.bbox_list and isinstance(passage.bbox_list[0], list)) else None

        # Format specific currency banner for this citation if amended/superseded/uncertain
        eff_banner = currency_banner
        if passage.currency_status == "UNCERTAIN" and not eff_banner:
            eff_banner = cls.DEFAULT_UNCERTAIN_BANNER
        elif passage.currency_status in ("AMENDED", "SUPERSEDED") and not eff_banner:
            eff_banner = cls.DEFAULT_UNCERTAIN_BANNER

        is_ext = getattr(passage, "is_external", False)
        ext_url = getattr(passage, "external_url", None)
        ext_domain = getattr(passage, "external_domain", None)

        if is_ext:
            pdf_page_link = ext_url or passage.source_url or ""
            disclaimer_text = "External Web Source - Consulted for comparative/supplementary context; not an official Uttarakhand State repository record."
        else:
            disclaimer_text = cls.LEGAL_DISCLAIMER

        return Citation(
            document_title=passage.title,
            department=passage.department_id,
            document_id=passage.document_id,
            go_number=passage.go_number,
            gazette_number=passage.gazette_number,
            version_hash=passage.sha256 or passage.version_id,
            issue_date=issue_date_str,
            page=passage.page_start,
            section=passage.section_heading,
            source_url=passage.source_url or "",
            retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
            pdf_page_link=pdf_page_link,
            bbox=bbox,
            currency_banner=eff_banner,
            disclaimer=disclaimer_text,
            is_external=is_ext,
            provenance_type="EXTERNAL_WEB" if is_ext else "INTERNAL_REPOSITORY",
            external_domain=ext_domain,
        )

    @classmethod
    def build_citations_from_packet(cls, packet: EvidencePacket) -> List[Citation]:
        """Build a list of unique citations from an EvidencePacket, preserving order."""
        citations: List[Citation] = []
        seen_keys = set()

        for p in packet.passages:
            key = (p.document_id, p.page_start, p.section_heading)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            cit = cls.build_citation(p, currency_banner=packet.currency_banner)
            citations.append(cit)

        return citations

    @classmethod
    def format_citation_markdown(cls, citation: Citation, index: int = 1) -> str:
        """Format citation as human-readable Markdown with direct page link and metadata."""
        go_str = f", GO: {citation.go_number}" if citation.go_number else ""
        date_str = f", Date: {citation.issue_date}" if citation.issue_date else ""
        sec_str = f", Section: {citation.section}" if citation.section else ""
        link_str = f" [View Original PDF Page]({citation.pdf_page_link})" if citation.pdf_page_link else ""

        banner_md = ""
        if citation.currency_banner:
            banner_md = f"\n   *Currency Alert: {citation.currency_banner}*"

        if citation.is_external:
            tag = f"[WEB-{index}]"
            domain_info = f" ({citation.external_domain})" if citation.external_domain else ""
            link_str = f" [Open External Web Source]({citation.pdf_page_link})" if citation.pdf_page_link else ""
            return (
                f"{tag} **{citation.document_title}**{domain_info}{link_str}\n"
                f"   *Web URL:* {citation.source_url or citation.pdf_page_link}\n"
                f"   *Provenance Notice:* {citation.disclaimer}"
            )

        return (
            f"[{index}] **{citation.document_title}** ({citation.department}{go_str}{date_str}, "
            f"Page {citation.page}{sec_str}){link_str}\n"
            f"   *Source URL:* {citation.source_url} | *Hash:* `{citation.version_hash[:12] if citation.version_hash else 'N/A'}`\n"
            f"   *Notice:* {citation.disclaimer}{banner_md}"
        )


# Convenience module-level export
format_citation_markdown = CitationBuilder.format_citation_markdown

