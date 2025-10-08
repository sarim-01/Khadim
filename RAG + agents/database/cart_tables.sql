-- Cart Management Tables
CREATE TABLE IF NOT EXISTS cart (
    cart_id UUID PRIMARY KEY,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'converted_to_order', 'abandoned')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Table for items in cart (can be menu items or deals)
CREATE TABLE IF NOT EXISTS cart_items (
    cart_id UUID REFERENCES cart(cart_id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    item_type TEXT CHECK (item_type IN ('menu_item', 'deal')),
    quantity INTEGER DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL,
    special_requests TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT cart_items_pkey PRIMARY KEY (cart_id, item_id, item_type)
);

-- Drop existing triggers and functions if they exist
DROP TRIGGER IF EXISTS validate_cart_item_trigger ON cart_items;
DROP TRIGGER IF EXISTS update_cart_timestamp ON cart;
DROP FUNCTION IF EXISTS validate_cart_item();
DROP FUNCTION IF EXISTS update_cart_timestamp();

-- Function to validate cart item references
CREATE OR REPLACE FUNCTION validate_cart_item()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.item_type = 'menu_item' THEN
        IF NOT EXISTS (SELECT 1 FROM menu_item WHERE item_id = NEW.item_id) THEN
            RAISE EXCEPTION 'Invalid menu_item reference: %', NEW.item_id;
        END IF;
    ELSIF NEW.item_type = 'deal' THEN
        IF NOT EXISTS (SELECT 1 FROM deal WHERE deal_id = NEW.item_id) THEN
            RAISE EXCEPTION 'Invalid deal reference: %', NEW.item_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to validate cart item references
CREATE TRIGGER validate_cart_item_trigger
    BEFORE INSERT OR UPDATE ON cart_items
    FOR EACH ROW
    EXECUTE FUNCTION validate_cart_item();

-- Function to update cart timestamp
CREATE OR REPLACE FUNCTION update_cart_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update cart timestamp
CREATE TRIGGER update_cart_timestamp
    BEFORE UPDATE ON cart
    FOR EACH ROW
    EXECUTE FUNCTION update_cart_timestamp();