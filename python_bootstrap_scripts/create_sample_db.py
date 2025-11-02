#!/usr/bin/env python3
"""Create a sample DuckDB database for testing Cataloger.

This script creates a realistic e-commerce database with:
- Users table (customer data)
- Products table (inventory)
- Orders table (transactions)
- Order items table (line items)

The data includes realistic patterns for the cataloging agent to discover:
- Null values in various columns
- Categorical distributions
- Temporal patterns
- Data quality issues
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb


def create_database(db_path: str = "data/sample_ecommerce.duckdb"):
    """Create and populate a sample e-commerce database."""

    # Ensure data directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Delete existing database if it exists
    db_file = Path(db_path)
    if db_file.exists():
        print(f"Removing existing database at: {db_path}")
        db_file.unlink()

    print(f"Creating database at: {db_path}")
    conn = duckdb.connect(db_path)

    # Create tables
    print("Creating tables...")
    create_users_table(conn)
    create_products_table(conn)
    create_orders_table(conn)
    create_order_items_table(conn)

    # Populate with sample data
    print("Populating users...")
    populate_users(conn, num_users=1000)

    print("Populating products...")
    populate_products(conn, num_products=200)

    print("Populating orders...")
    populate_orders(conn, num_orders=3000)

    print("Populating order items...")
    populate_order_items(conn)

    # Print summary
    print("\n" + "=" * 50)
    print("Database created successfully!")
    print("=" * 50)

    for table in ["users", "products", "orders", "order_items"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:15} {count:>6,} rows")

    print(f"\nDatabase location: {db_path}")
    print(f"Connection string: duckdb:///{db_path}")

    conn.close()


def create_users_table(conn):
    """Create users table with realistic schema."""
    conn.execute("""
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            email VARCHAR,
            first_name VARCHAR,
            last_name VARCHAR,
            phone VARCHAR,
            country VARCHAR,
            state VARCHAR,
            city VARCHAR,
            signup_date DATE,
            is_active BOOLEAN,
            total_orders INTEGER,
            total_spent DECIMAL(10,2)
        )
    """)


def create_products_table(conn):
    """Create products table."""
    conn.execute("""
        CREATE TABLE products (
            product_id INTEGER PRIMARY KEY,
            name VARCHAR,
            category VARCHAR,
            subcategory VARCHAR,
            price DECIMAL(10,2),
            cost DECIMAL(10,2),
            stock_quantity INTEGER,
            supplier VARCHAR,
            created_at TIMESTAMP
        )
    """)


def create_orders_table(conn):
    """Create orders table."""
    conn.execute("""
        CREATE TABLE orders (
            order_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            order_date TIMESTAMP,
            status VARCHAR,
            total_amount DECIMAL(10,2),
            shipping_address VARCHAR,
            payment_method VARCHAR,
            discount_code VARCHAR,
            shipped_date TIMESTAMP,
            delivered_date TIMESTAMP
        )
    """)


def create_order_items_table(conn):
    """Create order items table."""
    conn.execute("""
        CREATE TABLE order_items (
            order_item_id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price DECIMAL(10,2),
            discount DECIMAL(10,2)
        )
    """)


def populate_users(conn, num_users: int):
    """Populate users table with realistic data."""
    first_names = [
        "John",
        "Jane",
        "Michael",
        "Emily",
        "David",
        "Sarah",
        "Chris",
        "Lisa",
        "James",
        "Emma",
        "Robert",
        "Olivia",
        "William",
        "Ava",
        "Richard",
    ]
    last_names = [
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
        "Rodriguez",
        "Martinez",
        "Hernandez",
        "Lopez",
        "Wilson",
    ]
    countries = ["USA", "Canada", "UK", "Germany", "France", "Australia"]
    us_states = ["CA", "NY", "TX", "FL", "IL", "PA", "OH", "GA", "NC", "MI"]
    cities = [
        "New York",
        "Los Angeles",
        "Chicago",
        "Houston",
        "Phoenix",
        "Philadelphia",
        "San Antonio",
        "San Diego",
        "Dallas",
        "San Jose",
    ]

    users = []
    start_date = datetime(2020, 1, 1)

    for i in range(1, num_users + 1):
        first = random.choice(first_names)
        last = random.choice(last_names)

        # Some users have no email (data quality issue)
        email = (
            f"{first.lower()}.{last.lower()}{i}@example.com"
            if random.random() > 0.05
            else None
        )

        # Some users have no phone
        phone = (
            f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}"
            if random.random() > 0.1
            else None
        )

        country = random.choice(countries)
        state = random.choice(us_states) if country == "USA" else None
        city = random.choice(cities) if random.random() > 0.05 else None

        signup_days = random.randint(0, 1500)
        signup_date = start_date + timedelta(days=signup_days)

        is_active = random.random() > 0.15  # 85% active
        total_orders = random.randint(0, 50) if is_active else random.randint(0, 5)
        total_spent = round(random.uniform(0, 5000), 2) if total_orders > 0 else 0.0

        users.append(
            (
                i,
                email,
                first,
                last,
                phone,
                country,
                state,
                city,
                signup_date,
                is_active,
                total_orders,
                total_spent,
            )
        )

    conn.executemany(
        """
        INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        users,
    )


