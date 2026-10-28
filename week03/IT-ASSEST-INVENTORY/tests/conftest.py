from datetime import date
from decimal import Decimal

import pytest

from app import create_app
from app.auth.routes import hash_password
from app.extensions import db
from app.models import Asset, AssetModel, Category, Employee, Location, Manufacturer, Role, User
from config import TestConfig

PASSWORD = "correct-horse-battery"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def data(app):
    loc = Location(name="Berlin HQ", city="Berlin")
    cat = Category(name="Laptop", default_useful_life_months=36, default_residual_pct=Decimal("10"))
    model = AssetModel(manufacturer=Manufacturer(name="Dell"), category=cat, name="Latitude 7450")
    admin = User(email="admin@test.example", full_name="Ada Admin", role=Role.ADMIN, password_hash=hash_password(PASSWORD))
    manager = User(email="mgr@test.example", full_name="Max Manager", role=Role.MANAGER, password_hash=hash_password(PASSWORD))
    emp = Employee(employee_code="E1", full_name="Erika Mustermann", email="erika@test.example", location=loc)
    asset = Asset(asset_tag="IT-000001", model=model, serial_number="DL123", location=loc,
                  purchase_date=date(2025, 1, 15), purchase_cost=Decimal("1200.00"))
    db.session.add_all([loc, cat, model, admin, manager, emp, asset])
    db.session.commit()
    return {"admin": admin, "manager": manager, "employee": emp, "asset": asset}


@pytest.fixture
def client(app, data):
    client = app.test_client()
    client.post("/login", data={"email": "mgr@test.example", "password": PASSWORD})
    return client
