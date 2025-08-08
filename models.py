from datetime import datetime

try:  # running via `python app.py`
    from __main__ import db  # type: ignore
except ImportError:  # pragma: no cover
    from app import db  # type: ignore


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def init_db():
    db.create_all()
