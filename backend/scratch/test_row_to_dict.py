import dataclasses
from typing import Any

class MockModel:
    def __init__(self, id):
        self.id = id
    def model_dump(self):
        return {"id": self.id, "full_name": "Test User"}

class MockRow:
    def __init__(self, items):
        self.items = items
    def __getitem__(self, i):
        return self.items[i]
    def _asdict(self):
        return {"id": self.items[0], "name": "Extra"}

def _row_to_dict(row: Any, model_class) -> Any:
    data = {}
    if isinstance(row, model_class):
        data = row.model_dump()
    elif hasattr(row, "_asdict"): # SQLAlchemy Row
        # This is the current buggy logic
        try:
            data = row[0].model_dump()
            data.update(row._asdict())
        except Exception as e:
            print(f"Error in Row processing: {e}")
            return row
    elif isinstance(row, tuple):
        try:
            data = row[0].model_dump()
        except Exception as e:
            print(f"Error in tuple processing: {e}")
            return row
    else:
        return row
    return data

# Test case 1: Row with Model (Relations used)
user = MockModel(1)
row = MockRow([user, "DeptName"])
d = _row_to_dict(row, MockModel)
print(f"Relations Result: {d}")

# Test case 2: Row with Scalars (select_fields used)
row2 = MockRow([1, "admin"])
d2 = _row_to_dict(row2, MockModel)
print(f"SelectFields Result: {d2}")

# Simulation of UserAdminService
def user_service_row_to_dict(row):
    data = _row_to_dict(row, MockModel)
    print(f"Data type: {type(data)}")
    try:
        return data.get("full_name", "")
    except Exception as e:
        print(f"Service Error: {e}")

print("\nRunning Service Test with SelectFields...")
user_service_row_to_dict(row2)
