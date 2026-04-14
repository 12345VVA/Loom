import os
from sqlmodel import Session, select
from app.core.database import init_db, engine
from app.modules.base.model.sys import SysParam

def test_init():
    print("Initializing database...")
    init_db()
    print("Database initialized successfully.")
    
    with Session(engine) as session:
        print("Checking sys_param...")
        try:
            param = session.exec(select(SysParam).where(SysParam.key_name == "logKeep")).first()
            print(f"Success! Found param: {param.name if param else 'None'}")
        except Exception as e:
            print(f"Error checking sys_param: {e}")
            raise

if __name__ == "__main__":
    test_init()
