# Contributing

Thanks for improving Invoice Generator.

## Development setup

Use Python 3.11 or newer and install `requirements-dev.lock`. Run the commands from the README before opening a pull request.

Keep these invariants:

- private owner, client, reference PDF, and output data never enter Git;
- workspace files and skill runtime remain separate;
- a failed render never consumes a number or changes the ledger;
- the PDF remains one A4 page and existing EUR/USD geometry remains stable;
- new clients require an explicit alias and first invoice number.

Add focused tests for behavior changes. Do not update reference PDFs unless the visual change is intentional and explained.
