# Bill Lens

Bill Lens is a portfolio project for turning Victorian household electricity bill PDFs into structured, explainable, and verifiable data. The engineering rule is to use an LLM where a document is ambiguous and deterministic Python code for calculations, units, and validation.

The project is currently at **Milestone 0: extraction contract and golden dataset design**. There is no application or measured extraction accuracy yet.

- [Initial extraction contract](docs/extraction-contract.md)
- [Five-bill synthetic dataset plan](dataset/README.md)
- [ADR-001: PDF extraction strategy](docs/adr/001-pdf-extraction-strategy.md)

Next, create the synthetic PDFs and manually check their `expected.json` labels against the PDFs. The first application slice will then upload a PDF, extract and validate fields, persist the result, and return structured JSON.
