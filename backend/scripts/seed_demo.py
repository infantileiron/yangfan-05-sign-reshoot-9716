import json

from sqlalchemy import func, select

from migrations.bootstrap import migrate
from src.business.demo import demo_rows
from src.business.profile import PROFILE
from src.config.settings import Session, engine
from src.constants.workflow import Role
from src.models.account import Account
from src.models.night import Night
from src.services.datasets import save_in
from src.utils.csv_data import parse_csv, render_csv
from src.utils.passwords import hash_password

PASSWORD = "Yangfan-demo-2026"
NIGHT_KEY = PROFILE["seed_night"]["key"]
NIGHT_NAME = PROFILE["seed_night"]["name"]
NIGHT_CAPACITY = PROFILE["seed_night"]["capacity"]


def seed():
    columns = PROFILE["columns"]
    rows = parse_csv(render_csv(demo_rows(), [column["key"] for column in columns]), columns)
    with Session.begin() as db:
        for role in Role:
            email = f"{role.value}@demo.local"
            if db.get(Account, email) is None:
                db.add(Account(email=email, role=role.value, password_hash=hash_password(PASSWORD)))
        db.flush()
        night = db.scalar(select(Night).where(Night.key == NIGHT_KEY))
        if night is None:
            night = Night(key=NIGHT_KEY, name=NIGHT_NAME, capacity=NIGHT_CAPACITY, author="seed")
            db.add(night)
        db.flush()
        item, created = save_in(db, PROFILE["seed_name"], rows, "seed", audit=False)
        return {
            "accounts": db.scalar(select(func.count()).select_from(Account)),
            "nights": db.scalar(select(func.count()).select_from(Night)),
            "night": {"id": night.id, "capacity": night.capacity},
            "rows": len(item.rows), "checksum": item.checksum, "created": created,
        }


if __name__ == "__main__":
    migrate(engine)
    print(json.dumps(seed(), ensure_ascii=False))
