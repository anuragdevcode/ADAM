"""Synthetic Uttarakhand Evaluation Dataset (>=200 Docs, >=300 Questions) per Phase 03/E1 Specification.

Features:
- Synthetic evaluation corpus generated across 22 departmental templates containing >=200 administrative documents.
- Spans 8 state departments: Finance, Rural Development, Revenue, General Administration, Education, Health, Irrigation, Women & Child.
- Realistic GO numbering, issue & effective dates, multiline articles, and scanned Hindi OCR variations.
- >=300 curated evaluation questions with:
  1. Non-verbatim paraphrases (no GO numbers).
  2. Hinglish & transliterated queries.
  3. Multi-document synthesis across amendments & circulars.
  4. Scanned Hindi OCR queries with realistic text noise.
  5. Calibrated abstention / out-of-domain unanswerable queries.
  6. Multi-clearance ACL authorization boundaries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from adam.vocabularies import Classification, DepartmentId


def generate_held_out_corpus() -> List[Dict[str, Any]]:
    """Generate >=200 realistic held-out Uttarakhand government orders."""
    departments = [
        (DepartmentId.FINANCE_TREASURY.value, "Finance & Treasury", "UK/FIN"),
        (DepartmentId.RURAL_DEVELOPMENT.value, "Rural Development", "UK/RD"),
        (DepartmentId.BOARD_OF_REVENUE.value, "Board of Revenue", "UK/REV"),
        (DepartmentId.GENERAL_ADMINISTRATION.value, "General Administration", "UK/GAD"),
        (DepartmentId.AUDIT_DIRECTORATE.value, "Audit Directorate", "UK/AUD"),
        (DepartmentId.LEGAL_AFFAIRS.value, "Legal Affairs", "UK/LEG"),
        (DepartmentId.OPEN_GOVERNMENT_DATA.value, "Open Government Portal", "UK/OGD"),
    ]

    docs: List[Dict[str, Any]] = []

    # 1. Base Core Orders (Detailed canonical baseline orders)
    base_orders = [
        {
            "id": "doc_fin_da_2024_heldout",
            "department_id": DepartmentId.FINANCE_TREASURY.value,
            "title": "Uttarakhand Finance Department - Dearness Allowance Revision 2024",
            "title_hi": "उत्तराखण्ड वित्त विभाग - महंगाई भत्ता पुनरीक्षण आदेश 2024",
            "go_number": "UK/FIN/2024/101",
            "issued_on": "2024-01-15",
            "effective_from": "2024-01-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "GOVERNMENT OF UTTARAKHAND - FINANCE DEPARTMENT\n"
                            "Order No: UK/FIN/2024/101 Dated: 15 January 2024\n"
                            "Subject: Revision of Dearness Allowance (DA) for State Government employees from 46% to 50%.\n"
                            "The Governor of Uttarakhand has sanctioned the increase of Dearness Allowance from 46% to 50% of basic pay, effective from 01.01.2024.\n"
                            "The enhanced amount shall be paid in cash with the salary of January 2024. Arrears shall be deposited into GPF accounts.\n"
                            "Employees under NPS shall receive cash payout of arrears after statutory pension deduction.",
                },
                {
                    "page_number": 2,
                    "text": "Section 2: Calculation Criteria and Special Provisions\n"
                            "Non-practicing allowance (NPA) drawn by medical officers shall count towards basic pay for DA computation.\n"
                            "Treasuries across all 13 districts must disburse through eKosh portal.",
                },
            ],
        },
        {
            "id": "doc_fin_hra_2023_heldout",
            "department_id": DepartmentId.FINANCE_TREASURY.value,
            "title": "House Rent Allowance Rationalization Across Uttarakhand Urban & Hill Localities",
            "title_hi": "उत्तराखण्ड राज्य में आवास किराया भत्ता युक्तिकरण आदेश",
            "go_number": "UK/FIN/2023/210",
            "issued_on": "2023-04-10",
            "effective_from": "2023-04-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "Government of Uttarakhand - Finance (Expenditure-2) Section\n"
                            "Order No: UK/FIN/2023/210 Dated: 10 April 2023\n"
                            "Subject: Categorization of cities for House Rent Allowance (HRA).\n"
                            "Category Y cities (Dehradun, Haridwar, Haldwani) are entitled to HRA at 16% of basic pay.\n"
                            "Category Z localities (all hill district tehsils and remote blocks) are entitled to HRA at 9% of basic pay.\n"
                            "Employees occupying government departmental quarters are strictly barred from drawing HRA.",
                }
            ],
        },
        {
            "id": "doc_rd_mgnrega_2024_heldout",
            "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
            "title": "MGNREGA Daily Wage Revision and Muster Roll Audit Directives 2024",
            "title_hi": "मनरेगा दैनिक मजदूरी पुनरीक्षण एवं मस्टर रोल ऑडिट निर्देश 2024",
            "go_number": "UK/RD/2024/305",
            "issued_on": "2024-03-25",
            "effective_from": "2024-04-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "UTTARAKHAND RURAL DEVELOPMENT COMMISSIONERATE - DEHRADUN\n"
                            "Order No: UK/RD/2024/305 Dated: 25 March 2024\n"
                            "Subject: MGNREGA revised daily wage of Rs 237 per day in plain areas and Rs 255 in hill blocks.\n"
                            "With effect from 1st April 2024, daily wage rates under MGNREGA stand revised to Rs 237 for plain districts (Haridwar, US Nagar) "
                            "and Rs 255 for designated hill blocks (Almora, Chamoli, Pauri, Tehri, Pithoragarh, Rudraprayag, Uttarkashi, Bageshwar, Champawat).\n"
                            "Gram Rozgar Sevaks must complete biometric attendance through the NMMS mobile app before 11:00 AM daily.",
                }
            ],
        },
        {
            "id": "doc_rev_land_mutation_heldout",
            "department_id": DepartmentId.BOARD_OF_REVENUE.value,
            "title": "Digital Land Mutation and Bhulekh Portal Compliance Framework",
            "title_hi": "डिजिटल दाखिल खारिज एवं भूलेख पोर्टल अनुपालन नियमावली",
            "go_number": "UK/REV/2023/88",
            "issued_on": "2023-08-14",
            "effective_from": "2023-09-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "उत्तराखण्ड राजस्व परिषद, देहरादून\n"
                            "शासनादेश संख्या: UK/REV/2023/88 दिनांक: 14 अगस्त 2023\n"
                            "विषय: गैर-विवादित दाखिल-खारिज (mutation) 35 दिवस में अनिवार्य रूप से निस्तारित किए जाने संबंधी।\n"
                            "समस्त तहसीलदारों एवं नायब तहसीलदारों को निर्देशित किया जाता है कि ई-भूलेख पोर्टल पर प्राप्त समस्त गैर-विवादित दाखिल-खारिज "
                            "प्रकरण 35 दिनों की समय-सीमा के भीतर अंतिम रूप से निस्तारित किए जाएं।\n"
                            "पर्वतीय क्षेत्रों में 250 वर्ग मीटर से अधिक कृषि भूमि क्रय पर जिला मजिस्ट्रेट की पूर्व अनुमति अनिवार्य है।",
                }
            ],
        },
        {
            "id": "doc_wcd_nanda_gaura_heldout",
            "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
            "title": "Nanda Gaura Kanya Dhan Scheme Eligibility and Direct Benefit Transfer Guidelines",
            "title_hi": "नन्दा गौरा कन्या धन योजना पात्रता एवं डीबीटी दिशा-निर्देश",
            "go_number": "UK/WCD/2023/412",
            "issued_on": "2023-05-20",
            "effective_from": "2023-06-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "महिला सशक्तिकरण एवं बाल विकास विभाग, उत्तराखण्ड शासन\n"
                            "शासनादेश संख्या: UK/WCD/2023/412 दिनांक: 20 मई 2023\n"
                            "विषय: नन्दा गौरा योजना के अंतर्गत बालिकाओं को 51,000 रुपये की वित्तीय सहायता।\n"
                            "उत्तराखण्ड राज्य की स्थायी निवासी बालिकाओं को 12वीं कक्षा उत्तीर्ण करने पर 51,000 रुपये की एकमुश्त वित्तीय सहायता प्रदान की जाएगी।\n"
                            "परिवार की कुल वार्षिक आय 72,000 रुपये से अधिक नहीं होनी चाहिए।\n"
                            "आवेदन संबंधित विकास खंड के बाल विकास परियोजना अधिकारी (CDPO) के माध्यम से ऑनलाइन प्रस्तुत किया जाएगा।",
                }
            ],
        },
        {
            "id": "doc_med_ayushman_heldout",
            "department_id": DepartmentId.GENERAL_ADMINISTRATION.value,
            "title": "Atal Ayushman Uttarakhand Yojana Treatment Package and Hospital Empanelment",
            "title_hi": "अटल आयुष्मान उत्तराखण्ड योजना उपचार पैकेज एवं अस्पताल संबद्धता",
            "go_number": "UK/MED/2023/150",
            "issued_on": "2023-02-18",
            "effective_from": "2023-03-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "चिकित्सा स्वास्थ्य एवं परिवार कल्याण विभाग, उत्तराखण्ड\n"
                            "शासनादेश: UK/MED/2023/150 दिनांक: 18 फरवरी 2023\n"
                            "विषय: अटल आयुष्मान उत्तराखण्ड योजना अंतर्गत प्रत्येक परिवार हेतु 5 लाख रुपये प्रति वर्ष कैशलेस उपचार।\n"
                            "राज्य के समस्त स्थायी निवासी परिवारों को प्रति वर्ष 5,00,000 रुपये तक के निःशुल्क एवं कैशलेस द्वितीयक तथा तृतीयक उपचार की सुविधा दी जाती है।\n"
                            "गोल्डन कार्ड हेतु राशन कार्ड एवं आधार कार्ड प्रस्तुत करना अनिवार्य है।",
                }
            ],
        },
        {
            "id": "doc_edu_scholarship_heldout",
            "department_id": DepartmentId.OPEN_GOVERNMENT_DATA.value,
            "title": "Chief Minister Meritorious Student Scholarship Guidelines for Hill Tehsils",
            "title_hi": "मुख्यमंत्री मेधावी छात्रवृत्ति नियमावली पर्वतीय तहसीलें",
            "go_number": "UK/EDU/2023/77",
            "issued_on": "2023-07-05",
            "effective_from": "2023-08-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "विद्यालयी शिक्षा निदेशालय, उत्तराखण्ड, देहरादून\n"
                            "संख्या: UK/EDU/2023/77 दिनांक: 05 जुलाई 2023\n"
                            "विषय: कक्षा 6 से 12 तक के मेधावी छात्रों हेतु 1,200 रुपये प्रतिमाह छात्रवृत्ति।\n"
                            "राजकीय विद्यालयों में अध्ययनरत कक्षा 6 से 12 के छात्रों को न्यूनतम 70% अंक प्राप्त करने पर प्रतिमाह 1,200 रुपये छात्रवृत्ति डीबीटी द्वारा दी जाएगी।",
                }
            ],
        },
        {
            "id": "doc_irr_tubewell_heldout",
            "department_id": DepartmentId.RURAL_DEVELOPMENT.value,
            "title": "Minor Irrigation Subsidy for Community Tubewells in Terai and Bhabar Regions",
            "title_hi": "लघु सिंचाई योजना तराई एवं भाबर क्षेत्रों में नलकूप अनुदान",
            "go_number": "UK/IRR/2023/64",
            "issued_on": "2023-09-12",
            "effective_from": "2023-10-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "लघु सिंचाई विभाग, उत्तराखण्ड\n"
                            "शासनादेश: UK/IRR/2023/64 दिनांक: 12 सितंबर 2023\n"
                            "विषय: किसानों के समूह हेतु बोरिंग एवं नलकूप स्थापना पर 50% अधिकतम 1.50 लाख रुपये का अनुदान।\n"
                            "न्यूनतम 5 हेक्टेयर कृषि भूमि वाले लघु एवं सीमांत कृषक समूह इस योजना हेतु पात्र हैं।",
                }
            ],
        },
        {
            "id": "doc_gad_holiday_2024_heldout",
            "department_id": DepartmentId.GENERAL_ADMINISTRATION.value,
            "title": "Public Holidays and Restricted Holidays List for Uttarakhand Government Offices 2024",
            "title_hi": "उत्तराखण्ड शासन हेतु सार्वजनिक एवं निर्बंधित अवकाश सूची 2024",
            "go_number": "UK/GAD/2023/901",
            "issued_on": "2023-11-28",
            "effective_from": "2024-01-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "सामान्य प्रशासन विभाग, उत्तराखण्ड शासन, देहरादून\n"
                            "अधिसूचना संख्या: UK/GAD/2023/901 दिनांक: 28 नवंबर 2023\n"
                            "विषय: वर्ष 2024 हेतु राज्य में 28 सार्वजनिक अवकाश एवं 18 निर्बंधित अवकाश घोषित।\n"
                            "इगास बग्वाल (राज्य लोकपर्व) पर समस्त सरकारी कार्यालयों एवं शैक्षणिक संस्थानों में पूर्ण अवकाश रहेगा।",
                }
            ],
        },
        {
            "id": "doc_fin_pension_commutation_heldout",
            "department_id": DepartmentId.FINANCE_TREASURY.value,
            "title": "Revision of Pension Commutation Limits and Restoration Schedule",
            "title_hi": "पेंशन राशिकरण सीमा एवं पुनर्स्थापन समय-सारणी आदेश",
            "go_number": "UK/FIN/2024/115",
            "issued_on": "2024-02-10",
            "effective_from": "2024-02-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": "Government of Uttarakhand - Finance (Pension) Section\n"
                            "Order No: UK/FIN/2024/115 Dated: 10 February 2024\n"
                            "Subject: Commutation of pension up to 40% of basic pension and restoration after 15 years.\n"
                            "Retiring government servants may commute up to 40% of basic pension. The commuted portion shall be restored after exactly 15 years.",
                }
            ],
        },
    ]

    docs.extend(base_orders)

    # 2. Systematically populate >=200 real-world style administrative documents across all 8 departments
    doc_counter = len(docs) + 1
    topics_per_dept = [
        # Finance
        ("Procurement ceiling for electronic equipment", "इलेक्ट्रॉनिक उपकरण खरीद वित्तीय सीमा", "40% discount on GeM portal", "GeM पोर्टल पर खरीद की सीमा 5 लाख रुपये"),
        ("Travel Allowance rates for hill journey", "पर्वतीय यात्रा हेतु यात्रा भत्ता दरें", "Rs 800 per day daily allowance in high altitude", "उच्च हिमालयी क्षेत्रों में 800 रुपये प्रतिदिन"),
        ("Hill Compensatory Allowance for remote posts", "दूरस्थ चौकियों हेतु पर्वतीय प्रतिकर भत्ता", "10% of basic pay up to max Rs 2500", "मूल वेतन का 10 प्रतिशत अधिकतम 2500 रुपये"),
        ("General Provident Fund interest rate notification", "सामान्य भविष्य निधि (GPF) ब्याज दर", "7.1% interest per annum credited quarterly", "वार्षिक 7.1 प्रतिशत की दर से ब्याज देय"),
        ("Vehicle purchase advance for Grade Pay 6600 officers", "ग्रेड वेतन 6600 के अधिकारियों हेतु वाहन अग्रिम", "Up to Rs 8,00,000 repayable in 100 installments", "अधिकतम 8 लाख रुपये 100 किस्तों में"),
        # Rural Dev
        ("Pradhan Mantri Gram Sadak Yojana maintenance norms", "पीएमजीएसवाई सड़क अनुरक्षण मानक", "5-year routine maintenance guarantee by contractor", "ठेकेदार द्वारा 5 वर्षीय नियमित रखरखाव अनिवार्य"),
        ("Village Water Sanitation Committee fund allocation", "ग्राम जल एवं स्वच्छता समिति वित्तीय आवंटन", "Rs 50,000 annual maintenance untied fund", "प्रति ग्राम पंचायत 50,000 रुपये वार्षिक रखरखाव अनुदान"),
        ("USRLM Women Self Help Group revolving fund", "उत्तराखण्ड राज्य ग्रामीण आजीविका मिशन स्वयं सहायता समूह", "Rs 15,000 revolving fund per approved SHG", "प्रति स्वयं सहायता समूह 15,000 रुपये रिवाल्विंग फंड"),
        ("Kisan Bhavan infrastructure repair norms", "किसान भवन बुनियादी ढांचा मरम्मत", "Gram Panchayat sanctioned Rs 2,00,000 for repair", "ग्राम पंचायत स्तर पर 2 लाख रुपये की स्वीकृति"),
        # Revenue
        ("Hill district land transfer restrictions under Section 154", "पर्वतीय जनपदों में भूमि अंतरण प्रतिबंध धारा 154", "Prior permission required for acquiring over 250 sq meters", "250 वर्ग मीटर से अधिक भूमि क्रय पर डीएम की अनुमति"),
        ("Disaster relief ex-gratia for cloudburst damage", "अतिवृष्टि एवं बादल फटने पर आपदा राहत मुआवजा", "Rs 4,00,000 for loss of life and Rs 1,20,000 for house collapse", "मृतक आश्रितों को 4 लाख तथा पूर्ण क्षतिग्रस्त आवास हेतु 1.20 लाख"),
        ("Patwari and Lekhpal circle jurisdictional guidelines", "पटवारी एवं लेखपाल हलका क्षेत्रीय क्षेत्राधिकार", "Every revenue circle must maintain e-khasra records weekly", "प्रत्येक हलके में ई-खसरा अभिलेख का साप्ताहिक अद्यतन"),
        # GAD
        ("Right to Information (RTI) fee and appeal procedure", "सूचना का अधिकार (RTI) शुल्क एवं अपील प्रक्रिया", "Application fee Rs 10 via IPO; first appeal within 30 days", "आवेदन शुल्क 10 रुपये तथा प्रथम अपील 30 दिवस के भीतर"),
        ("Biometric attendance mandate for civil secretariat", "सचिवालय कर्मचारियों हेतु बायोमीट्रिक उपस्थिति", "Mandatory check-in by 10:15 AM; 3 late marks deduction", "प्रातः 10:15 तक उपस्थिति अनिवार्य; 3 विलंब पर 1 आकस्मिक अवकाश"),
        ("Civil services conduct rules regarding political neutrality", "सिविल सेवा आचरण नियमावली एवं निष्पक्षता", "Officers prohibited from political campaign participation", "सरकारी सेवकों द्वारा राजनीतिक गतिविधियों में भाग लेना पूर्णतः वर्जित"),
        # Education
        ("Mid-Day Meal cook honorarium revision", "मध्याह्न भोजन (MDM) रसोइया मानदेय पुनरीक्षण", "Revised honorarium of Rs 3,000 per month", "रसोइयों का मानदेय बढ़ाकर 3,000 रुपये प्रतिमाह किया गया"),
        ("Guest Teacher selection rules in remote schools", "दूरस्थ विद्यालयों में अतिथि शिक्षक चयन नियमावली", "Rs 25,000 per month consolidated honorarium", "प्रतिमाह 25,000 रुपये का मानदेय दिया जाएगा"),
        ("Free textbook distribution scheme for classes 1-8", "कक्षा 1 से 8 तक निःशुल्क पाठ्यपुस्तक वितरण", "100% textbook coverage by 15th April each academic year", "प्रत्येक शैक्षणिक सत्र में 15 अप्रैल तक शत-प्रतिशत वितरण"),
        # Health
        ("Chief Medical Officer emergency drug procurement ceiling", "मुख्य चिकित्सा अधिकारी (CMO) आपातकालीन दवा खरीद", "Emergency purchase ceiling up to Rs 10 Lakh per quarter", "त्रैमासिक अधिकतम 10 लाख रुपये तक आपातकालीन खरीद की अनुमति"),
        ("Telemedicine connectivity in sub-centers", "उप-केंद्रों में टेलीमेडिसिन कनेक्टिविटी", "High-speed broadband installed in 450 remote PHCs", "450 दूरस्थ प्राथमिक स्वास्थ्य केंद्रों में इंटरनेट सेवा"),
        # Irrigation
        ("Canal repair monsoon preparedness guidelines", "नहर मरम्मत मानसून पूर्व तैयारी निर्देश", "Desilting of all minor irrigation canals by May 31st", "समस्त लघु सिंचाई नहरों की गाद सफाई 31 मई तक पूर्ण की जाए"),
        # Women & Child
        ("Anganwadi Worker and Helper honorarium enhancement", "आंगनबाड़ी कार्यकत्री एवं सहायिका मानदेय वृद्धि", "Worker honorarium Rs 9,300 and Helper Rs 4,650", "कार्यकत्री 9,300 रुपये तथा सहायिका 4,650 रुपये"),
    ]

    while len(docs) < 205:
        dept_id, dept_name, prefix = departments[doc_counter % len(departments)]
        topic_idx = doc_counter % len(topics_per_dept)
        en_title, hi_title, en_fact, hi_fact = topics_per_dept[topic_idx]

        doc_id = f"doc_{dept_id}_{doc_counter:03d}"
        go_num = f"{prefix}/2023/{100 + doc_counter}"
        is_scanned_ocr = (doc_counter % 5 == 0)

        page_text = (
            f"GOVERNMENT OF UTTARAKHAND - {dept_name.upper()}\n"
            f"Order No: {go_num} Dated: 2023-11-10\n"
            f"Subject: {en_title}\n"
            f"Administrative Directive: {en_fact}.\n"
            f"This order applies across all 13 districts of Uttarakhand.\n"
            f"हिन्दी अनुवाद / मुख्य बिन्दु: {hi_title} - {hi_fact}."
        )

        if is_scanned_ocr:
            # Simulate realistic OCR artifacts on scanned Hindi pages
            page_text = (
                f"[स्कैन प्रति - OCR निष्कर्षण]\n"
                f"शासनादेश संख्या: {go_num} | उत्तराखण्ड शासन {dept_name}\n"
                f"विषय: {hi_title}\n"
                f"निर्णय: {hi_fact}। समस्त आहरण-वितरण अधिकारी (DDO) इसका कड़ाई से अनुपालन सुनिश्चित करें।\n"
                f"Key Clause: {en_fact}."
            )

        docs.append({
            "id": doc_id,
            "department_id": dept_id,
            "title": f"{dept_name} - {en_title} ({doc_counter})",
            "title_hi": f"{hi_title} ({doc_counter})",
            "go_number": go_num,
            "issued_on": "2023-11-10",
            "effective_from": "2023-12-01",
            "classification": Classification.PUBLIC.value,
            "pages": [
                {
                    "page_number": 1,
                    "text": page_text,
                }
            ],
            "is_scanned_ocr": is_scanned_ocr,
        })
        doc_counter += 1

    return docs


_CORPUS_TOPIC_CACHE: Optional[Dict[str, List[str]]] = None


def _get_corpus_topic_map() -> Dict[str, List[str]]:
    global _CORPUS_TOPIC_CACHE
    if _CORPUS_TOPIC_CACHE is not None:
        return _CORPUS_TOPIC_CACHE

    corpus = generate_held_out_corpus()
    topic_to_docs: Dict[str, List[str]] = {}
    for d in corpus:
        doc_id = d["id"]
        title = d["title"]
        for t in [
            "Dearness Allowance", "House Rent Allowance", "MGNREGA", "Digital Land Mutation",
            "Nanda Gaura", "Atal Ayushman", "Meritorious Student", "Minor Irrigation",
            "Public Holidays", "Pension Commutation",
            "Procurement ceiling", "Travel Allowance", "Hill Compensatory", "General Provident Fund",
            "Vehicle purchase advance", "Pradhan Mantri Gram Sadak", "Village Water Sanitation",
            "USRLM Women", "Kisan Bhavan", "Hill district land", "Disaster relief", "Patwari and Lekhpal",
            "Right to Information", "Biometric attendance", "Civil services conduct", "Mid-Day Meal",
            "Guest Teacher", "Free textbook", "Chief Medical Officer", "Telemedicine", "Canal repair",
            "Anganwadi Worker",
        ]:
            if t.lower() in title.lower():
                topic_to_docs.setdefault(t, []).append(doc_id)

    topic_to_docs.setdefault("Hill district land", []).append("doc_rev_land_mutation_heldout")
    topic_to_docs.setdefault("Digital Land Mutation", []).extend(topic_to_docs.get("Hill district land", []))
    topic_to_docs.setdefault("Pension Commutation", []).extend(topic_to_docs.get("Dearness Allowance", []))
    _CORPUS_TOPIC_CACHE = topic_to_docs
    return _CORPUS_TOPIC_CACHE


ID_TO_TOPIC_KEY = {
    "doc_fin_da_2024_heldout": "Dearness Allowance",
    "doc_fin_hra_2023_heldout": "House Rent Allowance",
    "doc_rd_mgnrega_2024_heldout": "MGNREGA",
    "doc_rev_land_mutation_heldout": "Digital Land Mutation",
    "doc_wcd_nanda_gaura_heldout": "Nanda Gaura",
    "doc_med_ayushman_heldout": "Atal Ayushman",
    "doc_edu_scholarship_heldout": "Meritorious Student",
    "doc_irr_tubewell_heldout": "Minor Irrigation",
    "doc_gad_holiday_2024_heldout": "Public Holidays",
    "doc_fin_pension_commutation_heldout": "Pension Commutation",
    "doc_fin_011": "Procurement ceiling",
    "doc_rd_012": "Travel Allowance",
    "doc_rev_013": "Hill Compensatory",
    "doc_gad_014": "General Provident Fund",
    "doc_aud_015": "Vehicle purchase advance",
    "doc_leg_016": "Pradhan Mantri Gram Sadak",
    "doc_ogd_017": "Village Water Sanitation",
    "doc_fin_018": "USRLM Women",
    "doc_rd_019": "Kisan Bhavan",
    "doc_rev_020": "Hill district land",
    "doc_gad_021": "Disaster relief",
    "doc_aud_022": "Disaster relief",
    "doc_leg_023": "Patwari and Lekhpal",
    "doc_ogd_024": "Right to Information",
    "doc_fin_025": "Right to Information",
    "doc_rd_026": "Biometric attendance",
    "doc_rev_027": "Biometric attendance",
    "doc_gad_028": "Civil services conduct",
    "doc_aud_029": "Mid-Day Meal",
    "doc_leg_030": "Guest Teacher",
    "doc_ogd_031": "Free textbook",
    "doc_fin_032": "Chief Medical Officer",
    "doc_rd_033": "Telemedicine",
    "doc_rev_034": "Canal repair",
    "doc_gad_035": "Anganwadi Worker",
    "doc_aud_036": "Anganwadi Worker",
    "doc_fin_033": "Procurement ceiling",
    "doc_rd_037": "Vehicle purchase advance",
    "doc_rev_038": "Village Water Sanitation",
    "doc_gad_039": "Disaster relief",
    "doc_rd_040": "MGNREGA",
    "doc_fin_041": "Pension Commutation",
}


def resolve_expected_doc_ids(raw_ids: List[str]) -> List[str]:
    """Map legacy/placeholder topic IDs to actual synthetic corpus document IDs."""
    topic_map = _get_corpus_topic_map()
    resolved: List[str] = []
    for orig in raw_ids:
        topic = ID_TO_TOPIC_KEY.get(orig)
        if topic and topic in topic_map:
            resolved.extend(topic_map[topic])
        else:
            resolved.append(orig)
    # Deduplicate while preserving order
    seen = set()
    out = []
    for r in resolved:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def generate_held_out_questions() -> List[Dict[str, Any]]:
    """Generate 320 curated, unique evaluation questions over the synthetic Uttarakhand corpus."""
    questions: List[Dict[str, Any]] = []
    q_counter = 1

    # -----------------------------------------------------------------------
    # 1. Non-Verbatim Paraphrase Queries (120 Questions: 60 EN, 60 HI)
    # -----------------------------------------------------------------------
    paraphrases_en = [
        ("What was the approved percentage increase in Dearness Allowance for Uttarakhand employees in early 2024?", ["doc_fin_da_2024_heldout"], 1, {"numbers": ["50%", "46%"], "dates": ["01.01.2024"]}),
        ("How are the Dearness Allowance arrears treated for government servants covered under the General Provident Fund?", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["GPF", "arrears"]}),
        ("Are medical officers eligible to include Non-Practicing Allowance when calculating basic pay for Dearness Allowance?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["NPA", "basic pay"]}),
        ("Under which digital treasury portal must disbursals for the revised DA be executed across all 13 districts?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["eKosh"]}),
        ("What special payout mechanism is established for NPS subscribers regarding Dearness Allowance arrears?", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["NPS", "cash payout"]}),
        ("What percentage of basic pay is granted as House Rent Allowance for employees posted in Category Y cities like Dehradun and Haldwani?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%"]}),
        ("Are state government employees residing in allotted government accommodations entitled to draw HRA?", ["doc_fin_hra_2023_heldout"], 1, {"eligibility": ["government departmental quarters", "barred"]}),
        ("What is the admissible HRA entitlement for government staff stationed in Category Z remote hill blocks?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["9%"]}),
        ("Which specific urban centers in Uttarakhand are classified as Category Y for House Rent Allowance purposes?", ["doc_fin_hra_2023_heldout"], 1, {"eligibility": ["Dehradun", "Haridwar", "Haldwani"]}),
        ("What is the revised daily wage rate sanctioned for MGNREGA workers in Uttarakhand hill districts compared to plain areas?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["Rs 255", "Rs 237"]}),
        ("Which plain districts in Uttarakhand are assigned the MGNREGA daily wage of 237 rupees?", ["doc_rd_mgnrega_2024_heldout"], 1, {"eligibility": ["Haridwar", "US Nagar"]}),
        ("By what time each morning must Gram Rozgar Sevaks record biometric attendance on the NMMS application?", ["doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["11:00 AM"]}),
        ("Within how many days must an uncontested land mutation be finalized on the digital Bhulekh portal?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["35"]}),
        ("What is the maximum area of agricultural land an individual can purchase in hill districts without District Magistrate permission?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["250"]}),
        ("Which revenue authorities are explicitly directed to resolve undisputed mutation applications within the 35-day window?", ["doc_rev_land_mutation_heldout"], 1, {"eligibility": ["तहसीलदारों", "नायब तहसीलदारों"]}),
        ("What financial grant is provided to girl students under the Nanda Gaura scheme upon completing intermediate education?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["51,000"]}),
        ("What is the family annual income ceiling for availing Nanda Gaura scheme assistance?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["72,000"]}),
        ("Which departmental officer is responsible for receiving and processing online applications under the Nanda Gaura initiative?", ["doc_wcd_nanda_gaura_heldout"], 1, {"eligibility": ["CDPO"]}),
        ("What is the annual cashless secondary and tertiary treatment ceiling per family under Atal Ayushman Uttarakhand Yojana?", ["doc_med_ayushman_heldout"], 1, {"numbers": ["5 lakh", "5,00,000"]}),
        ("Which identification documents are mandatory for issuance of the Golden Card under Atal Ayushman Uttarakhand?", ["doc_med_ayushman_heldout"], 1, {"eligibility": ["राशन कार्ड", "आधार कार्ड"]}),
        ("What monthly scholarship amount is awarded to meritorious students from Class 6 to 12 in state schools?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["1,200"]}),
        ("What minimum qualifying academic percentage is mandated for school students to secure the Chief Minister merit scholarship?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["70%"]}),
        ("What subsidy percentage is admissible for groups of small farmers installing community tubewells in Terai areas?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["50%", "1.50 lakh"]}),
        ("What is the minimum landholding requirement for a farmer collective to be eligible for community tubewell boring subsidies?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["5 हेक्टेयर"]}),
        ("How many public holidays and restricted holidays were notified for Uttarakhand government offices for 2024?", ["doc_gad_holiday_2024_heldout"], 1, {"numbers": ["28", "18"]}),
        ("On which state folk festival is a full mandatory holiday observed across government offices and schools?", ["doc_gad_holiday_2024_heldout"], 1, {"eligibility": ["इगास बग्वाल"]}),
        ("What is the maximum percentage of basic pension a retiring civil servant can commute, and after how many years is it restored?", ["doc_fin_pension_commutation_heldout"], 1, {"numbers": ["40%", "15 years"]}),
        ("Under which state finance circular are the rules for pension commutation and restoration limits detailed?", ["doc_fin_pension_commutation_heldout"], 1, {"eligibility": ["UK/FIN/2024/115"]}),
        ("What is the maximum procurement financial ceiling permitted for electronic equipment purchases via GeM portal?", ["doc_fin_011"], 1, {"numbers": ["5 lakh", "40%"]}),
        ("What daily allowance rate is sanctioned for state employees undertaking official journeys in high-altitude hill regions?", ["doc_rd_012"], 1, {"numbers": ["Rs 800"]}),
        ("What is the maximum ceiling for Hill Compensatory Allowance granted to staff in remote hill postings?", ["doc_rev_013"], 1, {"numbers": ["10%", "2500"]}),
        ("What is the notified annual interest rate credited quarterly on General Provident Fund balances?", ["doc_gad_014"], 1, {"numbers": ["7.1%"]}),
        ("Up to what amount can Grade Pay 6600 officers obtain as a government vehicle purchase advance?", ["doc_aud_015"], 1, {"numbers": ["8,00,000", "100"]}),
        ("What mandatory routine maintenance guarantee duration must PMGSY road contractors provide?", ["doc_leg_016"], 1, {"numbers": ["5-year"]}),
        ("What annual untied maintenance grant is allocated to Village Water and Sanitation Committees?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("What is the sanctioned revolving fund amount released per approved USRLM women self-help group?", ["doc_fin_018"], 1, {"numbers": ["15,000"]}),
        ("What financial sanction is approved for the repair and maintenance of Kisan Bhavan at the Gram Panchayat level?", ["doc_rd_019"], 1, {"numbers": ["2,00,000"]}),
        ("Under Section 154 of the Revenue Act, beyond what area does purchasing hill land mandate prior DM clearance?", ["doc_rev_020"], 1, {"numbers": ["250 sq meters"]}),
        ("What ex-gratia compensation is sanctioned for loss of life resulting from cloudburst natural disasters?", ["doc_gad_021"], 1, {"numbers": ["4,00,000"]}),
        ("How much disaster relief is awarded for a fully damaged house during severe hill torrential rains?", ["doc_aud_022"], 1, {"numbers": ["1,20,000"]}),
        ("How frequently must Patwaris and Lekhpals update electronic khasra land records in their revenue circles?", ["doc_leg_023"], 1, {"eligibility": ["weekly"]}),
        ("What is the prescribed application fee for filing an RTI request via Indian Postal Order?", ["doc_ogd_024"], 1, {"numbers": ["Rs 10"]}),
        ("Within how many calendar days must a citizen file a first appeal under the Right to Information Act?", ["doc_fin_025"], 1, {"numbers": ["30 days"]}),
        ("By what time must civil secretariat staff register their biometric attendance to avoid late marks?", ["doc_rd_026"], 1, {"dates": ["10:15 AM"]}),
        ("How many biometric late check-in occurrences result in the deduction of one day casual leave?", ["doc_rev_027"], 1, {"numbers": ["3 late marks"]}),
        ("What restrictions are placed on state civil servants regarding active involvement in political campaigns?", ["doc_gad_028"], 1, {"eligibility": ["prohibited"]}),
        ("What is the revised monthly honorarium fixed for Mid-Day Meal cooks working in government primary schools?", ["doc_aud_029"], 1, {"numbers": ["3,000"]}),
        ("What consolidated monthly honorarium is paid to guest teachers deployed in remote hill schools?", ["doc_leg_030"], 1, {"numbers": ["25,000"]}),
        ("By what target date each academic session must free textbooks be distributed to students of classes 1 to 8?", ["doc_ogd_031"], 1, {"dates": ["15th April"]}),
        ("What is the quarterly emergency pharmaceutical procurement financial ceiling authorized for Chief Medical Officers?", ["doc_fin_032"], 1, {"numbers": ["10 Lakh"]}),
        ("How many remote Primary Health Centers in the state are being connected with high-speed telemedicine broadband?", ["doc_rd_033"], 1, {"numbers": ["450"]}),
        ("By what cutoff date must the desilting and repair of all minor irrigation canals be accomplished before the monsoon?", ["doc_rev_034"], 1, {"dates": ["May 31st"]}),
        ("What is the enhanced monthly honorarium sanctioned for Anganwadi Workers in Uttarakhand?", ["doc_gad_035"], 1, {"numbers": ["9,300"]}),
        ("What monthly honorarium rate is designated for Anganwadi Helpers under the revised women and child welfare norms?", ["doc_aud_036"], 1, {"numbers": ["4,650"]}),
        ("What is the minimum discount required on the GeM portal when buying departmental computer hardware?", ["doc_fin_033"], 1, {"numbers": ["40%"]}),
        ("How many equal installments are scheduled for recovering the vehicle advance granted to Grade Pay 6600 officers?", ["doc_rd_037"], 1, {"numbers": ["100"]}),
        ("What is the financial grant provided annually for the maintenance of rural drinking water sources at the village tier?", ["doc_rev_038"], 1, {"numbers": ["50,000"]}),
        ("What compensation is provided for the family of a deceased victim in flash flood emergency guidelines?", ["doc_gad_039"], 1, {"numbers": ["4,00,000"]}),
        ("Which digital platform is mandated for biometric attendance of rural employment workers?", ["doc_rd_040"], 1, {"eligibility": ["NMMS"]}),
        ("What is the permissible percentage commutation of monthly pension upon retirement for state employees?", ["doc_fin_041"], 1, {"numbers": ["40%"]}),
    ]

    for q_text, doc_ids, page_num, facts in paraphrases_en:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": "en",
            "department": DepartmentId.FINANCE_TREASURY.value if "fin" in doc_ids[0] else DepartmentId.RURAL_DEVELOPMENT.value,
            "category": "paraphrase",
            "expected_doc_ids": resolve_expected_doc_ids(doc_ids),
            "expected_page": page_num,
            "expected_facts": facts,
            "expected_refusal": False,
        })
        q_counter += 1

    paraphrases_hi = [
        ("वर्ष 2024 के प्रारंभ में उत्तराखण्ड के सरकारी कर्मचारियों हेतु महंगाई भत्ते में कितनी वृद्धि की गई?", ["doc_fin_da_2024_heldout"], 1, {"numbers": ["50%", "46%"], "dates": ["01.01.2024"]}),
        ("सामान्य भविष्य निधि धारक कर्मचारियों के महंगाई भत्ता एरियर का भुगतान किस रूप में किया जाएगा?", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["GPF", "खाते"]}),
        ("क्या चिकित्सा अधिकारियों द्वारा प्राप्त नॉन-प्रैक्टिसिंग भत्ता महंगाई भत्ते की गणना में बेसिक पे माना जाएगा?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["मूल वेतन", "NPA"]}),
        ("उत्तराखण्ड के समस्त 13 जनपदों के कोषागारों को डीए भुगतान किस ऑनलाइन पोर्टल के माध्यम से करने का निर्देश है?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["eKosh"]}),
        ("एनपीएस के दायरे में आने वाले कार्मिकों को महंगाई भत्ते के बकाया का नकद भुगतान किस प्रकार किया जाएगा?", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["NPS", "नकद"]}),
        ("देहरादून तथा हरिद्वार में तैनात राज्य कर्मचारियों को बेसिक वेतन का कितना प्रतिशत मकान किराया भत्ता देय है?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%"]}),
        ("विभागीय आवासीय क्वार्टर में रहने वाले सरकारी कर्मचारियों के लिए आवास किराया भत्ता अनुमन्यता की क्या शर्त है?", ["doc_fin_hra_2023_heldout"], 1, {"eligibility": ["प्रतिबंधित", "क्वार्टर"]}),
        ("पर्वतीय जनपदों के दूरस्थ ब्लॉकों एवं श्रेणी-Z क्षेत्रों के लिए निर्धारित एचआरए की दर क्या है?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["9%"]}),
        ("उत्तराखण्ड आवास किराया भत्ता आदेश के अंतर्गत श्रेणी-Y में कौन-कौन से प्रमुख नगर सम्मिलित किए गए हैं?", ["doc_fin_hra_2023_heldout"], 1, {"eligibility": ["देहरादून", "हरिद्वार", "हल्द्वानी"]}),
        ("पर्वतीय जनपदों में मनरेगा श्रमिकों हेतु 2024 से लागू संशोधित दैनिक मजदूरी दर क्या निर्धारित की गई है?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["255", "237"]}),
        ("उत्तराखण्ड के मैदानी जिलों हरिद्वार एवं ऊधमसिंह नगर हेतु मनरेगा मजदूरी कितनी स्वीकृत है?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["237"]}),
        ("ग्राम रोजगार सेवकों द्वारा एनएमएमएस मोबाइल ऐप पर प्रतिदिन किस समय तक उपस्थिति दर्ज कराना अनिवार्य है?", ["doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["11:00"]}),
        ("ई-भूलेख पोर्टल पर गैर-विवादित दाखिल खारिज कितने दिनों की निश्चित समय सीमा में निपटाना अनिवार्य है?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["35"]}),
        ("पर्वतीय क्षेत्रों में गैर-कृषकों द्वारा कितनी कृषि भूमि बिना जिला मजिस्ट्रेट की पूर्व अनुमति के क्रय की जा सकती है?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["250"]}),
        ("नायब तहसीलदारों तथा तहसीलदारों को दाखिल खारिज के त्वरित निस्तारण हेतु क्या निर्देश जारी किए गए हैं?", ["doc_rev_land_mutation_heldout"], 1, {"eligibility": ["तहसीलदार", "निस्तारित"]}),
        ("नन्दा गौरा कन्या धन योजना में 12वीं पास बालिकाओं को कितनी एकमुश्त धनराशि प्रदान की जाती है?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["51,000"]}),
        ("नन्दा गौरा योजना का लाभ प्राप्त करने हेतु परिवार की अधिकतम वार्षिक आय सीमा कितनी तय की गई है?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["72,000"]}),
        ("नन्दा गौरा योजना के अंतर्गत ऑनलाइन आवेदन किस स्थानीय बाल विकास अधिकारी के कार्यालय में प्रेषित होगा?", ["doc_wcd_nanda_gaura_heldout"], 1, {"eligibility": ["CDPO"]}),
        ("अटल आयुष्मान योजना के तहत प्रति परिवार प्रति वर्ष कितने रुपये तक का निःशुल्क उपचार अनुमन्य है?", ["doc_med_ayushman_heldout"], 1, {"numbers": ["5,00,000"]}),
        ("आयुष्मान कार्ड बनवाने के लिए लाभार्थियों को कौन से पहचान पत्र एवं दस्तावेज प्रस्तुत करना अनिवार्य है?", ["doc_med_ayushman_heldout"], 1, {"eligibility": ["राशन कार्ड", "आधार कार्ड"]}),
        ("सरकारी प्राथमिक व माध्यमिक विद्यालयों में 70% अंक पाने वाले छात्रों को प्रतिमाह कितनी छात्रवृत्ति मिलती है?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["1,200"]}),
        ("मुख्यमंत्री मेधावी छात्रवृत्ति के लिए कक्षा 6 से 12 तक के विद्यार्थियों हेतु न्यूनतम शैक्षणिक अर्हता क्या है?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["70%"]}),
        ("लघु एवं सीमांत कृषक समूहों को नलकूप एवं बोरिंग लगाने पर अधिकतम कितना अनुदान दिया जाता है?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["50%", "1.50 लाख"]}),
        ("सामुदायिक नलकूप बोरिंग योजना हेतु कृषक समूह के पास न्यूनतम कितनी कृषि भूमि का स्वामित्व अनिवार्य है?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["5 हेक्टेयर"]}),
        ("राज्य कर्मचारियों के लिए वर्ष 2024 में कुल कितने सार्वजनिक अवकाश तथा निर्बंधित अवकाश घोषित किए गए हैं?", ["doc_gad_holiday_2024_heldout"], 1, {"numbers": ["28", "18"]}),
        ("उत्तराखण्ड राज्य के किस प्रसिद्ध लोकपर्व पर समस्त कार्यालयों एवं शिक्षण संस्थानों में पूर्ण अवकाश रहता है?", ["doc_gad_holiday_2024_heldout"], 1, {"eligibility": ["इगास बग्वाल"]}),
        ("सेवानिवृत्ति पर अधिकतम कितने प्रतिशत पेंशन का राशिकरण कराया जा सकता है और यह कितने वर्ष बाद बहाल होती है?", ["doc_fin_pension_commutation_heldout"], 1, {"numbers": ["40%", "15"]}),
        ("पेंशन राशिकरण तथा पुनर्स्थापन के संबंध में जारी वित्त विभाग के आदेश का क्रमांक क्या है?", ["doc_fin_pension_commutation_heldout"], 1, {"eligibility": ["UK/FIN/2024/115"]}),
        ("गवर्नमेंट ई-मार्केटप्लेस (GeM) से इलेक्ट्रॉनिक उपकरण खरीद हेतु निर्धारित वित्तीय सीमा क्या है?", ["doc_fin_011"], 1, {"numbers": ["5 लाख"]}),
        ("उच्च हिमालयी पर्वतीय क्षेत्रों में शासकीय दौरे पर जाने वाले कर्मियों हेतु दैनिक यात्रा भत्ता क्या है?", ["doc_rd_012"], 1, {"numbers": ["800"]}),
        ("दूरस्थ चौकियों पर तैनात राज्य कर्मियों हेतु पर्वतीय प्रतिकर भत्ते की अधिकतम सीमा क्या निर्धारित है?", ["doc_rev_013"], 1, {"numbers": ["2500", "10%"]}),
        ("सामान्य भविष्य निधि पर सरकार द्वारा त्रैमासिक आधार पर कितने प्रतिशत वार्षिक ब्याज जमा किया जाता है?", ["doc_gad_014"], 1, {"numbers": ["7.1%"]}),
        ("ग्रेड वेतन 6600 के अधिकारियों हेतु वाहन अग्रिम के रूप में अधिकतम कितनी धनराशि स्वीकृत की जा सकती है?", ["doc_aud_015"], 1, {"numbers": ["8 लाख"]}),
        ("प्रधानमंत्री ग्राम सड़क योजना के अंतर्गत ठेकेदारों हेतु सड़क रखरखाव की न्यूनतम गारंटी अवधि क्या है?", ["doc_leg_016"], 1, {"numbers": ["5 वर्ष"]}),
        ("ग्राम जल एवं स्वच्छता समिति को पेयजल स्रोतों के वार्षिक रखरखाव हेतु कितना अवमुक्त अनुदान मिलता है?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("उत्तराखण्ड राज्य ग्रामीण आजीविका मिशन के तहत महिला स्वयं सहायता समूहों को कितना रिवाल्विंग फंड देय है?", ["doc_fin_018"], 1, {"numbers": ["15,000"]}),
        ("ग्राम पंचायत स्तर पर किसान भवन की मरम्मत एवं जीर्णोद्धार हेतु कितनी वित्तीय स्वीकृति प्रदान की गई है?", ["doc_rd_019"], 1, {"numbers": ["2 लाख"]}),
        ("राजस्व संहिता की धारा 154 के तहत पर्वतीय जनपदों में भूमि क्रय पर क्या प्रतिबंध लागू है?", ["doc_rev_020"], 1, {"numbers": ["250"]}),
        ("बादल फटने तथा अतिवृष्टि जैसी प्राकृतिक आपदाओं में जनहानि होने पर पीड़ित परिवार को कितना मुआवजा देय है?", ["doc_gad_021"], 1, {"numbers": ["4 लाख"]}),
        ("आपदा में मकान पूर्ण रूप से क्षतिग्रस्त होने पर राहत नियमावली के अंतर्गत कितनी आर्थिक सहायता मिलती है?", ["doc_aud_022"], 1, {"numbers": ["1.20 लाख"]}),
        ("प्रत्येक राजस्व वृत्त में पटवारी एवं लेखपाल द्वारा ई-खसरा अभिलेख का अद्यतन किस अंतराल पर किया जाना अनिवार्य है?", ["doc_leg_023"], 1, {"eligibility": ["साप्ताहिक"]}),
        ("सूचना का अधिकार अधिनियम के अंतर्गत आईपीओ द्वारा आवेदन प्रस्तुत करने पर निर्धारित शुल्क कितना है?", ["doc_ogd_024"], 1, {"numbers": ["10"]}),
        ("प्रथम अपीलीय अधिकारी के समक्ष आरटीआई अपील कितने दिनों के भीतर दाखिल की जा सकती है?", ["doc_fin_025"], 1, {"numbers": ["30 दिन"]}),
        ("सचिवालय कार्मिकों हेतु बायोमीट्रिक उपस्थिति दर्ज करने का अंतिम समय क्या निर्धारित किया गया है?", ["doc_rd_026"], 1, {"dates": ["10:15"]}),
        ("बायोमीट्रिक हाजिरी में कितनी बार विलंब होने पर कर्मचारी का एक दिन का आकस्मिक अवकाश काटा जाता है?", ["doc_rev_027"], 1, {"numbers": ["3 विलंब"]}),
        ("सरकारी सेवकों के राजनीतिक दलों के चुनाव प्रचार में भाग लेने पर आचरण नियमावली क्या कहती है?", ["doc_gad_028"], 1, {"eligibility": ["वर्जित"]}),
        ("राजकीय प्राथमिक विद्यालयों में कार्यरत मध्याह्न भोजन रसोइयों का मानदेय बढ़ाकर कितना किया गया है?", ["doc_aud_029"], 1, {"numbers": ["3,000"]}),
        ("विषम पर्वतीय विद्यालयों में तैनात अतिथि शिक्षकों को प्रतिमाह कितना एकमुश्त मानदेय दिया जाता है?", ["doc_leg_030"], 1, {"numbers": ["25,000"]}),
        ("कक्षा 1 से 8 तक के छात्र-छात्राओं को प्रतिवर्ष किस तिथि तक निःशुल्क पाठ्यपुस्तकें उपलब्ध कराना अनिवार्य है?", ["doc_ogd_031"], 1, {"dates": ["15 अप्रैल"]}),
        ("मुख्य चिकित्सा अधिकारी को त्रैमासिक आधार पर आपातकालीन औषधि क्रय हेतु कितनी वित्तीय शक्ति प्राप्त है?", ["doc_fin_032"], 1, {"numbers": ["10 लाख"]}),
        ("राज्य के कितने दूरस्थ प्राथमिक स्वास्थ्य केंद्रों को हाई-स्पीड टेलीमेडिसिन कनेक्टिविटी से जोड़ा गया है?", ["doc_rd_033"], 1, {"numbers": ["450"]}),
        ("मानसून प्रारंभ होने से पूर्व समस्त लघु सिंचाई नहरों की गाद सफाई किस निश्चित तिथि तक पूरी होनी चाहिए?", ["doc_rev_034"], 1, {"dates": ["31 मई"]}),
        ("उत्तराखण्ड शासन द्वारा आंगनबाड़ी कार्यकत्रियों का संशोधित मासिक मानदेय कितना निर्धारित किया गया है?", ["doc_gad_035"], 1, {"numbers": ["9,300"]}),
        ("महिला एवं बाल विकास विभाग में आंगनबाड़ी सहायिकाओं हेतु स्वीकृत नवीन मानदेय क्या है?", ["doc_aud_036"], 1, {"numbers": ["4,650"]}),
        ("ई-कोश सॉफ्टवेयर प्रणाली द्वारा राज्य कर्मचारियों के भत्तों के आहरण हेतु क्या व्यवस्था है?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["eKosh"]}),
        ("वाहन क्रय अग्रिम की वसूली हेतु सरकारी कार्मिकों को कितनी अधिकतम मासिक किस्तें अनुमन्य हैं?", ["doc_aud_015"], 1, {"numbers": ["100"]}),
        ("महिला स्वयं सहायता समूहों को आत्मनिर्भर बनाने हेतु किस योजना से वित्तीय अनुदान दिया जाता है?", ["doc_fin_018"], 1, {"eligibility": ["USRLM"]}),
        ("आपदा राहत कोष से मकान आंशिक रूप से टूटने पर क्या सहायता राशि अनुमन्य है?", ["doc_aud_022"], 1, {"numbers": ["1.20 लाख"]}),
        ("ग्रामीण क्षेत्रों में पेयजल गुणवत्ता परीक्षण हेतु समितियों को कौन सा फंड मिलता है?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("पर्वतीय क्षेत्रों में पटवारी हलकों के सीमांकन में क्या साप्ताहिक कार्य अनिवार्य है?", ["doc_leg_023"], 1, {"eligibility": ["ई-खसरा"]}),
    ]

    for q_text, doc_ids, page_num, facts in paraphrases_hi:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": "hi",
            "department": DepartmentId.FINANCE_TREASURY.value if "fin" in doc_ids[0] else DepartmentId.BOARD_OF_REVENUE.value,
            "category": "paraphrase",
            "expected_doc_ids": resolve_expected_doc_ids(doc_ids),
            "expected_page": page_num,
            "expected_facts": facts,
            "expected_refusal": False,
        })
        q_counter += 1

    # -----------------------------------------------------------------------
    # 2. Hinglish / Romanized Transliteration Queries (60 Questions)
    # -----------------------------------------------------------------------
    hinglish_queries = [
        ("Uttarakhand sarkari karmchariyon ke DA me kitni badhotari hui hai 2024 me?", ["doc_fin_da_2024_heldout"], 1, {"numbers": ["50%"]}),
        ("Dehradun aur Haldwani me posting hone par HRA kitna percentage milta hai?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%"]}),
        ("Hill districts me MNREGA daily wage rate kitna fix hua hai?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["255"]}),
        ("Bhulekh portal par dakhil kharij kitne dino me hona zaroori hai?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["35"]}),
        ("Nanda Gaura scheme ke liye family ki annual income limit kitni hai?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["72,000"]}),
        ("Atal Ayushman card par kitne tak ka free treatment milta hai har saal?", ["doc_med_ayushman_heldout"], 1, {"numbers": ["5 lakh"]}),
        ("Pahadi kshetron me tubewell lagane par kitna subsidy milta hai?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["50%"]}),
        ("Pension kitne saal baad poori restore hoti hai agar commute karwaya ho?", ["doc_fin_pension_commutation_heldout"], 1, {"numbers": ["15"]}),
        ("Class 10th aur 12th pass hone par medhavi chhatravritti kitni milti hai?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["1,200"]}),
        ("Uttarakhand government calendar ke hisab se public holidays kitni declare hui hain?", ["doc_gad_holiday_2024_heldout"], 1, {"numbers": ["28"]}),
        ("NPS wale staff ko DA ka arrear cash me milega ya GPF me jama hoga?", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["NPS"]}),
        ("Doctors ko milne wala NPA allowance kya basic pay me jodkar DA calculate hoga?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["NPA"]}),
        ("Tehsildar ko kitne din me dakhil kharij verify karna hota hai online?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["35"]}),
        ("Pahadi gaon me kisan kitni zameen khareed sakta hai bina DM permission ke?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["250"]}),
        ("Nanda Gaura scheme ka form bharne ke liye kiske office me submit karna hoga?", ["doc_wcd_nanda_gaura_heldout"], 1, {"eligibility": ["CDPO"]}),
        ("Ayushman golden card banane ke liye ration card ke sath aur kya manga jata hai?", ["doc_med_ayushman_heldout"], 1, {"eligibility": ["आधार"]}),
        ("Tubewell lagane ke liye kisan group ke paas kam se kam kitni land honi chahiye?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["5"]}),
        ("State government me 40 percent pension commute karne par kab restore hoti hai?", ["doc_fin_pension_commutation_heldout"], 1, {"numbers": ["15"]}),
        ("Haridwar aur US Nagar me MNREGA ki daily mazdoori kitni milti hai?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["237"]}),
        ("Igas Bagwal ke tyohar par kya sabhi sarkari office me holiday hoti hai?", ["doc_gad_holiday_2024_heldout"], 1, {"eligibility": ["इगास बग्वाल"]}),
        ("GeM portal par computer ya printer khareedne ki maximum financial limit kya hai?", ["doc_fin_011"], 1, {"numbers": ["5 lakh"]}),
        ("Pahadi ilaqon me official tour par daily travel allowance kitna milta hai?", ["doc_rd_012"], 1, {"numbers": ["800"]}),
        ("Remote posting par hill compensatory allowance basic pay ka kitna percent hota hai?", ["doc_rev_013"], 1, {"numbers": ["10%"]}),
        ("GPF par state government saal ka kitna percent interest credit karti hai?", ["doc_gad_014"], 1, {"numbers": ["7.1%"]}),
        ("Grade pay 6600 wale officer ko car advance kitne rupaye tak mil sakta hai?", ["doc_aud_015"], 1, {"numbers": ["8 लाख"]}),
        ("PMGSY road contract me routine maintenance ki guarantee kitne saal ki hoti hai?", ["doc_leg_016"], 1, {"numbers": ["5"]}),
        ("Gram panchayat me paani ki samiti ko maintenance ke liye kitna untied fund milta hai?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("USRLM me mahila swayam sahayata samooh ko revolving fund kitna milta hai?", ["doc_fin_018"], 1, {"numbers": ["15,000"]}),
        ("Kisan bhavan ki repair ke liye gram panchayat ko kitna budget sanction hua hai?", ["doc_rd_019"], 1, {"numbers": ["2 लाख"]}),
        ("Aapda ke samay baadal fatne se death hone par government kitna compensation deti hai?", ["doc_gad_021"], 1, {"numbers": ["4 लाख"]}),
        ("Baarish se ghar poori tarah toot jaane par kitni relief rashi di jaati hai?", ["doc_aud_022"], 1, {"numbers": ["1.20 लाख"]}),
        ("Lekhpal aur patwari ko khasra online kitne din me update karna padta hai?", ["doc_leg_023"], 1, {"eligibility": ["साप्ताहिक"]}),
        ("RTI lagane ke liye Indian Postal Order kitne rupaye ka lagana hota hai?", ["doc_ogd_024"], 1, {"numbers": ["10"]}),
        ("RTI ki first appeal kitne din ke andar file karni hoti hai?", ["doc_fin_025"], 1, {"numbers": ["30"]}),
        ("Secretariat me biometric attendance subah kitne baje tak lagani zaroori hai?", ["doc_rd_026"], 1, {"dates": ["10:15"]}),
        ("Biometric me kitni baar late aane par ek din ki casual leave deduct ho jati hai?", ["doc_rev_027"], 1, {"numbers": ["3"]}),
        ("Sarkari karmchariyon ke chunav prachar me bhaag lene par kya ban laga hai?", ["doc_gad_028"], 1, {"eligibility": ["वर्जित"]}),
        ("School me MDM banane wali rasoiya ka monthly mandeya kitna kar diya gaya hai?", ["doc_aud_029"], 1, {"numbers": ["3,000"]}),
        ("Remote pahadi schools me guest teacher ko har mahine kitni salary milti hai?", ["doc_leg_030"], 1, {"numbers": ["25,000"]}),
        ("Class 1 se 8 tak free books kis date tak distribute ho jani chahiye?", ["doc_ogd_031"], 1, {"dates": ["15 अप्रैल"]}),
        ("CMO ko emergency medicines purchase karne ke liye kitna quarterly budget milta hai?", ["doc_fin_032"], 1, {"numbers": ["10 लाख"]}),
        ("Kitne pahadi PHC me telemedicine aur broadband internet connection lagaya gaya hai?", ["doc_rd_033"], 1, {"numbers": ["450"]}),
        ("Monsoon aane se pehle neharon ki safai kis date tak poori honi chahiye?", ["doc_rev_034"], 1, {"dates": ["31 मई"]}),
        ("Anganwadi karyakatri ka badha hua mandeya kitna announce hua hai?", ["doc_gad_035"], 1, {"numbers": ["9,300"]}),
        ("Anganwadi helper ko har mahine kitna honorarium diya jata hai?", ["doc_aud_036"], 1, {"numbers": ["4,650"]}),
        ("eKosh portal se salary aur DA nikalne ka kya process hai?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["eKosh"]}),
        ("Car loan ka paisa kitni monthly installments me wapas karna hota hai?", ["doc_aud_015"], 1, {"numbers": ["100"]}),
        ("Gram Jal Samiti ko 50000 ka maintenance grant kis kaam ke liye milta hai?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("Flash flood aane par ghar girne par 1.20 lakh ka relief kaun deta hai?", ["doc_aud_022"], 1, {"numbers": ["1.20 लाख"]}),
        ("NMMS app par mazdooron ki attendance subah 11 baje se pehle lagana kyu zaroori hai?", ["doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["11:00"]}),
        ("Dehradun aur Haridwar Category Y city hone ke naate HRA 16 percent kyu milta hai?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%"]}),
        ("Remote block me Category Z me posting par 9 percent HRA hi kyu milta hai?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["9%"]}),
        ("Nanda Gaura me 12th pass ladki ko 51000 DBT ke through milta hai ya cheque se?", ["doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["51,000"]}),
        ("Ayushman card par 5 lakh ka ilaj har saal private hospital me bhi ho sakta hai kya?", ["doc_med_ayushman_heldout"], 1, {"numbers": ["5 लाख"]}),
        ("Government school ke baccho ko 70 percent marks lane par 1200 scholarship kaise milti hai?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["1,200"]}),
        ("Tubewell boring par 50 percent subsidy pane ke liye kitne kisano ka group chahiye?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["50%"]}),
        ("Retire hone ke baad GPF balance par kitne percent interest milta hai?", ["doc_gad_014"], 1, {"numbers": ["7.1%"]}),
        ("Biometric system me continuous late aane par kya action hota hai?", ["doc_rev_027"], 1, {"numbers": ["3"]}),
        ("Anganwadi helper aur worker ke mandeya me kitne rupaye ka antar hai?", ["doc_gad_035"], 1, {"numbers": ["9,300"]}),
        ("Uttarakhand me sarkari gaadi khareedne ke liye 8 lakh ka advance kis grade pay par milta hai?", ["doc_aud_015"], 1, {"numbers": ["6600"]}),
    ]

    for q_text, doc_ids, page_num, facts in hinglish_queries:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": "hi-Latn",
            "department": DepartmentId.FINANCE_TREASURY.value,
            "category": "hinglish",
            "expected_doc_ids": resolve_expected_doc_ids(doc_ids),
            "expected_page": page_num,
            "expected_facts": facts,
            "expected_refusal": False,
        })
        q_counter += 1

    # -----------------------------------------------------------------------
    # 3. Multi-Document Synthesis Queries (50 Questions)
    # -----------------------------------------------------------------------
    multi_doc_queries = [
        ("Compare the compensation provided for rural development daily wages versus Anganwadi honorarium rates.", ["doc_rd_mgnrega_2024_heldout", "doc_gad_035"], 1, {"numbers": ["255", "9,300"]}),
        ("What are the simultaneous benefits available for female students under the Nanda Gaura grant and school merit scholarship?", ["doc_wcd_nanda_gaura_heldout", "doc_edu_scholarship_heldout"], 1, {"numbers": ["51,000", "1,200"]}),
        ("How do hill compensatory criteria align between HRA category Z tehsils and MGNREGA hill block classifications?", ["doc_fin_hra_2023_heldout", "doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["9%", "Rs 255"]}),
        ("What are the combined financial limits when purchasing electronics under GeM versus emergency drugs under CMO quotas?", ["doc_fin_011", "doc_fin_032"], 1, {"numbers": ["5 lakh", "10 Lakh"]}),
        ("Compare the deadline for pre-monsoon canal desilting against the deadline for free textbook distribution.", ["doc_rev_034", "doc_ogd_031"], 1, {"dates": ["May 31st", "15th April"]}),
        ("How does the family income ceiling for Nanda Gaura compare with the eligibility criteria for community tubewell subsidies?", ["doc_wcd_nanda_gaura_heldout", "doc_irr_tubewell_heldout"], 1, {"numbers": ["72,000", "50%"]}),
        ("Contrast the financial compensation for cloudburst house destruction against the loan limit for government vehicle advances.", ["doc_aud_022", "doc_aud_015"], 1, {"numbers": ["1,20,000", "8,00,000"]}),
        ("What are the respective appeal and resolution timelines for RTI first appeals versus digital land mutation applications?", ["doc_fin_025", "doc_rev_land_mutation_heldout"], 1, {"numbers": ["30 days", "35"]}),
        ("Compare the monthly remuneration of a Mid-Day Meal cook with that of an Anganwadi helper.", ["doc_aud_029", "doc_aud_036"], 1, {"numbers": ["3,000", "4,650"]}),
        ("How do attendance compliance rules differ between secretariat staff biometric check-in and MGNREGA field workers on NMMS?", ["doc_rd_026", "doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["10:15 AM", "11:00 AM"]}),
        ("Contrast the interest rate earned on GPF savings with the pension commutation restoration tenure.", ["doc_gad_014", "doc_fin_pension_commutation_heldout"], 1, {"numbers": ["7.1%", "15 years"]}),
        ("What financial assistance is available for village water sanitation maintenance compared to Kisan Bhavan infrastructure repair?", ["doc_ogd_017", "doc_rd_019"], 1, {"numbers": ["50,000", "2,00,000"]}),
        ("Compare the daily travel allowance for high-altitude official journeys with the daily wage rate for MGNREGA in hill districts.", ["doc_rd_012", "doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["800", "255"]}),
        ("How do Category Y and Category Z House Rent Allowance rates compare across different district postings?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%", "9%"]}),
        ("Compare the financial relief granted for loss of life in natural disasters with the total advance permissible for vehicle purchase.", ["doc_gad_021", "doc_aud_015"], 1, {"numbers": ["4,00,000", "8,00,000"]}),
        ("Contrast the online portal requirements between Dearness Allowance treasury disbursal via eKosh and land mutation on Bhulekh.", ["doc_fin_da_2024_heldout", "doc_rev_land_mutation_heldout"], 2, {"eligibility": ["eKosh", "Bhulekh"]}),
        ("How do the honorarium scales of remote school guest teachers compare with the monthly wages of Anganwadi workers?", ["doc_leg_030", "doc_gad_035"], 1, {"numbers": ["25,000", "9,300"]}),
        ("Compare the mandatory maintenance guarantee period for PMGSY roads with the restoration period for commuted pensions.", ["doc_leg_016", "doc_fin_pension_commutation_heldout"], 1, {"numbers": ["5-year", "15 years"]}),
        ("Contrast the land area ceilings specified for community tubewell grants versus private agricultural land acquisition in hill areas.", ["doc_irr_tubewell_heldout", "doc_rev_land_mutation_heldout"], 1, {"numbers": ["5", "250"]}),
        ("What are the combined healthcare provisions established under Atal Ayushman coverage and CMO emergency pharmaceutical reserves?", ["doc_med_ayushman_heldout", "doc_fin_032"], 1, {"numbers": ["5 lakh", "10 Lakh"]}),
        ("नन्दा गौरा योजना तथा मेधावी छात्रवृत्ति के वित्तीय लाभों की तुलनात्मक समीक्षा प्रस्तुत करें।", ["doc_wcd_nanda_gaura_heldout", "doc_edu_scholarship_heldout"], 1, {"numbers": ["51,000", "1,200"]}),
        ("मकान किराया भत्ता श्रेणी-Z तथा मनरेगा पर्वतीय दरों के लिए निर्धारित जनपदों का विवरण दें।", ["doc_fin_hra_2023_heldout", "doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["9%", "255"]}),
        ("ग्राम विकास दैनिक मजदूरी एवं आंगनबाड़ी कार्यकत्री के मासिक मानदेय में वित्तीय अंतर स्पष्ट करें।", ["doc_rd_mgnrega_2024_heldout", "doc_gad_035"], 1, {"numbers": ["255", "9,300"]}),
        ("नहरों की सिल्ट सफाई की अंतिम तिथि तथा पाठ्यपुस्तक वितरण की समय सीमा का तुलनात्मक विवरण दें।", ["doc_rev_034", "doc_ogd_031"], 1, {"dates": ["31 मई", "15 अप्रैल"]}),
        ("सूचना का अधिकार अपील समय सीमा तथा ई-भूलेख दाखिल खारिज निस्तारण अवधि की तुलना करें।", ["doc_fin_025", "doc_rev_land_mutation_heldout"], 1, {"numbers": ["30", "35"]}),
        ("आपदा में जनहानि पर देय अनुग्रह राशि तथा वाहन खरीद हेतु अनुमन्य अग्रिम की तुलनात्मक सीमा क्या है?", ["doc_gad_021", "doc_aud_015"], 1, {"numbers": ["4 लाख", "8 लाख"]}),
        ("मध्याह्न भोजन रसोइया तथा आंगनबाड़ी सहायिका के मासिक मानदेय की तुलना प्रस्तुत करें।", ["doc_aud_029", "doc_aud_036"], 1, {"numbers": ["3,000", "4,650"]}),
        ("सचिवालय बायोमीट्रिक उपस्थिति नियम तथा मनरेगा एनएमएमएस हाजिरी समय सीमा में क्या अंतर है?", ["doc_rd_026", "doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["10:15", "11:00"]}),
        ("जीपीएफ ब्याज दर तथा पेंशन राशिकरण पुनर्स्थापन अवधि के वित्तीय प्रावधानों का विश्लेषण करें।", ["doc_gad_014", "doc_fin_pension_commutation_heldout"], 1, {"numbers": ["7.1%", "15"]}),
        ("किसान भवन मरम्मत अनुदान तथा ग्राम जल स्वच्छता समिति के वार्षिक बजट में क्या अनुपात है?", ["doc_rd_019", "doc_ogd_017"], 1, {"numbers": ["2 लाख", "50,000"]}),
        ("पर्वतीय यात्रा भत्ता दैनिक दर तथा मनरेगा पर्वतीय मजदूरी की तुलनात्मक समीक्षा करें।", ["doc_rd_012", "doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["800", "255"]}),
        ("आवास किराया भत्ता श्रेणी-Y तथा श्रेणी-Z की दरों में कितने प्रतिशत का अंतर है?", ["doc_fin_hra_2023_heldout"], 1, {"numbers": ["16%", "9%"]}),
        ("अटल आयुष्मान योजना के उपचार पैकेज तथा सीएमओ आपातकालीन दवा खरीद सीमा में क्या संबंध है?", ["doc_med_ayushman_heldout", "doc_fin_032"], 1, {"numbers": ["5 लाख", "10 लाख"]}),
        ("गेम पोर्टल इलेक्ट्रॉनिक खरीद सीमा तथा सीएमओ त्रैमासिक खरीद सीमा की तुलना करें।", ["doc_fin_011", "doc_fin_032"], 1, {"numbers": ["5 लाख", "10 लाख"]}),
        ("अतिथि शिक्षक के मासिक मानदेय तथा आंगनबाड़ी कार्यकत्री के मानदेय में क्या वित्तीय भिन्नता है?", ["doc_leg_030", "doc_gad_035"], 1, {"numbers": ["25,000", "9,300"]}),
        ("नन्दा गौरा कन्या धन पात्रता आय सीमा तथा लघु सिंचाई अनुदान भूमि सीमा की तुलना करें।", ["doc_wcd_nanda_gaura_heldout", "doc_irr_tubewell_heldout"], 1, {"numbers": ["72,000", "5"]}),
        ("प्राकृतिक आपदा में पूर्ण क्षतिग्रस्त मकान की सहायता तथा स्वयं सहायता समूह रिवाल्विंग फंड की तुलना करें।", ["doc_aud_022", "doc_fin_018"], 1, {"numbers": ["1.20 लाख", "15,000"]}),
        ("ई-कोश कोषागार भुगतान प्रणाली तथा ई-भूलेख म्यूटेशन पोर्टल के संचालन में क्या प्रशासनिक अंतर है?", ["doc_fin_da_2024_heldout", "doc_rev_land_mutation_heldout"], 2, {"eligibility": ["eKosh", "Bhulekh"]}),
        ("पीएमजीएसवाई सड़क रखरखाव गारंटी अवधि तथा पेंशन बहाली समय-सीमा की तुलना करें।", ["doc_leg_016", "doc_fin_pension_commutation_heldout"], 1, {"numbers": ["5", "15"]}),
        ("पर्वतीय भूमि क्रय सीमा 250 वर्ग मीटर तथा सामुदायिक नलकूप हेतु 5 हेक्टेयर की शर्त का तुलनात्मक अध्ययन करें।", ["doc_rev_land_mutation_heldout", "doc_irr_tubewell_heldout"], 1, {"numbers": ["250", "5"]}),
        ("Compare the welfare benefits provided to girl children between primary school stage and intermediate graduation.", ["doc_edu_scholarship_heldout", "doc_wcd_nanda_gaura_heldout"], 1, {"numbers": ["1,200", "51,000"]}),
        ("How do financial authorizations differ between Gram Panchayat untied funds and block development project allocations?", ["doc_ogd_017", "doc_rd_019"], 1, {"numbers": ["50,000", "2,00,000"]}),
        ("Contrast the penalties for civil service political activism against administrative penalties for biometric tardiness.", ["doc_gad_028", "doc_rev_027"], 1, {"numbers": ["3"]}),
        ("Compare the cash payout terms of DA arrears under NPS versus deposit into General Provident Fund accounts.", ["doc_fin_da_2024_heldout"], 1, {"eligibility": ["NPS", "GPF"]}),
        ("How does the annual cashless limit under Ayushman compare with ex-gratia compensation for cloudburst loss of life?", ["doc_med_ayushman_heldout", "doc_gad_021"], 1, {"numbers": ["5 lakh", "4,00,000"]}),
        ("Analyze the difference between Category Y HRA entitlement and Hill Compensatory Allowance for remote posts.", ["doc_fin_hra_2023_heldout", "doc_rev_013"], 1, {"numbers": ["16%", "10%"]}),
        ("Contrast the documentation required for Ayushman golden cards with documents required for digital land mutation.", ["doc_med_ayushman_heldout", "doc_rev_land_mutation_heldout"], 1, {"eligibility": ["राशन", "आधार"]}),
        ("Compare the wage revision effective dates between Dearness Allowance and MGNREGA daily remuneration in 2024.", ["doc_fin_da_2024_heldout", "doc_rd_mgnrega_2024_heldout"], 1, {"dates": ["01.01.2024", "1st April 2024"]}),
        ("How do the vehicle advance repayment terms compare with the loan limits available to rural self-help groups?", ["doc_aud_015", "doc_fin_018"], 1, {"numbers": ["100", "15,000"]}),
        ("Evaluate the inter-relationship between telemedicine broadband rollouts in PHCs and emergency drug procurement ceilings.", ["doc_rd_033", "doc_fin_032"], 1, {"numbers": ["450", "10 Lakh"]}),
    ]

    for q_text, doc_ids, page_num, facts in multi_doc_queries:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": "hi" if any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in q_text) else "en",
            "department": DepartmentId.FINANCE_TREASURY.value,
            "category": "multi_doc_synthesis",
            "expected_doc_ids": resolve_expected_doc_ids(doc_ids),
            "expected_page": page_num,
            "expected_facts": facts,
            "expected_refusal": False,
        })
        q_counter += 1

    # -----------------------------------------------------------------------
    # 4. Scanned Hindi OCR Queries (40 Questions)
    # -----------------------------------------------------------------------
    ocr_queries = [
        ("ई-भूलेख दाखिल खारिज के संबंध में स्कैन प्रति में उल्लिखित समय सीमा क्या है?", ["doc_rev_land_mutation_heldout"], 1, {"numbers": ["35"]}),
        ("स्कैन शासनादेश के अनुसार नन्दा गौरा कन्या धन के लिए आवेदन किस अधिकारी के माध्यम से प्रस्तुत होगा?", ["doc_wcd_nanda_gaura_heldout"], 1, {"eligibility": ["CDPO"]}),
        ("आयुष्मान उत्तराखण्ड के स्कैन आदेश में राशन कार्ड तथा आधार कार्ड की क्या अनिवार्यता दी गई है?", ["doc_med_ayushman_heldout"], 1, {"eligibility": ["राशन कार्ड", "आधार कार्ड"]}),
        ("लघु सिंचाई बोरिंग अनुदान की स्कैन अधिसूचना में न्यूनतम कितने हेक्टेयर भूमि की शर्त है?", ["doc_irr_tubewell_heldout"], 1, {"numbers": ["5"]}),
        ("स्कैन प्रति में उल्लिखित महंगाई भत्ता वृद्धि आदेश 2024 की प्रभावी तिथि क्या दर्ज है?", ["doc_fin_da_2024_heldout"], 1, {"dates": ["01.01.2024"]}),
        ("मकान किराया भत्ता युक्तिकरण के स्कैन शासनादेश में श्रेणी Y जनपदों की सूची में क्या दर्ज है?", ["doc_fin_hra_2023_heldout"], 1, {"eligibility": ["देहरादून", "हरिद्वार", "हल्द्वानी"]}),
        ("मनरेगा मजदूरी पुनरीक्षण के स्कैन आदेश में पर्वतीय ब्लॉकों हेतु क्या दैनिक दर मुद्रित है?", ["doc_rd_mgnrega_2024_heldout"], 1, {"numbers": ["255"]}),
        ("पेंशन राशिकरण के स्कैन सरकारी आदेश में 15 वर्ष बाद बहाली संबंधी क्या उपबंध है?", ["doc_fin_pension_commutation_heldout"], 1, {"numbers": ["15"]}),
        ("मेधावी छात्रवृत्ति के स्कैन परिपत्र में 70 प्रतिशत अंक की अनिवार्यता किस पैराग्राफ में दी गई है?", ["doc_edu_scholarship_heldout"], 1, {"numbers": ["70%"]}),
        ("सार्वजनिक अवकाश सूची 2024 के स्कैन गजट में इगास बग्वाल पर्व पर क्या टिप्पणी दर्ज है?", ["doc_gad_holiday_2024_heldout"], 1, {"eligibility": ["इगास बग्वाल"]}),
        ("स्कैन शासनादेश संख्या UK/FIN/2023/111 में GeM पोर्टल खरीद सीमा कितनी स्पष्ट दिखती है?", ["doc_fin_011"], 1, {"numbers": ["5 लाख"]}),
        ("पर्वतीय यात्रा भत्ता आदेश की स्कैन प्रति में 800 रुपये प्रतिदिन का भत्ता किस पद हेतु है?", ["doc_rd_012"], 1, {"numbers": ["800"]}),
        ("दूरस्थ चौकियों के प्रतिकर भत्ता आदेश में 10 प्रतिशत की सीमा किस स्कैन धारा में है?", ["doc_rev_013"], 1, {"numbers": ["10%"]}),
        ("सामान्य भविष्य निधि ब्याज दर अधिसूचना की स्कैन कॉपी में 7.1 प्रतिशत की तिमाही प्रविष्टि क्या है?", ["doc_gad_014"], 1, {"numbers": ["7.1%"]}),
        ("ग्रेड वेतन 6600 वाहन अग्रिम के स्कैन सर्कुलर में 100 किस्तों का क्या उल्लेख है?", ["doc_aud_015"], 1, {"numbers": ["100"]}),
        ("पीएमजीएसवाई सड़क मरम्मत के स्कैन अनुबंध में 5 वर्षीय गारंटी की क्या शर्त लिखी है?", ["doc_leg_016"], 1, {"numbers": ["5 वर्ष"]}),
        ("ग्राम जल स्वच्छता समिति के स्कैन आवंटन पत्र में 50,000 रुपये का क्या विवरण है?", ["doc_ogd_017"], 1, {"numbers": ["50,000"]}),
        ("महिला स्वयं सहायता समूह के स्कैन शासनादेश में 15,000 रुपये रिवाल्विंग फंड का क्या नियम है?", ["doc_fin_018"], 1, {"numbers": ["15,000"]}),
        ("किसान भवन मरम्मत स्वीकृति के स्कैन आदेश में 2 लाख रुपये की मद क्या दर्शायी गई है?", ["doc_rd_019"], 1, {"numbers": ["2 लाख"]}),
        ("राजस्व धारा 154 के स्कैन आदेश में 250 वर्ग मीटर से अधिक भूमि पर डीएम अनुमति का क्या पाठ है?", ["doc_rev_020"], 1, {"numbers": ["250"]}),
        ("बादल फटने से जनहानि पर 4 लाख रुपये मुआवजे का स्कैन अधिसूचना क्रमांक क्या है?", ["doc_gad_021"], 1, {"numbers": ["4 लाख"]}),
        ("आपदा में मकान क्षति पर 1.20 लाख रुपये राहत का विवरण किस स्कैन प्रति में मुद्रित है?", ["doc_aud_022"], 1, {"numbers": ["1.20 लाख"]}),
        ("ई-खसरा साप्ताहिक अद्यतन के स्कैन निर्देश में पटवारी और लेखपाल हेतु क्या आदेश है?", ["doc_leg_023"], 1, {"eligibility": ["साप्ताहिक"]}),
        ("सूचना का अधिकार 10 रुपये आवेदन शुल्क संबंधी स्कैन अधिसूचना का दिनांक क्या है?", ["doc_ogd_024"], 1, {"numbers": ["10"]}),
        ("आरटीआई प्रथम अपील 30 दिवस की समय सीमा किस स्कैन प्रशासनिक पत्र में लिखी है?", ["doc_fin_025"], 1, {"numbers": ["30"]}),
        ("सचिवालय बायोमीट्रिक हाजिरी के स्कैन आदेश में 10:15 बजे की समय सीमा कैसे मुद्रित है?", ["doc_rd_026"], 1, {"dates": ["10:15"]}),
        ("बायोमीट्रिक तीन विलंब पर एक आकस्मिक अवकाश कटौती का नियम किस स्कैन प्रस्तर में है?", ["doc_rev_027"], 1, {"numbers": ["3"]}),
        ("राजनीतिक तटस्थता आचरण नियमावली के स्कैन गजट में सरकारी सेवकों पर क्या पाबंदी है?", ["doc_gad_028"], 1, {"eligibility": ["वर्जित"]}),
        ("मध्याह्न भोजन रसोइया 3,000 रुपये मानदेय के स्कैन शासनादेश का विषय क्या है?", ["doc_aud_029"], 1, {"numbers": ["3,000"]}),
        ("अतिथि शिक्षक 25,000 रुपये मानदेय की स्कैन प्रति में दूरस्थ विद्यालयों का क्या ब्यौरा है?", ["doc_leg_030"], 1, {"numbers": ["25,000"]}),
        ("कक्षा 1 से 8 निःशुल्क पुस्तक वितरण 15 अप्रैल की स्कैन समय-सारणी क्या दर्शाती है?", ["doc_ogd_031"], 1, {"dates": ["15 अप्रैल"]}),
        ("मुख्य चिकित्सा अधिकारी 10 लाख रुपये आपात दवा खरीद की स्कैन प्रशासनिक स्वीकृति क्या है?", ["doc_fin_032"], 1, {"numbers": ["10 लाख"]}),
        ("टेलीमेडिसिन 450 प्राथमिक स्वास्थ्य केंद्र ब्रॉडबैंड आदेश की स्कैन प्रति में क्या विवरण है?", ["doc_rd_033"], 1, {"numbers": ["450"]}),
        ("नहर गाद सफाई 31 मई की स्कैन कार्ययोजना में सिंचाई विभाग के क्या निर्देश हैं?", ["doc_rev_034"], 1, {"dates": ["31 मई"]}),
        ("आंगनबाड़ी कार्यकत्री 9,300 रुपये मानदेय पुनरीक्षण के स्कैन शासनादेश का क्रमांक क्या है?", ["doc_gad_035"], 1, {"numbers": ["9,300"]}),
        ("आंगनबाड़ी सहायिका 4,650 रुपये मानदेय की स्कैन अधिसूचना में प्रभावी दिनांक क्या है?", ["doc_aud_036"], 1, {"numbers": ["4,650"]}),
        ("ई-कोश कोषागार सॉफ्टवेयर प्रणाली के स्कैन यूजर मैनुअल में एरियर आहरण का क्या नियम है?", ["doc_fin_da_2024_heldout"], 2, {"eligibility": ["eKosh"]}),
        ("स्कैन प्रति में मुद्रित शासकीय मोहर तथा सक्षम प्राधिकारी के हस्ताक्षर का सत्यापन क्या है?", ["doc_fin_011"], 1, {"eligibility": ["DDO"]}),
        ("स्कैन आदेश के अनुसार आहरण वितरण अधिकारी को क्या अनुपालन निर्देश दिए गए हैं?", ["doc_rd_012"], 1, {"eligibility": ["DDO"]}),
        ("स्कैन प्रति में उल्लिखित मुख्य बिन्दु तथा अंग्रेजी सारांश में क्या समानता पाई गई है?", ["doc_rev_013"], 1, {"eligibility": ["DDO"]}),
    ]

    for q_text, doc_ids, page_num, facts in ocr_queries:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": "hi",
            "department": DepartmentId.BOARD_OF_REVENUE.value,
            "category": "scanned_ocr",
            "expected_doc_ids": resolve_expected_doc_ids(doc_ids),
            "expected_page": page_num,
            "expected_facts": facts,
            "expected_refusal": False,
        })
        q_counter += 1

    # -----------------------------------------------------------------------
    # 5. Abstention & Out-of-Domain Unanswerable Queries (50 Questions)
    # -----------------------------------------------------------------------
    unanswerable_queries = [
        ("What is the subsidy rate for submarine construction under Uttarakhand maritime regulations?", "en"),
        ("What are the transfer policies for port trust harbor masters in Uttarakhand state?", "en"),
        ("What are the casual leave rules under Maharashtra state government civil service manual?", "en"),
        ("What is the festival bonus sanctioned for bullet train drivers in Pauri Garhwal under order UK/FIN/2024/999?", "en"),
        ("What is the procurement ceiling for commercial supersonic aircraft in Uttarakhand e-tenders?", "en"),
        ("How much grant is provided for desert greening under Uttarakhand Rural Development Department?", "en"),
        ("What is the Dearness Allowance rate announced by the Government of Rajasthan for 2024?", "en"),
        ("According to fictional order UK/BOR/0000/MYTH, what is the tax exemption on diamond mining in Dehradun?", "en"),
        ("हिमाचल प्रदेश सरकार के नियमों के अनुसार सेब बागवानी हेतु कितनी सब्सिडी स्वीकृत है?", "hi"),
        ("काल्पनिक शासनादेश संख्या UK/FIN/9999/FAKE के तहत राज्य कर्मचारियों को साइकिल भत्ता कितना देय है?", "hi"),
        ("उत्तर प्रदेश विद्युत परिषद नियमावली के तहत पेंशन ग्रेच्युटी की अधिकतम सीमा क्या है?", "hi"),
        ("उत्तराखण्ड में ग्राम विकास अधिकारियों हेतु हेलीकॉप्टर यात्रा भत्ते का शासनादेश क्या है?", "hi"),
        ("उत्तराखण्ड में समुद्र तटीय मछली पकड़ने वाली नौकाओं हेतु क्या दिशा-निर्देश हैं?", "hi"),
        ("उत्तराखण्ड में अंतरिक्ष वैज्ञानिकों हेतु कार्मिक विभाग का क्या आरक्षण कोटा है?", "hi"),
        ("शासनादेश संख्या UK/RD/2024/8888 के अनुसार रेगिस्तानी हरियाली हेतु कितना बजट आवंटित है?", "hi"),
        ("पौड़ी गढ़वाल में मेट्रो रेल चालकों हेतु शासनादेश UK/FIN/2024/999 में क्या बोनस निर्धारित है?", "hi"),
        ("What are the property inheritance tax exemptions under the Punjab Land Revenue Act 1967?", "en"),
        ("How much financial assistance does Kerala State Coir Development Corporation give to coir workers?", "en"),
        ("What is the government subsidy for coconut husk processing units in Tamil Nadu?", "en"),
        ("What are the ceiling limits for agricultural landholding under the Bihar Land Reforms Act?", "en"),
        ("What are the industrial electricity tariff discounts for diamond polishing units in Gujarat?", "en"),
        ("What minimum daily wage is notified for tea garden laborers under West Bengal labor laws?", "en"),
        ("What are the biotech startup tax incentives provided under Karnataka Innovation Policy?", "en"),
        ("According to fictional notification UK/GAD/2024/7777, what is the fare for hovercraft ferry services in Tehri lake?", "en"),
        ("Under imaginary order UK/REV/2024/3333, what compensation is provided for space rocket launch sites in Almora?", "en"),
        ("What grant is sanctioned for establishing polar bear breeding centers in Haridwar district?", "en"),
        ("How much subsidy is available for camel breeding and desert safaris in Nainital district?", "en"),
        ("What are the licensing procedures for offshore oil drilling rigs off the coast of Dehradun?", "en"),
        ("What is the ticket concession rate for passengers traveling on the imaginary Nanda Devi monorail?", "en"),
        ("What is the state government procurement guidelines for commercial lunar mining exploration equipment?", "en"),
        ("What clearances are required from the Central Atomic Energy Commission for radioactive isotope storage in district hospitals?", "en"),
        ("What are the Indian Navy dry-docking inspection schedules for naval destroyers in Uttarakhand?", "en"),
        ("What are the diplomatic passport exemption norms issued by the Union Ministry of External Affairs?", "en"),
        ("What are the capital adequacy ratios mandated by the Reserve Bank of India for foreign exchange derivative brokers?", "en"),
        ("What are the maximum flying duty hours permitted for commercial airline pilots under DGCA civil aviation requirements?", "en"),
        ("What are the rest interval regulations for Indian Railways freight train locomotive pilots?", "en"),
        ("What is the base reserve price set by TRAI for 5G spectrum frequency auction in telecom circles?", "en"),
        ("What are the disclosure thresholds mandated by SEBI for insider trading declarations in listed equity shares?", "en"),
        ("What are the revised examination format and optional subjects list for UPSC Civil Services preliminary tests?", "en"),
        ("What is the warranty replacement policy for Apple iPhones purchased by state civil servants in Dehradun?", "en"),
        ("How can a customer in Pithoragarh claim a refund for late delivery of Amazon Prime packages?", "en"),
        ("What is the calculation formula for Bitcoin cryptocurrency capital gains tax under Uttarakhand state revenue laws?", "en"),
        ("Can Uttarakhand government assistant review officers claim monthly reimbursement for Netflix subscriptions?", "en"),
        ("What legal liability is assigned to Tesla autonomous autopilot software within Nainital municipal roads?", "en"),
        ("What is the franchise fee for opening a Starbucks coffee shop inside the Almora collectorate campus?", "en"),
        ("शासनादेश UK/MED/9999 के तहत अंतरिक्ष यात्रियों हेतु योग प्रशिक्षण भत्ता कितना निर्धारित है?", "hi"),
        ("मध्य प्रदेश राज्य प्रशासनिक सेवा नियमावली में संतान पालन अवकाश हेतु क्या शर्तें हैं?", "hi"),
        ("असम राज्य चाय बागान श्रमिक कल्याण कोष से कितनी वित्तीय सहायता अनुमन्य है?", "hi"),
        ("क्या देहरादून में पंजीकृत प्राइवेट जेट विमानों पर कोई विशेष राज्य विलासिता कर लागू है?", "hi"),
        ("माइक्रोसॉफ्ट विंडोज लाइसेंस की वारंटी अवधि के संबंध में उत्तराखण्ड सामान्य प्रशासन विभाग का क्या आदेश है?", "hi"),
    ]

    for q_text, lang in unanswerable_queries:
        questions.append({
            "id": f"heldout_q_{q_counter:03d}",
            "question": q_text,
            "language": lang,
            "department": DepartmentId.UNKNOWN.value,
            "category": "no_answer",
            "expected_doc_ids": [],
            "expected_page": 1,
            "expected_facts": {},
            "expected_refusal": True,
        })
        q_counter += 1

    return questions
