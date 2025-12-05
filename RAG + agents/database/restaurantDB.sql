----------------------
-- NUKING OLD TABLES (for safe re-running)
----------------------
DROP TABLE IF EXISTS deal_item CASCADE;
DROP TABLE IF EXISTS menu_item_chefs CASCADE;
DROP TABLE IF EXISTS deal CASCADE;
DROP TABLE IF EXISTS menu_item CASCADE;
DROP TABLE IF EXISTS chef CASCADE;
DROP TABLE IF EXISTS kitchen_tasks CASCADE;

-- Also drop agent-created tables
DROP TABLE IF EXISTS cart_items CASCADE;
DROP TABLE IF EXISTS cart CASCADE;
DROP TABLE IF EXISTS orders CASCADE;

----------------------
-- creating tables
----------------------
CREATE TABLE chef (
    cheff_id SERIAL PRIMARY KEY,
    cheff_name TEXT NOT NULL,
    specialty TEXT,
    active_status BOOLEAN DEFAULT TRUE,
    max_current_orders INT
);


CREATE TABLE menu_item (
    item_id SERIAL PRIMARY KEY,
    item_name TEXT NOT NULL,
    item_description TEXT,
    item_category TEXT CHECK (item_category IN ('starter','main','drink','side','bread')),
    item_cuisine TEXT CHECK (item_cuisine IN ('BBQ','Desi','Fast Food','Chinese','Drinks')),
    item_price DECIMAL(7,2),
    item_cost DECIMAL(7,2),
    tags TEXT[],
    availability BOOLEAN DEFAULT TRUE,
    serving_size INT,
    quantity_description TEXT,
    prep_time_minutes INT
);


CREATE TABLE deal (
    deal_id SERIAL PRIMARY KEY,
    deal_name TEXT NOT NULL,
    deal_price DECIMAL(7,2),
    active BOOLEAN DEFAULT TRUE,
    serving_size INT
);


CREATE TABLE deal_item (
    deal_id      INT NOT NULL REFERENCES deal(deal_id) ON DELETE CASCADE,
    menu_item_id INT NOT NULL REFERENCES menu_item(item_id),
    quantity     INT NOT NULL,
    PRIMARY KEY (deal_id, menu_item_id)
);


CREATE TABLE menu_item_chefs (
    menu_item_id INT REFERENCES menu_item(item_id),
    chef_id INT REFERENCES chef(cheff_id),
    PRIMARY KEY (menu_item_id, chef_id)
);

CREATE TABLE IF NOT EXISTS kitchen_tasks (
    task_id TEXT PRIMARY KEY,
    order_id INT NOT NULL,
    menu_item_id INT,
    item_name TEXT,
    qty INT,
    station TEXT,
    assigned_chef TEXT,
    estimated_minutes INT,
    status TEXT DEFAULT 'QUEUED',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

select * from kitchen_tasks
select * from cart
select * from cart_items

----------------------
-- adding cheffs
----------------------
INSERT INTO chef (cheff_name, specialty, active_status, max_current_orders) VALUES
('Ali Khan', 'BBQ', TRUE, 4),
('Shah Ali', 'BBQ', TRUE, 4),
('Imran Qureshi', 'Desi', TRUE, 3),
('Fatima Noor', 'Desi', TRUE, 3),
('abdul mateen', 'Fast Food', TRUE, 3),
('akbar ahmed', 'Fast Food', TRUE, 3),
('esha khurram', 'Chinese', TRUE, 2),
('abid Ali', 'Chinese', TRUE, 3),
('Rashid Khan', 'Breads', TRUE, 6),
('Fazal Haq', 'Drinks', TRUE, 5);


----------------------
-- adding menu items
----------------------
-- Fast food
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Cheeseburger', 'Classic beef patty with cheese, lettuce, tomato, and sauce',
 'main', 'Fast Food', 450, 270,
 ARRAY['beef','burger','mild','contains_dairy','contains_gluten','halal'],
 TRUE, 1, '1 burger (200g)', 15),
 
('Chicken Burger', 'Crispy chicken fillet, mayo, lettuce, and tomato',
 'main', 'Fast Food', 375, 225,
 ARRAY['chicken','burger','mild','contains_dairy','contains_gluten','halal'],
 TRUE, 1, '1 burger (180g)', 15),
 
('Veggie Burger', 'Grilled vegetable patty with cheese and greens',
 'main', 'Fast Food', 300, 180,
 ARRAY['vegetarian','burger','mild','contains_dairy','contains_gluten'],
 TRUE, 1, '1 burger (170g)', 15),
 
