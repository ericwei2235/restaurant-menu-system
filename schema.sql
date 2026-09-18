CREATE TABLE menu_items(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_number TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL
);


CREATE TABLE menu_item_prices(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_item_id INTEGER NOT NULL,
    size_label TEXT,
    price INTEGER,
    FOREIGN KEY (menu_item_id) REFERENCES menu_items (id)
);

CREATE TABLE orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE order_items(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    menu_item_price_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (order_id) REFERENCES orders (id),
    FOREIGN KEY (menu_item_price_id) REFERENCES menu_item_prices (id)
);