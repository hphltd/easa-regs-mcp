"""Registry of EASA Easy Access Rules (EAR) books the server knows about.

Each book is published by EASA as a zipped Flat-OPC (Word 2003 XML package)
file that embeds an ``er:document`` table of contents with stable ERulesIds.
Download IDs are the numeric part of https://www.easa.europa.eu/en/downloads/<id>/en
and are taken from the book's landing page.

Some documents are only published as PDF (CS-22 Amendment 3, Special Conditions, ESF, deviations,
Certification Memoranda). Those books have ``kind="pdf"`` and list their documents in ``docs``;
see pdfbook.py for how they are split into rules.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DOWNLOAD_URL = "https://www.easa.europa.eu/en/downloads/{id}/en"


@dataclass(frozen=True)
class PdfDoc:
    ref: str             # citation key, e.g. 'SC-22.2014-01'
    title: str
    content_type: str    # CS | SC | ESF | DEV | CM
    download_id: int
    page: str            # EASA landing page of the document
    issue: str = ""      # e.g. 'Issue 2', 'ED Decision 2021/013/R'
    date: str = ""       # publication date as shown by EASA, ISO yyyy-mm-dd

    @property
    def url(self) -> str:
        return DOWNLOAD_URL.format(id=self.download_id)


@dataclass(frozen=True)
class Book:
    code: str            # short, stable key used in the DB and tools
    title: str
    xml_download_id: int
    landing_page: str
    kind: str = "xml"    # xml = EAR package (parse.py) | pdf = list of PDF documents (pdfbook.py)
    docs: tuple[PdfDoc, ...] = ()
    split: str = "doc"   # pdf books: 'doc' = one rule per document | 'cs' = one rule per CS/AMC paragraph

    @property
    def xml_url(self) -> str:
        return DOWNLOAD_URL.format(id=self.xml_download_id)


_CONSULT = "https://www.easa.europa.eu/en/document-library/product-certification-consultations/"


BOOKS: dict[str, Book] = {
    b.code: b
    for b in [
        Book(
            code="AIRCREW",
            title="Easy Access Rules for Aircrew (Regulation (EU) No 1178/2011)",
            xml_download_id=136679,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-aircrew-regulation-eu-no-11782011",
        ),
        Book(
            code="AIROPS",
            title="Easy Access Rules for Air Operations (Regulation (EU) No 965/2012)",
            xml_download_id=136682,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-air-operations",
        ),
        Book(
            code="SAILPLANES",
            title="Sailplane Rule Book - Easy Access Rules (Part-SFCL, Part-SAO, ...)",
            xml_download_id=136684,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "sailplane-rule-book-easy-access-rules",
        ),
        Book(
            code="BALLOONS",
            title="Easy Access Rules for Balloons (Part-BFCL, Part-BOP, ...)",
            xml_download_id=136683,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-balloons",
        ),
        Book(
            code="CONTAIR",
            title="Easy Access Rules for Continuing Airworthiness (Part-M, Part-ML, Part-145, Part-CAMO, ...)",
            xml_download_id=136699,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-continuing-airworthiness",
        ),
        Book(
            code="BASIC",
            title="Easy Access Rules for the Basic Regulation (Regulation (EU) 2018/1139)",
            xml_download_id=136659,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-basic-regulation-regulation-eu-20181139",
        ),
        Book(
            code="UAS",
            title="Easy Access Rules for Unmanned Aircraft Systems (drones)",
            xml_download_id=137111,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-unmanned-aircraft-systems",
        ),
        Book(
            code="AERODROMES",
            title="Easy Access Rules for Aerodromes (Regulation (EU) No 139/2014)",
            xml_download_id=136677,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-aerodromes",
        ),
        Book(
            code="SERA",
            title="Easy Access Rules for Standardised European Rules of the Air (SERA)",
            xml_download_id=136676,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-standardised-european-rules-air",
        ),
        Book(
            code="INITAIR",
            title="Easy Access Rules for Initial Airworthiness and Environmental Protection "
            "(Regulation (EU) No 748/2012)",
            xml_download_id=136660,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-initial-airworthiness-and-environmental",
        ),
        Book(
            code="INFOSEC",
            title="Easy Access Rules for Information Security (Regulations (EU) 2023/203 and 2022/1645)",
            xml_download_id=138790,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-information-security-regulations-eu-2023203-and-20221645",
        ),
        # AMC-20 is published per amendment, each with its own download id: bump it with each new amendment.
        Book(
            code="AMC20",
            title="Easy Access Rules for Acceptable Means of Compliance for Airworthiness of Products, Parts and "
            "Appliances (AMC-20), Amendment 23",
            xml_download_id=137992,
            landing_page="https://www.easa.europa.eu/en/document-library/easy-access-rules/"
            "easy-access-rules-acceptable-means-compliance-airworthiness",
        ),
        # The Easy Access Rules for CS-22 stop at Amendment 2; Amendment 3 exists only as a PDF.
        Book(
            code="CS22",
            title="CS-22 Sailplanes and Powered Sailplanes, Amendment 3 (ED Decision 2021/013/R)",
            xml_download_id=0,
            landing_page="https://www.easa.europa.eu/en/document-library/certification-specifications/"
            "cs-22-amendment-3",
            kind="pdf",
            split="cs",
            docs=(
                PdfDoc("CS-22", "Sailplanes and Powered Sailplanes, Amendment 3", "CS", 131414,
                       "https://www.easa.europa.eu/en/document-library/certification-specifications/cs-22-amendment-3",
                       "ED Decision 2021/013/R", "2021-09-17"),
            ),
        ),
        # Final documents tagged 'CS-22' in EASA's Product Certification Consultations library, not superseded.
        # Check that library (filter CS-22) for new or superseding documents and add them here.
        Book(
            code="SC22",
            title="EASA Special Conditions, Equivalent Safety Findings, Deviations and Certification Memoranda "
            "for CS-22 sailplanes and powered sailplanes (final documents)",
            xml_download_id=0,
            landing_page="https://www.easa.europa.eu/en/document-library/product-certification-consultations"
            "?certifiable%5B%5D=60",
            kind="pdf",
            split="doc",
            docs=(
                PdfDoc("SC-22.2014-01", "Installation of Electric Propulsion Units in Powered Sailplanes", "SC",
                       16912, _CONSULT + "installation-electric-propulsion-units-powered", "Issue 2", "2014-11-14"),
                PdfDoc("SC E-01", "Airworthiness standard for CS 22H electrical engines to be operated in powered "
                       "sailplanes", "SC", 116003, _CONSULT + "special-condition-airworthiness-standard-cs",
                       "", "2006-04-15"),
                PdfDoc("SC-ELA.2015-01", "Installation of Li-type storage batteries in sailplanes/powered "
                       "sailplanes, LSA and VLA", "SC", 48800, _CONSULT + "special-condition-sc-ela2015-01",
                       "", "2018-10-12"),
                PdfDoc("SC-B22.151-01", "Sustainer assisted aerotow", "SC", 131394,
                       _CONSULT + "final-special-condition-sc-b22151-01-sustainer", "Issue 01", "2021-09-14"),
                PdfDoc("SC CS-22 hand rudder control", "Airworthiness standards for CS-22 sailplanes with hand "
                       "rudder control", "SC", 65378, _CONSULT + "special-condition-airworthiness-standards-cs",
                       "", "2018-10-31"),
                PdfDoc("SC CS-22H turbine engine", "Airworthiness standard for CS-22H turbine engines to be "
                       "operated in powered sailplanes", "SC", 6037,
                       _CONSULT + "airworthiness-standard-cs-22h-new-special", "", "2010-02-25"),
                PdfDoc("DEV-B22.335-01", "Deviation from CS 22 requirements related to flutter and VD", "DEV",
                       117234, _CONSULT + "final-deviation-dev-b22335-01-cs-22", "", "2020-07-17"),
                PdfDoc("ESF CS 22.925(a)", "Equivalent Safety Finding to CS 22.925(a), Propeller clearance", "ESF",
                       119207, _CONSULT + "equivalent-safety-finding-cs-22925-propeller", "", "2020-10-05"),
                PdfDoc("CM-S-008", "Additive Manufacturing", "CM", 142436, _CONSULT + "additive-manufacturing",
                       "Issue 4", ""),
            ),
        ),
    ]
}

# A newer amendment published as its own book supersedes the same references in an older book:
# CS22 holds CS-22 Amendment 3, the SAILPLANES Easy Access Rules still carry CS-22 Amendment 2.
SUPERSEDES = {"CS22": "SAILPLANES"}

# Forks that publish their own index releases set EASA_REGS_REPO=<owner>/<repo> on their host
# (or EASA_REGS_INDEX_URL to point at any other copy of the prebuilt index).
GITHUB_REPO = os.environ.get("EASA_REGS_REPO", "muchsneaks/easa-regs-mcp")
INDEX_URL = os.environ.get(
    "EASA_REGS_INDEX_URL", f"https://github.com/{GITHUB_REPO}/releases/latest/download/easa_regs.sqlite")

DISCLAIMER = (
    "Unofficial reproduction of EASA Easy Access Rules for information only. "
    "Not legally binding - only the texts published in the Official Journal of the EU "
    "are authentic. Always verify against the current official publication "
    "before relying on it for operational or compliance decisions."
)

ATTRIBUTION = "Source: EASA Easy Access Rules (eRules XML), (c) European Union Aviation Safety Agency."