('Fries', 'Golden fried potato sticks',
 'side', 'Fast Food', 200, 120,
 ARRAY['vegetarian','fries','non_spicy','vegan','gluten_free','all_year'],
 TRUE, 1, '150g', 10),
 
('Chicken Nuggets', 'Breaded chicken bites with dip',
 'side', 'Fast Food', 450, 270,
 ARRAY['chicken','nuggets','mild','contains_gluten','halal'],
 TRUE, 1, '8 pieces (120g)', 10),
 
('Fish Fillet Sandwich', 'Fried fish fillet, tartar sauce, lettuce',
 'main', 'Fast Food', 650, 390,
 ARRAY['fish','sandwich','mild','contains_gluten','contains_dairy'],
 TRUE, 1, '1 sandwich (250g)', 15),
 
('Onion Rings', 'Crispy battered onion rings',
 'side', 'Fast Food', 350, 210,
 ARRAY['vegetarian','onion','mild','contains_gluten'],
 TRUE, 1, '8 rings (120g)', 10),
 
('Club Sandwich', 'Triple-layered sandwich with chicken, egg, and veggies',
 'main', 'Fast Food', 700, 420,
 ARRAY['chicken','sandwich','mild','contains_eggs','contains_gluten','contains_dairy'],
 TRUE, 1, '4 pieces (300g)', 15),
 
('Zinger Burger', 'Spicy fried chicken fillet, lettuce, and mayo',
 'main', 'Fast Food', 550, 330,
 ARRAY['chicken','spicy','burger','contains_dairy','contains_gluten','halal'],
 TRUE, 1, '1 burger (200g)', 15),
 
('Loaded Fries', 'Fries topped with cheese, jalapenos, chicken, and sauce',
 'side', 'Fast Food', 550, 330,
 ARRAY['vegetarian','fries','chicken','cheese','mild_spicy','contains_dairy'],
 TRUE, 1, '200g', 10);


-- Chinese
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Kung Pao Chicken', 'Stir-fried chicken with peanuts and chili',
 'main', 'Chinese', 1200, 720,
 ARRAY['chicken','spicy','contains_nuts','contains_soy','halal'],
 TRUE, 3, '600g', 20),
 
('Sweet and Sour Chicken', 'Crispy chicken in tangy sauce',
 'main', 'Chinese', 1150, 690,
 ARRAY['chicken','sweet','tangy','contains_gluten','halal'],
 TRUE, 3, '600g', 20),
 
('Chicken Chow Mein', 'Stir-fried noodles with chicken and vegetables',
 'main', 'Chinese', 1000, 600,
 ARRAY['chicken','noodles','mild','contains_gluten','contains_soy','halal'],
 TRUE, 2, '500g', 20),
 
('Vegetable Spring Rolls', 'Crispy rolls with mixed vegetable filling',
 'starter', 'Chinese', 600, 360,
 ARRAY['vegetarian','starter','mild','contains_gluten','vegan'],
 TRUE, 2, '6 pieces', 10),
 
('Beef with Black Bean Sauce', 'Sliced beef in savory black bean sauce',
 'main', 'Chinese', 1350, 810,
 ARRAY['beef','sauce','mild','contains_soy','halal'],
 TRUE, 3, '600g', 20),
 
('Egg Fried Rice', 'Rice stir-fried with egg and vegetables',
 'side', 'Chinese', 800, 480,
 ARRAY['vegetarian','rice','mild','contains_eggs','contains_soy'],
 TRUE, 2, '300g', 10),
 
('Hot and Sour Soup', 'Spicy, tangy soup with tofu and veggies',
 'starter', 'Chinese', 850, 510,
 ARRAY['vegetarian','soup','spicy','tangy','vegan','contains_soy'],
 TRUE, 4, '1 bowl of 600ml', 15),
 
('Szechuan Beef', 'Spicy beef with Szechuan peppers',
 'main', 'Chinese', 1450, 870,
 ARRAY['beef','very_spicy','contains_soy','halal'],
 TRUE, 3, '600g', 25),
 
('Chicken Manchurian', 'Fried chicken balls in spicy sauce',
 'main', 'Chinese', 1250, 750,
 ARRAY['chicken','spicy','contains_gluten','contains_soy','halal'],
 TRUE, 3, '600g', 20),
 
('Fish Crackers', 'Crispy fish-flavored snacks',
 'side', 'Chinese', 500, 300,
 ARRAY['fish','snack','mild','contains_gluten'],
 TRUE, 2, '12-15 pieces', 5);


