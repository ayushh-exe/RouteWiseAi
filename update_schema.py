import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASE_URL = DATABASE_URL.strip()
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def update_schema():
    with engine.connect() as connection:
        print("Adding profile columns to users table if they don't exist...")
        
        # We can try to add each column and catch errors if it already exists,
        # or use DO Block in postgres to handle it conditionally.
        sql = """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='age') THEN
                ALTER TABLE users ADD COLUMN age VARCHAR(10);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='gender') THEN
                ALTER TABLE users ADD COLUMN gender VARCHAR(20);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='nationality') THEN
                ALTER TABLE users ADD COLUMN nationality VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='license') THEN
                ALTER TABLE users ADD COLUMN license VARCHAR(50);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='address') THEN
                ALTER TABLE users ADD COLUMN address TEXT;
            END IF;
        END $$;
        """
        
        connection.execute(text(sql))
        connection.commit()
        print("Schema update complete.")

if __name__ == "__main__":
    update_schema()
