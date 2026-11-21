# inventory-cli

A small command-line tool that tracks stock items in a JSON file.

    python3 -m inventory --db stock.json add --sku A1 --name Widget --qty 3 --price 2.5
    python3 -m inventory --db stock.json list
    python3 -m inventory --db stock.json report

## Wishlist

- JSON output for `list` and a future `export`.
- A web view of the stock levels.
