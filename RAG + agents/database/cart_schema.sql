-- Cart Management Schema
CREATE TABLE IF NOT EXISTS cart (
    cart_id TEXT PRIMARY KEY,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cart_items (
    cart_id TEXT,
    item_id INTEGER,
    item_type TEXT CHECK (item_type IN ('menu_item', 'deal')),
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10,2),
    special_requests TEXT,
    FOREIGN KEY (cart_id) REFERENCES cart(cart_id) ON DELETE CASCADE,
    PRIMARY KEY (cart_id, item_id, item_type)
);