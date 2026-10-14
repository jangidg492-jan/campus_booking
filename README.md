# Smart Campus Resource & Room Booking System

Ek lightweight, self-contained desktop web application jo campus ke rooms aur gear booking ko streamline karta hai, schedule conflicts aur double-booking actively rokta hai.

---

## 📌 Project Overview
Campus mein study rooms, auditoriums aur lab gear book karte waqt aksar double-booking aur schedule clashes hote hain. Yeh system auto-conflict detection logic provide karta hai jisse:
- Duplicate reservations block hoti hain.
- Students/Faculty resources easily browse aur book kar sakte hain.
- Administrators requests ko review, approve ya reject kar sakte hain.

---

## 🚀 Key Features
- **Resource Directory:** Rooms (jaise Seminar Hall) aur gear (jaise GPU servers) ki capacity, specs aur rules ka clear catalog.
- **Conflict Prevention Engine:** Real-time checking system jo identical time-slot par multiple bookings ko block karta hai.
- **Approval Workflow:** Admin dashboard jahan pending requests ko accept/reject kiya ja sake with custom notes.
- **Personal Dashboard:** Students apne past aur upcoming reservations ka status dekh sakte hain aur cancel kar sakte hain.
- **Zero Cloud Dependency:** Data securely local SQLite database mein store hota hai bina kisi external cloud service ke.

---

## 🛠️ Tech Stack
- **Language:** Python 3.10+
- **Frontend / UI:** Streamlit[cite: 1]
- **Database:** SQLite3 (Local file-based storage)[cite: 1]

---

## ⚙️ Installation & Local Setup

### Prerequisites
Make sure Python 3.10 ya usse higher version installed ho:
```bash
python3 --version
# campus_booking
