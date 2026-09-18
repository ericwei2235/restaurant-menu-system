INSERT INTO menu_items (item_number, name, description, category) VALUES ('002', 'Egg Rolls (2)', 'Crispy fried rolls with cabbage and pork', 'Appetizers');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '002'), NULL, 375);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('020', 'Wonton Soup', 'Pork-filled wontons in a savory broth', 'Soup');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '020'), 'Small', 425);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '020'), 'Large', 675);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('031', 'Vegetable Fried Rice', 'Wok-fried rice with mixed vegetables and egg', 'Fried Rice');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '031'), 'Small', 695);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '031'), 'Large', 995);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '031'), 'Extra Large', 1595);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('001', 'Shrimp Spring Roll (2)', 'Crispy fried rolls filled with shrimp and vegetables', 'Appetizers');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '001'), NULL, 350);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('005', 'Crab Rangoon (6)', 'Crispy fried wontons filled with cream cheese and imitation crab', 'Appetizers');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '005'), NULL, 695);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('009', 'Teriyaki Chicken (4)', 'Grilled chicken skewers glazed with teriyaki sauce', 'Appetizers');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '009'), NULL, 695);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('021', 'Egg Drop Soup', 'Silky egg ribbons in a light chicken broth', 'Soup');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '021'), 'Small', 425);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '021'), 'Large', 675);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('022', 'Hot and Sour Soup', 'Tofu, mushroom, and bamboo shoots in a spicy, tangy broth', 'Soup');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '022'), 'Small', 475);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '022'), 'Large', 695);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('032', 'Chicken Fried Rice', 'Wok-fried rice with diced chicken, egg, and scallion', 'Fried Rice');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '032'), 'Small', 695);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '032'), 'Large', 995);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '032'), 'Extra Large', 1595);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('034', 'Shrimp Fried Rice', 'Wok-fried rice with shrimp, egg, and scallion', 'Fried Rice');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '034'), 'Small', 695);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '034'), 'Large', 995);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '034'), 'Extra Large', 1595);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('050', 'Chicken Kow w. Vegetable', 'Sliced chicken sauteed with mixed vegetables', 'Poultry');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '050'), 'Small', 850);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '050'), 'Large', 1250);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('053', 'Kung Pao Chicken w/ Peanut', 'Diced chicken, peanuts, and chili peppers in a spicy sauce', 'Poultry');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '053'), 'Small', 850);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '053'), 'Large', 1250);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('056', 'Chicken w/ Broccoli', 'Sliced chicken sauteed with fresh broccoli', 'Poultry');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '056'), 'Small', 850);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '056'), 'Large', 1250);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('057', 'Sweet & Sour Chicken', 'Crispy chicken tossed in a sweet and tangy sauce', 'Poultry');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '057'), 'Small', 850);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '057'), 'Large', 1250);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('071', 'Mongolian Beef', 'Sliced beef sauteed with scallions in a savory sauce', 'Beef');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '071'), 'Small', 895);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '071'), 'Large', 1395);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('075', 'Beef w. Broccoli', 'Sliced beef sauteed with fresh broccoli', 'Beef');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '075'), 'Small', 895);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '075'), 'Large', 1395);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('078', 'Kung Pao Beef', 'Diced beef, peanuts, and chili peppers in a spicy sauce', 'Beef');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '078'), 'Small', 895);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '078'), 'Large', 1395);

INSERT INTO menu_items(item_number, name, description, category) VALUES ('079', 'Szechuan Beef', 'Sliced beef sauteed in a spicy Szechuan sauce', 'Beef');
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '079'), 'Small', 895);
INSERT INTO menu_item_prices(menu_item_id, size_label, price) VALUES ((SELECT id FROM menu_items WHERE item_number = '079'), 'Large', 1395);