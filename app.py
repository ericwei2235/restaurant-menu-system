from flask import Flask, render_template
import sqlite3




app = Flask(__name__)



def get_menu():

    menu = {}

    # Make the rows behave like dictionaries for easier use
    conn = sqlite3.connect("restaurant.db")
    conn.row_factory = sqlite3.Row
    # Join the menu_items with menu_item_prices
    cursor = conn.execute("SELECT m.name, m.description, m.category, p.size_label, p.price FROM menu_items m JOIN menu_item_prices p ON p.menu_item_id = m.id ORDER BY m.category, m.id")
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        # Creates a category with value of empty list if it doesn't exist already
        if row["category"] not in menu:
            menu[row["category"]] = []

        # Checks if the last item has the same name as the current row's item
        if menu[row["category"]] and menu[row["category"]][-1]["name"] == row["name"]:
            # If yes, just append a new dict containing this row item's size and price to the existing price list
            menu[row["category"]][-1]["prices"].append({"label": row["size_label"], "price": f"{row['price'] / 100:.2f}"})
        else:
            # Otherwise, create a new menu item entry using this row's info
            entry = {"name": row["name"], "description": row["description"], "prices": [{"label": row["size_label"], "price": f"{row['price'] / 100:.2f}"}]}
            menu[row["category"]].append(entry)

    return menu





@app.route("/")
def home():
    menu = get_menu()
    return render_template("menu.html", menu=menu)


if __name__ == "__main__":
    app.run(debug=True)