def populate_products(conn, num_products: int):
    """Populate products table with realistic data."""
    categories = {
        "Electronics": ["Laptops", "Phones", "Tablets", "Accessories"],
        "Clothing": ["Men", "Women", "Kids", "Shoes"],
        "Home": ["Furniture", "Decor", "Kitchen", "Bedding"],
        "Books": ["Fiction", "Non-Fiction", "Educational", "Comics"],
        "Sports": ["Equipment", "Apparel", "Outdoor", "Fitness"],
    }

    suppliers = [
        "Acme Corp",
        "Global Supply Co",
        "Prime Vendors",
        "Wholesale Direct",
        "Quality Goods Inc",
        "Budget Suppliers",
    ]

    products = []
    start_date = datetime(2019, 1, 1)

    for i in range(1, num_products + 1):
        category = random.choice(list(categories.keys()))
        subcategory = random.choice(categories[category])

        name = f"{subcategory} Product {i}"
        price = round(random.uniform(9.99, 999.99), 2)
        cost = round(price * random.uniform(0.4, 0.7), 2)

        # Some products out of stock
        stock_quantity = random.randint(0, 500)

        # Some products have no supplier (data quality issue)
        supplier = random.choice(suppliers) if random.random() > 0.05 else None

        created_days = random.randint(0, 1800)
        created_at = start_date + timedelta(days=created_days)

        products.append(
            (
                i,
                name,
                category,
                subcategory,
                price,
                cost,
                stock_quantity,
                supplier,
                created_at,
            )
        )

    conn.executemany(
        """
        INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        products,
    )


def populate_orders(conn, num_orders: int):
    """Populate orders table with realistic data."""
    statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
    status_weights = [0.05, 0.10, 0.15, 0.60, 0.10]

    payment_methods = ["credit_card", "debit_card", "paypal", "apple_pay", "google_pay"]

    discount_codes = ["SAVE10", "WELCOME20", "FLASH15", None, None, None, None]

    orders = []
    start_date = datetime(2022, 1, 1)

    # Get user IDs
    user_ids = [
        row[0]
        for row in conn.execute(
            "SELECT user_id FROM users WHERE is_active = true"
        ).fetchall()
    ]

    for i in range(1, num_orders + 1):
        user_id = random.choice(user_ids)

        order_days = random.randint(0, 730)  # Last 2 years
        order_date = start_date + timedelta(days=order_days)

        status = random.choices(statuses, weights=status_weights)[0]

        total_amount = round(random.uniform(20, 1000), 2)

        # Shipping address sometimes missing (data quality)
        shipping_address = (
            f"{random.randint(100, 9999)} Main St, City, ST 12345"
            if random.random() > 0.02
            else None
        )

        payment_method = random.choice(payment_methods)
        discount_code = random.choice(discount_codes)

        # Shipped/delivered dates based on status
        shipped_date = None
        delivered_date = None

        if status in ["shipped", "delivered"]:
            shipped_date = order_date + timedelta(days=random.randint(1, 3))

            if status == "delivered":
                delivered_date = shipped_date + timedelta(days=random.randint(1, 7))

        orders.append(
            (
                i,
                user_id,
                order_date,
                status,
                total_amount,
                shipping_address,
                payment_method,
                discount_code,
                shipped_date,
                delivered_date,
            )
        )

    conn.executemany(
        """
        INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        orders,
    )


def populate_order_items(conn):
    """Populate order items based on orders."""
    # Get order IDs and product IDs
    order_ids = [
        row[0] for row in conn.execute("SELECT order_id FROM orders").fetchall()
    ]
    products = conn.execute("SELECT product_id, price FROM products").fetchall()

    order_items = []
    item_id = 1

    for order_id in order_ids:
        # Each order has 1-5 items
        num_items = random.randint(1, 5)
        order_products = random.sample(products, num_items)

        for product_id, price in order_products:
            quantity = random.randint(1, 3)
            unit_price = float(price)

            # Sometimes apply discount
            discount = (
                round(random.uniform(0, unit_price * 0.3), 2)
                if random.random() > 0.7
                else 0.0
            )

            order_items.append(
                (item_id, order_id, product_id, quantity, unit_price, discount)
            )
            item_id += 1

    conn.executemany(
        """
        INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?)
    """,
        order_items,
    )


if __name__ == "__main__":
    create_database()
