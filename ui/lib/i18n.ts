/**
 * Bilingual localization layer (English / Hindi Devanagari) for ADAM Uttarakhand Portal (H7).
 */

export type LanguageCode = "en" | "hi";

export interface Translations {
  appName: string;
  appSubtitle: string;
  stateName: string;
  department: string;
  clearanceLevel: string;
  role: string;
  login: string;
  logout: string;
  queryPlaceholder: string;
  submitQuery: string;
  askingQuestion: string;
  citedSources: string;
  sourceDocument: string;
  pageNumber: string;
  orderNumber: string;
  effectiveDate: string;
  confidenceScore: string;
  refusalTitle: string;
  refusalMessage: string;
  evidencePacket: string;
  verifiedFactual: string;
  supersededNotice: string;
  uploadDocument: string;
  dragAndDrop: string;
  browseFiles: string;
  sourcesCatalog: string;
  auditTrail: string;
  systemHealth: string;
  governanceStatus: string;
  airGappedBadge: string;
  clearancePublic: string;
  clearanceInternal: string;
  clearanceRestricted: string;
  clearanceConfidential: string;
  clearanceAdmin: string;
}

export const translations: Record<LanguageCode, Translations> = {
  en: {
    appName: "ADAM",
    appSubtitle: "Uttarakhand Public Records Acquisition & Citizen Intelligence Platform",
    stateName: "Government of Uttarakhand",
    department: "Department",
    clearanceLevel: "Clearance Level",
    role: "User Role",
    login: "Sign In",
    logout: "Sign Out",
    queryPlaceholder: "Ask a question about Uttarakhand Government orders, rules, or schemes...",
    submitQuery: "Send Query",
    askingQuestion: "Synthesizing verified administrative records...",
    citedSources: "Cited Official Sources",
    sourceDocument: "Document",
    pageNumber: "Page",
    orderNumber: "GO Number",
    effectiveDate: "Effective Date",
    confidenceScore: "Confidence",
    refusalTitle: "No Authoritative Records Found",
    refusalMessage: "No official Uttarakhand government order or gazette in the authorized corpus supports an answer to this query.",
    evidencePacket: "Evidence Packet",
    verifiedFactual: "Statutory Grounding Verified",
    supersededNotice: "This order has been superseded or amended by subsequent notifications.",
    uploadDocument: "Upload Administrative Record",
    dragAndDrop: "Drag and drop government order PDFs or scanned records here",
    browseFiles: "Browse Files",
    sourcesCatalog: "Authorized Sources",
    auditTrail: "Audit Trail",
    systemHealth: "System Diagnostics",
    governanceStatus: "Compliance & Governance",
    airGappedBadge: "Sovereign Air-Gapped",
    clearancePublic: "Public",
    clearanceInternal: "Internal",
    clearanceRestricted: "Restricted",
    clearanceConfidential: "Confidential",
    clearanceAdmin: "Administrative Master",
  },
  hi: {
    appName: "एडम (ADAM)",
    appSubtitle: "उत्तराखण्ड लोक अभिलेख अर्जन एवं नागरिक अभिसूचना प्रणाली",
    stateName: "उत्तराखण्ड शासन",
    department: "विभाग",
    clearanceLevel: "गोपनीयता स्तर",
    role: "उपयोगकर्ता भूमिका",
    login: "साइन इन",
    logout: "लॉग आउट",
    queryPlaceholder: "शासनादेशों, सेवा नियमावलियों अथवा राज्य योजनाओं के संबंध में प्रश्न पूछें...",
    submitQuery: "प्रश्न भेजें",
    askingQuestion: "प्रमाणित प्रशासनिक अभिलेखों का विश्लेषण जारी है...",
    citedSources: "उद्धृत आधिकारिक स्रोत",
    sourceDocument: "दस्तावेज़",
    pageNumber: "पृष्ठ संख्या",
    orderNumber: "शासनादेश संख्या",
    effectiveDate: "प्रभावी तिथि",
    confidenceScore: "विश्वसनीयता",
    refusalTitle: "कोई आधिकारिक अभिलेख उपलब्ध नहीं",
    refusalMessage: "अधिकृत अभिलेख संग्रह में इस प्रश्न का उत्तर देने हेतु कोई प्रामाणिक शासनादेश अथवा राजपत्र उपलब्ध नहीं है।",
    evidencePacket: "साक्ष्य विवरण (एविडेंस पैकेट)",
    verifiedFactual: "वैधानिक पुष्टि सत्यापित",
    supersededNotice: "यह शासनादेश परवर्ती अधिसूचनाओं द्वारा अधिक्रमित अथवा संशोधित किया जा चुका है।",
    uploadDocument: "शासकीय अभिलेख अपलोड करें",
    dragAndDrop: "शासनादेश की पीडीएफ अथवा स्कैन प्रति यहाँ खींचें व छोड़ें",
    browseFiles: "फ़ाइलें चुनें",
    sourcesCatalog: "अधिकृत स्रोत सूची",
    auditTrail: "लेखा परीक्षा एवं ऑडिट ट्रेल",
    systemHealth: "प्रणाली निदान",
    governanceStatus: "अनुपालन एवं अभिशासन",
    airGappedBadge: "संप्रभु एयर-गैप्ड",
    clearancePublic: "सार्वजनिक (पब्लिक)",
    clearanceInternal: "आंतरिक (इंटरनल)",
    clearanceRestricted: "प्रतिबंधित (रिस्ट्रिक्टेड)",
    clearanceConfidential: "गोपनीय (कॉन्फिडेंशियल)",
    clearanceAdmin: "प्रशासनिक मास्टर",
  },
};

export function getTranslation(lang: LanguageCode = "en"): Translations {
  return translations[lang] || translations.en;
}
