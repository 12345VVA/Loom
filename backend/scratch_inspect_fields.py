from sqlmodel import Field, SQLModel
from typing import Optional

class TestModel(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=20, min_length=2, pattern="^[a-zA-Z]+$")
    age: int = Field(ge=0, le=150)

field = TestModel.model_fields['name']
print(f"Name metadata: {field.metadata}")
for m in field.metadata:
    print(f"Type: {type(m)}, Values: {vars(m) if hasattr(m, '__dict__') else m}")

age_field = TestModel.model_fields['age']
print(f"Age metadata: {age_field.metadata}")
