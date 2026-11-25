# easa-regs-mcp

**Give Claude (or any MCP client) the EASA rulebook.** Search, read and cite the EASA Easy Access Rules with
exact references instead of half-remembered answers.

> *"What do I need to revalidate my SEP class rating by experience?"*
> Claude calls `search_easa_rules`, reads **FCL.740.A**, and answers quoting (b)(1)(ii): 12 hours in class within
> 12 months incl. 6 h PIC, 12 take-offs and landings and 1 h refresher training with an FI/CRI, plus the linked AMC/GM.

Built by a CPL(A)/IR flight instructor who got tired of scrolling 1,500-page PDFs.

## Coverage

| Book | Contents |
|---|---|
| `AIRCREW` | Part-FCL, Part-MED, Part-CC, Part-ARA, Part-ORA, Part-DTO |
| `AIROPS` | Part-ORO, CAT, NCO, NCC, SPO, SPA, IAM, CS-FTL |
| `SERA` | Standardised European Rules of the Air |
| `SAILPLANES` | Sailplane Rule Book (Part-SFCL, Part-SAO, ...) |
| `BALLOONS` | Part-BFCL, Part-BOP, ... |
| `CONTAIR` | Continuing airworthiness: Part-M, Part-ML, Part-145, Part-CAMO, Part-CAO |
| `BASIC` | Basic Regulation (EU) 2018/1139 |
| `UAS` | Drones (Regulations (EU) 2019/947 and 2019/945) |
| `AERODROMES` | Regulation (EU) No 139/2014 |
| `INITAIR` | Initial airworthiness, Regulation (EU) No 748/2012: Part 21 (certification, DOA, POA), Part 21 Light, with AMC/GM |
| `INFOSEC` | Information security (Part-IS), Regulations (EU) 2023/203 and 2022/1645, with AMC/GM |
| `AMC20` | AMC-20: general AMC for airworthiness of products, parts and appliances (Amendment 23) |
| `CS22` | CS-22 Sailplanes and Powered Sailplanes, Amendment 3 (from the PDF; the Easy Access Rules stop at Amendment 2) |
| `SC22` | Final EASA Special Conditions, Equivalent Safety Findings, Deviations and Certification Memoranda tagged CS-22 (PDF) |
| `JAR22` | JAR-22 Sailplanes and Powered Sailplanes, Amendment 6 (JAA, 2001; superseded by CS-22). **Only in self-built indexes**: there is no official source to download it from, so the PDF must be supplied as `data/raw/JAR22/jar22.pdf` |
| `UCL_SM` | Czech national: *Směrnice ÚCL*, directives of the Czech Civil Aviation Authority (CAA-TI, CAA-ST, CAA/S-SP, ÚCL-2xx), in Czech (PDF) |
| `UCL_PO` | Czech national: *Poradní oběžníky ÚCL*, advisory circulars (PO/ST, PO/TI to L8/A, Part M/ML/145, PO-SL), in Czech (PDF) |
| `CZ_L` | Czech national: *Letecké předpisy řady L* (L 1-L 19, L 8/A, L 14H, L 4444, L 7030, L 8168, L 8400, L Frazeologie, ...), one rule per chapter, in Czech (PDF from LIS ŘLP ČR) |

Every rule keeps its stable EASA `ERulesId`, type (**IR** binding / **AMC** / **GM** / **CS**), location in the
regulation, amending regulation, applicability date and its linked AMC/GM. Tables and list structure are preserved.
The index is rebuilt weekly from EASA's official XML by a GitHub Action and published as a release.