-- Desi
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Chicken Karahi', 'Spicy chicken curry with tomatoes and green chilies',
 'main', 'Desi', 2250, 1350,
 ARRAY['chicken','spicy','curry','contains_dairy','halal','goes_with_naan'],
 TRUE, 4, '1kg', 30),
 
('Beef Biryani', 'Aromatic rice with beef and spices',
 'main', 'Desi', 1250, 750,
 ARRAY['beef','rice','mild_spicy','contains_dairy','halal'],
 TRUE, 3, '1 plate (500g)', 15),
 
('Daal Chawal', 'Lentil curry served with rice',
 'main', 'Desi', 650, 390,
 ARRAY['vegetarian','lentil','rice','mild','vegan','gluten_free'],
 TRUE, 2, '1 plate (350g)', 10),
 
('Nihari', 'Slow-cooked beef stew',
 'main', 'Desi', 1350, 810,
 ARRAY['beef','stew','mild_spicy','halal','goes_with_naan'],
 TRUE, 4, '500g', 25),
 
('Aloo Paratha', 'Flatbread stuffed with spiced potatoes',
 'bread', 'Desi', 250, 150,
 ARRAY['vegetarian','bread','mild','contains_gluten','contains_dairy'],
 TRUE, 1, '1 piece', 10),
 
('Palak Paneer', 'Spinach curry with cottage cheese',
 'main', 'Desi', 850, 510,
 ARRAY['vegetarian','cheese','curry','mild','contains_dairy','goes_with_naan'],
 TRUE, 3, '1 plate (600g)', 20),
 
('Chana Chaat', 'Spicy chickpea salad',
 'starter', 'Desi', 150, 90,
 ARRAY['vegetarian','chickpea','salad','tangy','spicy','vegan','gluten_free'],
 TRUE, 1, '200g', 5),
 
('Samosa Platter', 'Fried pastry with potato and pea filling',
 'starter', 'Desi', 250, 150,
 ARRAY['vegetarian','starter','pastry','mild_spicy','contains_gluten','vegan'],
 TRUE, 1, '2 samosa pieces', 5),
 
('Seekh Kabab', 'Minced meat skewers grilled to perfection',
 'main', 'Desi', 1350, 810,
 ARRAY['meat','kebab','spicy','halal','gluten_free'],
 TRUE, 4, '8 kababs', 25),
 
('Chicken Handi', 'Creamy chicken curry cooked in a clay pot',
 'main', 'Desi', 2400, 1440,
 ARRAY['chicken','curry','creamy','mild_spicy','contains_dairy','halal','goes_with_naan'],
 TRUE, 4, '1kg', 30);


-- BBQ
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Chicken Tikka', 'Marinated chicken pieces grilled on skewers',
 'main', 'BBQ', 1200, 720,
 ARRAY['chicken','grilled','bbq','spicy','contains_dairy','halal','gluten_free'],
 TRUE, 2, '1 leg and 1 chest piece', 20),
 
('Beef Boti', 'Cubes of beef marinated and grilled',
 'main', 'BBQ', 1450, 870,
 ARRAY['beef','grilled','bbq','spicy','contains_dairy','halal','gluten_free'],
 TRUE, 4, '12 pieces', 25),
 
('Malai Boti', 'Creamy, tender chicken cubes grilled',
 'main', 'BBQ', 1400, 840,
 ARRAY['chicken','creamy','grilled','bbq','mild','contains_dairy','halal','gluten_free'],
 TRUE, 4, '12 pieces', 20),
 
('Reshmi Kebab', 'Soft, silky chicken kebabs',
 'main', 'BBQ', 1350, 810,
 ARRAY['chicken','kebab','bbq','mild','contains_dairy','halal','gluten_free'],
 TRUE, 4, '8 pieces', 25),
 
('Grilled Fish', 'Spiced fish fillet grilled over charcoal',
 'main', 'BBQ', 1600, 960,
 ARRAY['fish','grilled','bbq','spicy','gluten_free','seasonal_summer'],
 TRUE, 4, '800g', 20);


-- Drinks
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Cola', 'Chilled carbonated soft drink',
 'drink', 'Drinks', 150, 90,
 ARRAY['cold','soft_drink','non_spicy','vegan','gluten_free','all_year'],
 TRUE, 1, '330 ml', 2),
 
('Lemonade', 'Freshly squeezed lemon juice with sugar',
 'drink', 'Drinks', 250, 150,
 ARRAY['cold','lemon','tangy','vegan','gluten_free','seasonal_summer'],
 TRUE, 1, '400 ml', 5),
 
