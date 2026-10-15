# Smart Campus Resource and Room Booking System

A local Streamlit application for browsing campus rooms and equipment, submitting
reservations, preventing approved-slot conflicts, and managing administrator
approvals.

## Features

- Register and sign in with a student, professor, or researcher account.
- Passwords are stored as salted PBKDF2 hashes, never as plaintext.
- Users can create, view, edit, and delete their own pending bookings. Approved
  bookings can be cancelled.
- Administrators can approve or reject bookings and create, edit, and delete
  resources. Resource deletion is blocked while booking history references it.
- Booking and resource data is stored in the local `campus_booking.db` SQLite
  database. Existing booking databases are migrated on startup.
- Set `CAMPUS_BOOKING_DB` to use a different SQLite file; by default the database
  is created next to `app.py`.

## Setup

Requires Python 3.10 or newer. The startup scripts create a virtual environment,
install requirements, and launch Streamlit:

```bash
./run.sh
```

Windows:

```bat
run.bat
```

## First administrator

Regular accounts can be registered from the app. Administrator accounts cannot
be self-registered. Edit the local `.env` file and set the administrator
credentials before the first launch. See `.env.example` for the variable names:

```bash
# Edit .env and set CAMPUS_ADMIN_EMAIL and CAMPUS_ADMIN_PASSWORD.
./run.sh
```

You can also provide these as environment variables; environment variables take
precedence over values in `.env`. The real `.env` file is ignored by Git. Keep
your credentials private and use a unique password of at least 12 characters.
The configured email is created as an administrator on first startup; if a
regular account with that email already exists, it is promoted during
provisioning. Changing the environment variables later does not reset an
existing administrator password.