The ÚCL documents (type **SM** directive / **PO** advisory circular) are read from the two listing pages at
[caa.gov.cz/dokumenty/predpisy](https://www.caa.gov.cz/dokumenty/predpisy/) on every rebuild, so new and revised
documents appear without code changes. Search them in Czech (`zkušební lety`, `prodloužení platnosti OLZ`) or by
reference (`CAA-TI-010-n/99`, `PO/ST-20-6`). Long documents are split into parts (`<ref> (část N)`) at their
headings. Scanned PDFs without a text layer are listed with their description and link only.

The Czech L series (type **L**) is read from the data files behind
[aim.rlp.cz/predpisy](https://aim.rlp.cz/predpisy/predpisy/index.htm), the free public copy of the Letecká
informační služba (LIS) of ŘLP ČR. Every chapter is one rule (`L 8 Část IIIB Hlava 2`, `L 2 Hlava 4`) carrying the
amendment in force; `get_easa_rule("L 8/A")` returns an overview with all chapters of the regulation.

## Tools

| Tool | Purpose |
|---|---|
| `search_easa_rules(query, book?, content_type?, limit?)` | Ranked search. Understands rule refs (`FCL.740`), plain English, common abbreviations (SEP, TMG, PIC, SVFR...) and common German terms. When an AMC/GM matches, its parent IR is shown first. |
| `get_easa_rule(ref, book?, include_related?, max_chars?)` | Full text, citation, metadata, parent IR and all AMC/GM. Accepts `FCL.740.A`, `AMC1 FCL.740(b)`, `sera.5010` or an ERulesId. |
| `browse_easa_toc(book, section_contains?)` | Book structure with IR/AMC/GM counts; lists all rules of a subpart (e.g. `"SUBPART H"`). |
| `list_easa_sources()` | Indexed books, publication dates, disclaimer. |

## Install

**Website with one-click setup:** https://easa-regs-site.vercel.app/

| Where | How |
|---|---|
| **Claude (web, desktop, iOS, Android)** | *Customize › Connectors › + › Add custom connector*, paste `https://easa-regs-mcp-murex.vercel.app/mcp`. Works on the Free plan too. |
| **Claude Desktop, local** | Download [`easa-regs.mcpb`](https://github.com/muchsneaks/easa-regs-mcp/releases/latest/download/easa-regs.mcpb), double-click, *Install*. No Python needed. |
| **Claude Code** | `claude mcp add easa-regs -- uvx --from git+https://github.com/muchsneaks/easa-regs-mcp easa-regs-mcp` |
| **Any MCP client** | `{"command": "uvx", "args": ["--from", "git+https://github.com/muchsneaks/easa-regs-mcp", "easa-regs-mcp"]}` |

The first start downloads the prebuilt index (~33 MB) from the latest release and refreshes it weekly.

### Host the remote connector yourself

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/hphltd/easa-regs-mcp&env=EASA_REGS_REPO&envDescription=GitHub%20repo%20whose%20releases%20hold%20the%20index%20(hphltd%2Feasa-regs-mcp))
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/hphltd/easa-regs-mcp)

**Vercel / serverless:** `app.py` exposes a lifespan-free ASGI app (`easa_regs.asgi:app`). It downloads the
prebuilt index to `/tmp` on first use and refreshes it daily, so no build step or redeploy is needed.
Locally: `uvicorn app:app --port 8000`.

**Docker host:** `docker build -t easa-regs-mcp . && docker run -p 8000:8000 easa-regs-mcp`.
The MCP endpoint is `https://<your-host>/mcp` (stateless streamable HTTP), health check at `/health`.
Optional `ALLOWED_HOSTS=your.domain` enables DNS-rebinding protection.
A fork that publishes its own index releases sets `EASA_REGS_REPO=<owner>/<repo>` on its host
(or `EASA_REGS_INDEX_URL` to any copy of `easa_regs.sqlite`). This fork (with Part 21, Part-IS, AMC-20,
CS-22 and the CS-22 Special Conditions) uses `EASA_REGS_REPO=hphltd/easa-regs-mcp`: `render.yaml` and the
`Dockerfile` already set it; on Vercel enter it when the button asks (or under *Settings → Environment Variables*).

## Develop / build the index yourself

```bash
git clone https://github.com/muchsneaks/easa-regs-mcp && cd easa-regs-mcp
./setup.sh      # venv, install, download EASA XML, build index, run tests, optional Claude Desktop registration
```

or step by step: `pip install -e ".[dev]" && easa-regs-fetch && easa-regs-build && pytest -q`.
`python tests/eval_questions.py` prints the retrieval hit rate on 30 real pilot/instructor questions.

```
src/easa_regs/
  sources.py   books, EASA download IDs, disclaimer
  fetch.py     download EASA XML zips / the prebuilt index (stdlib only)
  parse.py     EASA eRules XML (Flat OPC + er: metadata) -> rule records
  db.py        SQLite FTS5 index, search + rerank, lookup, AMC/GM links
  build.py     parse + index + manifest.json
  server.py    FastMCP server (stdio or streamable HTTP)
  asgi.py      serverless ASGI app for the hosted connector
mcpb/          Claude Desktop extension (built by scripts/build_mcpb.py, attached to every release)
app.py, vercel.json       hosted connector on Vercel (serverless)
Dockerfile, render.yaml   hosted connector on any Docker host
```

If EASA changes a download link, update the ID in `sources.py` (the number in
`https://www.easa.europa.eu/en/downloads/<id>/en` on the book's page).
PDF-only books (`CS22`, `SC22`) list their documents in `sources.py` and are split by `pdfbook.py`
(needs `pdfminer.six`, part of the `dev` extra). The ÚCL books (`UCL_SM`, `UCL_PO`) take their document list from
the ÚCL listing pages (`ucl.py`); if ÚCL changes its page layout, `parse_listing` is the place to adapt.
The L series (`CZ_L`) comes from the LIS `data.js` files (`lis.py`). JAR-22 (`JAR22`) is parsed by `jar.py` from the
JAA two-column PDF (requirements and inline AMC are told apart by font); `easa-regs-fetch` never downloads it and
`easa-regs-build` includes it only when `data/raw/JAR22/jar22.pdf` exists, so the published release index does not
contain it.

## Limitations

- Unofficial and **not legally binding**. Only the texts in the Official Journal of the EU are authentic.
  Always verify before operational or compliance decisions.
- National rules other than the ÚCL directives and advisory circulars and the Czech L series (e.g. LBA, NfL,
  AIP, Czech laws and decrees), ICAO documents in English and operator manuals are not included. The Czech texts
  are extracted from PDF; only the documents published by ÚCL and the printed L-series text are authentic.
- The smallest unit is an EASA "topic" (one rule with all its paragraphs).
- Future-applicable versions are not yet separated from current ones.

## Licence

Code: MIT. Content: EASA Easy Access Rules, (c) European Union Aviation Safety Agency - "Reproduction is
authorised, provided the source is acknowledged" ([EASA copyright notice](https://www.easa.europa.eu/en/copyright-disclaimer)).
The server includes the attribution and disclaimer in its responses.