('Mint Margarita', 'Refreshing mint and lemon mocktail',
 'drink', 'Drinks', 350, 210,
 ARRAY['cold','mint','mocktail','refreshing','vegan','gluten_free','seasonal_summer'],
 TRUE, 1, '350 ml', 5),
 
('Green Tea', 'Hot brewed green tea',
 'drink', 'Drinks', 200, 120,
 ARRAY['hot','tea','mild','vegan','gluten_free','all_year'],
 TRUE, 1, '250 ml', 5),
 
('Chai', 'Milk tea, a South Asian favorite',
 'drink', 'Drinks', 250, 150,
 ARRAY['hot','tea','milk','sweet','contains_dairy','all_year'],
 TRUE, 1, '250 ml', 5),
 
('Iced Coffee', 'Chilled coffee with milk and ice',
 'drink', 'Drinks', 450, 270,
 ARRAY['cold','coffee','milk','contains_dairy','all_year'],
 TRUE, 1, '350 ml', 5),
 
('Strawberry Shake', 'Creamy milkshake with fresh strawberries',
 'drink', 'Drinks', 400, 240,
 ARRAY['cold','shake','strawberry','sweet','contains_dairy','seasonal_summer'],
 TRUE, 1, '350 ml', 5),
 
('Orange Juice', 'Freshly squeezed orange juice',
 'drink', 'Drinks', 350, 210,
 ARRAY['cold','juice','orange','sweet','vegan','gluten_free','seasonal_winter'],
 TRUE, 1, '300 ml', 5),
 
('Water Bottle', 'Chilled mineral water',
 'drink', 'Drinks', 150, 90,
 ARRAY['cold','water','non_spicy','vegan','gluten_free','all_year'],
 TRUE, 1, '500 ml', 2);


-- Bread
INSERT INTO menu_item (
  item_name, item_description, item_category, item_cuisine,
  item_price, item_cost, tags, availability,
  serving_size, quantity_description, prep_time_minutes
) VALUES
('Roti', 'Traditional whole wheat flatbread, soft and fresh',
 'bread', 'Desi', 50, 30,
 ARRAY['bread','wheat','mild','vegan','all_year'],
 TRUE, 1, '1 piece', 1),
 
('Naan', 'Soft, leavened white flour bread, baked in a tandoor',
 'bread', 'Desi', 70, 42,
 ARRAY['bread','white_flour','mild','contains_dairy','vegetarian','all_year'],
 TRUE, 1, '1 piece', 1),
 
('Garlic Naan', 'Naan topped with garlic and herbs',
 'bread', 'Desi', 100, 60,
 ARRAY['bread','garlic','mild','contains_dairy','vegetarian','all_year'],
 TRUE, 1, '1 piece', 3),
 
('Paratha', 'Flaky, layered flatbread, pan-fried with ghee',
 'bread', 'Desi', 70, 42,
 ARRAY['bread','ghee','mild','contains_dairy','vegetarian','all_year'],
 TRUE, 1, '1 piece', 3),
 
('Chapatti', 'Thin, soft whole wheat flatbread',
 'bread', 'Desi', 60, 36,
 ARRAY['bread','wheat','mild','vegan','all_year'],
 TRUE, 1, '1 piece', 1);


----------------------
-- adding deals
----------------------

-- Insert deals 

INSERT INTO deal (deal_name, deal_price, serving_size) VALUES
('Fast Solo A',         ROUND((450+200+150)*0.9,2), 1),
('Fast Solo B',         ROUND((375+350+250)*0.9,2), 1),
('Fast Duo',            ROUND((2*(450+200+250))*0.9,2), 2),
('Fast Squad',          ROUND((2*700+1*375+1*450+2*550+4*150)*0.9,2), 4),
('Fast Food Big Party', ROUND((2*450+550+300+2*375+2*400+2*450+150+250+200+550+350+450)*0.9,2), 6),

('Chinese Solo',        ROUND((1000+200)*0.9,2), 1),
('Chinese Duo',         ROUND((1000+850+2*150)*0.9,2), 2),
('Chinese Squad A',     ROUND((1450+1000+2*800+850+4*350)*0.9,2), 4),
('Chinese Squad B',     ROUND((2*1250+2*600+4*450)*0.9,2), 4),
('Chinese Party Variety',ROUND((1150+1200+2*600+850+6*350)*0.9,2), 6),

('BBQ Solo',            ROUND((1200+250+50)*0.9,2), 1),
('BBQ Duo',             ROUND((1450+2*350+4*70)*0.9,2), 2),
('BBQ Squad',           ROUND((1200+1600+1450+4*150+4*100)*0.9,2), 4),
('BBQ Party A',         ROUND((2*1350+2*1400+6*450+3*70+3*70)*0.9,2), 6),
('BBQ Party B',         ROUND((3*1450+1200+6*400+4*60+3*100)*0.9,2), 6),

