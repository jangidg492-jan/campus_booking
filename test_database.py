import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from database import (
    authenticate_user,
    create_booking,
    database,
    delete_own_booking,
    init_db,
    register_user,
    update_booking,
)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_name = os.path.join(self.temp_dir.name, "test.db")
        self.env = patch.dict(
            os.environ,
            {"CAMPUS_ADMIN_EMAIL": "", "CAMPUS_ADMIN_PASSWORD": ""},
        )
        self.env.start()
        init_db(self.db_name)
        self.user = register_user(
            "Test User",
            "test@example.edu",
            "Student",
            "correct-horse-battery",
            self.db_name,
        )

    def tearDown(self):
        self.env.stop()
        self.temp_dir.cleanup()

    def test_registration_hashes_password_and_authenticates(self):
        with database(self.db_name) as conn:
            stored_hash = conn.execute(
                "SELECT password_hash FROM users WHERE id = ?", (self.user["id"],)
            ).fetchone()[0]
        self.assertNotEqual(stored_hash, "correct-horse-battery")
        self.assertIsNotNone(authenticate_user("TEST@example.edu", "correct-horse-battery", self.db_name))
        self.assertIsNone(authenticate_user("test@example.edu", "wrong-password", self.db_name))

    def test_registration_rejects_duplicate_email_and_short_password(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            register_user(
                "Duplicate User",
                "TEST@example.edu",
                "Student",
                "correct-horse-battery",
                self.db_name,
            )
        with self.assertRaisesRegex(ValueError, "12 characters"):
            register_user("New User", "new@example.edu", "Student", "short", self.db_name)

    def test_user_can_create_update_and_delete_own_pending_booking(self):
        with database(self.db_name) as conn:
            resource_id = conn.execute("SELECT id FROM resources LIMIT 1").fetchone()[0]

        create_booking(
            self.user, resource_id, "2099-06-01", "09:00", "10:00", self.db_name
        )
        with database(self.db_name) as conn:
            booking_id = conn.execute(
                "SELECT id FROM bookings WHERE user_id = ?", (self.user["id"],)
            ).fetchone()[0]

        update_booking(
            self.user["id"],
            booking_id,
            resource_id,
            "2099-06-02",
            "10:00",
            "11:00",
            self.db_name,
        )
        with database(self.db_name) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT booking_date FROM bookings WHERE id = ?", (booking_id,)
                ).fetchone()[0],
                "2099-06-02",
            )
        delete_own_booking(self.user["id"], booking_id, self.db_name)
        with database(self.db_name) as conn:
            self.assertIsNone(
                conn.execute("SELECT id FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            )

    def test_users_cannot_edit_or_delete_another_users_booking(self):
        other_user = register_user(
            "Other User",
            "other@example.edu",
            "Student",
            "another-correct-password",
            self.db_name,
        )
        with database(self.db_name) as conn:
            resource_id = conn.execute("SELECT id FROM resources LIMIT 1").fetchone()[0]
        create_booking(
            self.user, resource_id, "2099-06-01", "09:00", "10:00", self.db_name
        )
        with database(self.db_name) as conn:
            booking_id = conn.execute(
                "SELECT id FROM bookings WHERE user_id = ?", (self.user["id"],)
            ).fetchone()[0]

        with self.assertRaisesRegex(ValueError, "Only your pending bookings"):
            update_booking(
                other_user["id"],
                booking_id,
                resource_id,
                "2099-06-02",
                "10:00",
                "11:00",
                self.db_name,
            )
        with self.assertRaisesRegex(ValueError, "Only your pending bookings"):
            delete_own_booking(other_user["id"], booking_id, self.db_name)

    def test_booking_conflict_is_checked_when_creating(self):
        with database(self.db_name) as conn:
            resource_id = conn.execute("SELECT id FROM resources LIMIT 1").fetchone()[0]
            conn.execute(
                """
                INSERT INTO bookings
                    (resource_id, user_name, user_role, booking_date, start_time, end_time, status)
                VALUES (?, 'Other User', 'Student', '2099-06-01', '09:00', '10:00', 'APPROVED')
                """,
                (resource_id,),
            )
        with self.assertRaisesRegex(ValueError, "conflicts"):
            create_booking(
                self.user, resource_id, "2099-06-01", "09:30", "10:30", self.db_name
            )

    def test_existing_booking_database_is_migrated_without_losing_records(self):
        legacy_db = os.path.join(self.temp_dir.name, "legacy.db")
        conn = sqlite3.connect(legacy_db)
        conn.executescript(
            """
            CREATE TABLE resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                capacity INTEGER,
                specs TEXT,
                guidelines TEXT
            );
            INSERT INTO resources (name, type) VALUES ('Legacy room', 'Room');
            CREATE TABLE bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resource_id INTEGER,
                user_name TEXT,
                user_role TEXT,
                booking_date TEXT,
                start_time TEXT,
                end_time TEXT,
                status TEXT DEFAULT 'PENDING',
                admin_notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO bookings
                (resource_id, user_name, user_role, booking_date, start_time, end_time)
            VALUES (1, 'Legacy user', 'Student', '2099-06-01', '09:00', '10:00');
            """
        )
        conn.commit()
        conn.close()

        init_db(legacy_db)
        with database(legacy_db) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(bookings)")}
            legacy_booking = conn.execute(
                "SELECT user_name, user_id FROM bookings WHERE id = 1"
            ).fetchone()
        self.assertIn("user_id", columns)
        self.assertEqual(legacy_booking["user_name"], "Legacy user")
        self.assertIsNone(legacy_booking["user_id"])

    def test_deleted_resources_are_not_reseeded_on_next_startup(self):
        with database(self.db_name) as conn:
            conn.execute("DELETE FROM resources")
        init_db(self.db_name)
        with database(self.db_name) as conn:
            resource_count = conn.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        self.assertEqual(resource_count, 0)

    def test_admin_is_provisioned_from_environment(self):
        admin_db = os.path.join(self.temp_dir.name, "admin.db")
        with patch.dict(
            os.environ,
            {
                "CAMPUS_ADMIN_EMAIL": "admin@example.edu",
                "CAMPUS_ADMIN_PASSWORD": "a-unique-admin-password",
            },
        ):
            init_db(admin_db)
        admin = authenticate_user(
            "admin@example.edu", "a-unique-admin-password", admin_db
        )
        self.assertEqual(admin["role"], "ADMIN")
        with self.assertRaises(ValueError):
            register_user(
                "Unsafe Admin",
                "unsafe@example.edu",
                "Administrator",
                "correct-horse-battery",
                admin_db,
            )


if __name__ == "__main__":
    unittest.main()
