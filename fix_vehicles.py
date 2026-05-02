import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL").strip().replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)

def fix_vehicles_schema():
    with engine.connect() as connection:
        print("Dropping and recreating vehicles table...")
        
        connection.execute(text("DROP TABLE IF EXISTS vehicles CASCADE;"))
        
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
        
        connection.commit()
        print("Vehicles table recreated successfully.")

if __name__ == "__main__":
    fix_vehicles_schema()