('Desi Solo',           ROUND((650+250+50)*0.9,2), 1),
('Desi Duo',            ROUND((2*(150+150+250))*0.9,2), 2),
('Desi Squad A',        ROUND((2*1350+4*250+4*350)*0.9,2), 4),
('Desi Squad B',        ROUND((2250+1250+850+4*250)*0.9,2), 4),
('Desi Party',          ROUND((2*2400+1250+3*100+3*150+3*350+3*60)*0.9,2), 6)
;


---------------------------
-- adding deal items
---------------------------

INSERT INTO deal_item (deal_id, menu_item_id, quantity) VALUES
-- deal_id 1: Fast Solo A
(1,1,1),(1,4,1),(1,36,1),

-- deal_id 2: Fast Solo B
(2,2,1),(2,7,1),(2,37,1),

-- deal_id 3: Fast Duo
(3,1,2),(3,4,2),(3,37,2),

-- deal_id 4: Fast Squad
(4,8,2),(4,2,1),(4,1,1),(4,10,2),(4,36,4),

-- deal_id 5: Fast Food Big Party
(5,1,2),(5,9,1),(5,3,1),(5,2,2),(5,42,2),(5,41,2),(5,36,1),(5,37,1),(5,4,1),(5,10,1),(5,7,1),(5,5,1),

-- deal_id 6: Chinese Solo
(6,13,1),(6,39,1),

-- deal_id 7: Chinese Duo
(7,11,1),(7,17,1),(7,44,2),

-- deal_id 8: Chinese Squad A
(8,18,1),(8,13,1),(8,16,2),(8,17,1),(8,43,4),

-- deal_id 9: Chinese Squad B
(9,19,2),(9,14,2),(9,41,4),

-- deal_id 10: Chinese Party Variety
(10,12,1),(10,11,1),(10,14,2),(10,17,1),(10,43,6),

-- deal_id 11: BBQ Solo
(11,31,1),(11,37,1),(11,45,1),

-- deal_id 12: BBQ Duo
(12,32,1),(12,38,2),(12,46,4),

-- deal_id 13: BBQ Squad
(13,31,1),(13,35,1),(13,32,1),(13,36,4),(13,47,4),

-- deal_id 14: BBQ Party A
(14,34,2),(14,33,2),(14,41,6),(14,48,3),(14,46,3),

-- deal_id 15: BBQ Party B
(15,32,3),(15,31,1),(15,42,6),(15,49,4),(15,47,3),

-- deal_id 16: Desi Solo
(16,23,1),(16,40,1),(16,45,1),

-- deal_id 17: Desi Duo
(17,27,2),(17,44,2),(17,28,2),

-- deal_id 18: Desi Squad A
(18,29,2),(18,25,4),(18,38,4),

-- deal_id 19: Desi Squad B
(19,21,1),(19,22,1),(19,26,1),(19,37,4),

-- deal_id 20: Desi Party
(20,30,2),(20,22,1),(20,47,3),(20,36,3),(20,38,3),(20,49,3);


---------------------------
-- adding menu item cheff
---------------------------

-- For BBQ chefs
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Ali Khan')
FROM menu_item
WHERE item_cuisine = 'BBQ';

INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Shah Ali')
FROM menu_item
WHERE item_cuisine = 'BBQ';

-- For Desi chefs
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Imran Qureshi')
FROM menu_item
WHERE item_cuisine = 'Desi' AND item_category <> 'bread';

INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Fatima Noor')
FROM menu_item
WHERE item_cuisine = 'Desi' AND item_category <> 'bread';

-- For Fast Food chefs
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'abdul mateen')
FROM menu_item
WHERE item_cuisine = 'Fast Food';

INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'akbar ahmed')
FROM menu_item
WHERE item_cuisine = 'Fast Food';

-- For Chinese chefs
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'esha khurram')
FROM menu_item
WHERE item_cuisine = 'Chinese';

INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'abid Ali')
FROM menu_item
WHERE item_cuisine = 'Chinese';

-- For Breads specialist
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Rashid Khan')
FROM menu_item
WHERE item_category = 'bread';

-- For Drinks specialist
INSERT INTO menu_item_chefs (menu_item_id, chef_id)
SELECT item_id, (SELECT cheff_id FROM chef WHERE cheff_name = 'Fazal Haq')
FROM menu_item
WHERE item_category = 'drink';


select * from cart_items
select * from cart
select * from orders