import os
import sqlite3
import sys

# Build every path from this file's location, so the script works no matter which folder it's run from
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "restaurant.db")
SCHEMA_FILE = os.path.join(BASE_DIR, "schema.sql")
SEED_FILE = os.path.join(BASE_DIR, "seed.sql")

# Refuse to run on an existing database: the CREATE TABLE statements would fail,
# and deleting it automatically could wipe out orders that matter
if os.path.exists(DATABASE):
    print("restaurant.db already exists. Delete it first if you want to rebuild it from scratch.")
    sys.exit(1)

conn = sqlite3.connect(DATABASE)

# Create the tables, then fill in the menu items and prices
with open(SCHEMA_FILE) as f:
    conn.executescript(f.read())
with open(SEED_FILE) as f:
    conn.executescript(f.read())

conn.commit()
conn.close()

print("Created restaurant.db with the menu data.")
