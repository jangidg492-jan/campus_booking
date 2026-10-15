import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))

DB_NAME = Path(
    os.environ.get("CAMPUS_BOOKING_DB", Path(__file__).with_name("campus_booking.db"))
)
PASSWORD_ITERATIONS = 600_000


def get_connection(db_name=DB_NAME):
    conn = sqlite3.connect(db_name, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def database(db_name=DB_NAME, *, immediate=False):
    conn = get_connection(db_name)
    try:
        if immediate:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, password_hash):
    try:
        algorithm, iterations, salt_hex, digest_hex = password_hash.split("$")
        if (
            algorithm != "pbkdf2_sha256"
            or int(iterations) != PASSWORD_ITERATIONS
            or len(salt_hex) != 32
            or len(digest_hex) != 64
        ):
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            PASSWORD_ITERATIONS,
        )
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def init_db(db_name=DB_NAME):
    with database(db_name) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                user_role TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'USER',
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                capacity INTEGER,
                specs TEXT,
                guidelines TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id INTEGER,
                user_name TEXT,
                user_role TEXT,
                booking_date TEXT,
                start_time TEXT,
                end_time TEXT,
                status TEXT DEFAULT 'PENDING',
                admin_notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (resource_id) REFERENCES resources(id)
            )
        """)
        booking_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()
        }
        if "user_id" not in booking_columns:
            conn.execute(
                "ALTER TABLE bookings ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )

        seeded = conn.execute(
            "SELECT 1 FROM app_metadata WHERE key = 'default_resources_seeded'"
        ).fetchone()
        if seeded is None:
            resource_count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
            if resource_count == 0:
                conn.executemany(
                    """
                    INSERT INTO resources (name, type, capacity, specs, guidelines)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        ("Seminar Hall A", "Room", 120, "Projector, Surround Audio, AC", "Keep noise moderate after 7 PM."),
                        ("Conference Room 2", "Room", 15, "Smart Display, Polycom, Whiteboard", "Clean whiteboard after use."),
                        ("GPU Workstation Cluster", "Hardware", 1, "4x NVIDIA RTX 4090, 128GB RAM", "Do not interrupt long compute tasks."),
                        ("IoT Lab Hardware Kit 1", "Hardware", 4, "Raspberry Pi 4, Arduino, Sensor pack", "Return all component bags intact."),
                    ],
                )
            conn.execute(
                "INSERT INTO app_metadata (key, value) VALUES ('default_resources_seeded', '1')"
            )

        admin_email = os.environ.get("CAMPUS_ADMIN_EMAIL", "").strip().lower()
        admin_password = os.environ.get("CAMPUS_ADMIN_PASSWORD", "")
        if bool(admin_email) != bool(admin_password):
            raise ValueError(
                "Set both CAMPUS_ADMIN_EMAIL and CAMPUS_ADMIN_PASSWORD to provision an administrator."
            )
        if admin_email:
            if "@" not in admin_email or "." not in admin_email.rsplit("@", 1)[-1]:
                raise ValueError("CAMPUS_ADMIN_EMAIL must be a valid email address.")
            if len(admin_password) < 12:
                raise ValueError(
                    "CAMPUS_ADMIN_PASSWORD must contain at least 12 characters."
                )
            admin = conn.execute(
                "SELECT id, role FROM users WHERE email = ?", (admin_email,)
            ).fetchone()
            if admin is None:
                conn.execute(
                    """
                    INSERT INTO users (name, email, user_role, role, password_hash)
                    VALUES ('Campus Administrator', ?, 'Administrator', 'ADMIN', ?)
                    """,
                    (admin_email, hash_password(admin_password)),
                )
            elif admin["role"] != "ADMIN":
                conn.execute(
                    """
                    UPDATE users
                    SET role = 'ADMIN', user_role = 'Administrator', password_hash = ?
                    WHERE id = ?
                    """,
                    (hash_password(admin_password), admin["id"]),
                )


