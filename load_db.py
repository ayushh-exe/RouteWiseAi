import json
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Get the database URL from the environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set. Please create a .env file.")

DATABASE_URL = DATABASE_URL.strip()

# SQLAlchemy 1.4+ requires "postgresql://" instead of "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def create_tables():
    """Creates all required tables in the database."""
    with engine.connect() as connection:
        # Drop existing tables to start fresh
        connection.execute(text("DROP TABLE IF EXISTS challans CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS vehicles CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS users CASCADE;"))
        connection.execute(text("DROP TABLE IF EXISTS transport_options CASCADE;"))

        # ---------- Create users table ----------
        connection.execute(text("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL
        );
        """))

        # ---------- Create vehicles table ----------
        connection.execute(text("""
        CREATE TABLE vehicles (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            vehicle_type VARCHAR(20) NOT NULL,
            license_plate VARCHAR(50),
            model VARCHAR(100),
            color VARCHAR(50),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """))

        # ---------- Create challans table ----------
        connection.execute(text("""
        CREATE TABLE challans (
            id SERIAL PRIMARY KEY,
            challan_number VARCHAR(50) UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            status VARCHAR(50),
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE
        );
        """))

        # ---------- Create transport_options table ----------
        connection.execute(text("""
        CREATE TABLE transport_options (
            id SERIAL PRIMARY KEY,
            transport_type VARCHAR(10) NOT NULL,
            origin_city VARCHAR(100) NOT NULL,
            destination_city VARCHAR(100) NOT NULL,
            operator_name VARCHAR(100),
            departure_time VARCHAR(50),
            arrival_time VARCHAR(50),
            duration VARCHAR(50),
            fare INTEGER,
            seats_available INTEGER,
            details JSONB
        );
        """))

        connection.commit()

    print("✅ Tables 'users', 'vehicles', 'challans', and 'transport_options' created successfully.")


def insert_data(file_path, transport_type):
    """Reads a JSON dataset and inserts the data into the transport_options table."""
    if not os.path.exists(file_path):
        print(f"⚠️ Warning: Data file not found at {file_path}. Skipping.")
        return
        
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    records = []
    for route in data.get('routes', []):
        origin = route.get('from')
        destination = route.get('to')

        for operator in route.get('operators', []):
            operator_name = operator.get('airline') or operator.get('operator') or 'N/A'
            departures = operator.get('departures', [operator])

            for dep in departures:
                fare = dep.get('fare')
                if not fare:
                    continue

                details_dict = {
                    "bus_type": operator.get("bus_type"),
                    "train_class": operator.get("train_class"),
                    "cabin_class": operator.get("cabin_class"),
                    "operator_type": operator.get("operator_type"),
                    "distance_km_est": operator.get("distance_km_est")
                }
                details_json_string = json.dumps({k: v for k, v in details_dict.items() if v is not None})

                records.append({
                    "tt": transport_type,
                    "origin": origin,
                    "dest": destination,
                    "op_name": operator_name,
                    "dep_time": dep.get('departure'),
                    "arr_time": dep.get('arrival'),
                    "dur": dep.get('duration'),
                    "fare": int(fare),
                    "seats": dep.get('seats_available'),
                    "details": details_json_string
                })

    if records:
        with engine.connect() as connection:
            raw_conn = connection.connection
            # If using SQLAlchemy 2.0 with a wrapper, we might need driver_connection
            if hasattr(raw_conn, 'driver_connection'):
                raw_conn = raw_conn.driver_connection
            cursor = raw_conn.cursor()
            from psycopg2.extras import execute_values
            
            insert_query = """
            INSERT INTO transport_options (
                transport_type, origin_city, destination_city, operator_name,
                departure_time, arrival_time, duration, fare, seats_available, details
            ) VALUES %s
            """
            
            values = [(r['tt'], r['origin'], r['dest'], r['op_name'], r['dep_time'], r['arr_time'], r['dur'], r['fare'], r['seats'], r['details']) for r in records]
            
            # Execute values sends everything in one giant query
            template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSONB))"
            execute_values(cursor, insert_query, values, template=template)
            raw_conn.commit()

    print(f"✅ Successfully inserted {len(records)} records from {file_path}")


if __name__ == "__main__":
    create_tables()
    insert_data('flight_dataset_india.json', 'flight')
    insert_data('train_dataset_india.json', 'train')
    insert_data('bus_dataset_india.json', 'bus')
    print("🚀 Database population complete!")