def register_user(name, email, user_role, password, db_name=DB_NAME):
    name = name.strip()
    email = email.strip().lower()
    if not name:
        raise ValueError("Enter your full name.")
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise ValueError("Enter a valid email address.")
    if user_role not in {"Student", "Professor", "Researcher"}:
        raise ValueError("Choose a valid campus role.")
    if len(password) < 12:
        raise ValueError("Use a password with at least 12 characters.")

    try:
        with database(db_name) as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (name, email, user_role, password_hash)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, user_role, hash_password(password)),
            )
            user = conn.execute(
                "SELECT id, name, email, user_role, role FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise ValueError("An account with that email already exists.") from exc
    return dict(user)


def authenticate_user(email, password, db_name=DB_NAME):
    with database(db_name) as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
    if user is None:
        hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes(16), PASSWORD_ITERATIONS
        )
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "user_role": user["user_role"],
        "role": user["role"],
    }


def booking_conflicts(conn, resource_id, booking_date, start_time, end_time, exclude_id=None):
    query = """
        SELECT 1 FROM bookings
        WHERE resource_id = ?
          AND booking_date = ?
          AND status = 'APPROVED'
          AND start_time < ?
          AND end_time > ?
    """
    params = [resource_id, booking_date, end_time, start_time]
    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)
    return conn.execute(query, params).fetchone() is not None


def create_booking(user, resource_id, booking_date, start_time, end_time, db_name=DB_NAME):
    with database(db_name, immediate=True) as conn:
        if (
            conn.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,)).fetchone()
            is None
        ):
            raise ValueError("This resource is no longer available.")
        if booking_conflicts(conn, resource_id, booking_date, start_time, end_time):
            raise ValueError("That time slot conflicts with an approved booking.")
        conn.execute(
            """
            INSERT INTO bookings
                (resource_id, user_id, user_name, user_role, booking_date, start_time, end_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_id,
                user["id"],
                user["name"],
                user["user_role"],
                booking_date,
                start_time,
                end_time,
            ),
        )


def update_booking(user_id, booking_id, resource_id, booking_date, start_time, end_time, db_name=DB_NAME):
    with database(db_name, immediate=True) as conn:
        if (
            conn.execute("SELECT 1 FROM resources WHERE id = ?", (resource_id,)).fetchone()
            is None
        ):
            raise ValueError("This resource is no longer available.")
        if booking_conflicts(
            conn, resource_id, booking_date, start_time, end_time, exclude_id=booking_id
        ):
            raise ValueError("That time slot conflicts with an approved booking.")
        cursor = conn.execute(
            """
            UPDATE bookings
            SET resource_id = ?, booking_date = ?, start_time = ?, end_time = ?
            WHERE id = ? AND user_id = ? AND status = 'PENDING'
            """,
            (resource_id, booking_date, start_time, end_time, booking_id, user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Only your pending bookings can be edited.")


def delete_own_booking(user_id, booking_id, db_name=DB_NAME):
    with database(db_name) as conn:
        cursor = conn.execute(
            "DELETE FROM bookings WHERE id = ? AND user_id = ? AND status = 'PENDING'",
            (booking_id, user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("Only your pending bookings can be deleted.")


def approve_booking(booking_id, admin_note, db_name=DB_NAME):
    with database(db_name, immediate=True) as conn:
        booking = conn.execute(
            """
            SELECT resource_id, booking_date, start_time, end_time
            FROM bookings WHERE id = ? AND status = 'PENDING'
            """,
            (booking_id,),
        ).fetchone()
        if booking is None:
            raise ValueError("This pending booking no longer exists.")
        if booking_conflicts(
            conn,
            booking["resource_id"],
            booking["booking_date"],
            booking["start_time"],
            booking["end_time"],
        ):
            raise ValueError("An approved booking now clashes with this time slot.")
        conn.execute(
            "UPDATE bookings SET status = 'APPROVED', admin_notes = ? WHERE id = ?",
            (admin_note, booking_id),
        )
