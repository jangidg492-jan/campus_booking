import streamlit as st
import sqlite3
from datetime import datetime, date, time

DB_NAME = "campus_booking.db"

# ----------------- DATABASE SETUP -----------------
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table for rooms and gear
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            capacity INTEGER,
            specs TEXT,
            guidelines TEXT
        )
    """)
    
    # Table for booking requests
    cursor.execute("""
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
    
    # Seed default resources if empty
    cursor.execute("SELECT COUNT(*) FROM resources")
    if cursor.fetchone()[0] == 0:
        sample_resources = [
            ("Seminar Hall A", "Room", 120, "Projector, Surround Audio, AC", "Keep noise moderate after 7 PM."),
            ("Conference Room 2", "Room", 15, "Smart Display, Polycom, Whiteboard", "Clean whiteboard after use."),
            ("GPU Workstation Cluster", "Hardware", 1, "4x NVIDIA RTX 4090, 128GB RAM", "Do not interrupt long compute tasks."),
            ("IoT Lab Hardware Kit 1", "Hardware", 4, "Raspberry Pi 4, Arduino, Sensor pack", "Return all component bags intact.")
        ]
        cursor.executemany(
            "INSERT INTO resources (name, type, capacity, specs, guidelines) VALUES (?, ?, ?, ?, ?)",
            sample_resources
        )
    
    conn.commit()
    conn.close()

# ----------------- CORE LOGIC -----------------
def check_overlap(resource_id, b_date, start_str, end_str):
    """
    Checks if a requested slot overlaps with an APPROVED booking.
    Overlap condition: (StartA < EndB) and (EndA > StartB)
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM bookings 
        WHERE resource_id = ? 
          AND booking_date = ? 
          AND status = 'APPROVED'
          AND (start_time < ? AND end_time > ?)
    """, (resource_id, b_date, end_str, start_str))
    conflict = cursor.fetchone()
    conn.close()
    return conflict is not None

# ----------------- UI SETUP -----------------
st.set_page_config(page_title="Smart Campus Resource Booking", layout="wide")
init_db()

# Top Sidebar Role Switcher
st.sidebar.title("Campus Portal")
role = st.sidebar.radio("Select Persona", ["Student / Faculty", "Campus Administrator"])

# ----------------- VIEW 1: STUDENT / FACULTY -----------------
if role == "Student / Faculty":
    st.title("Smart Campus Resource & Room Booking")
    tab1, tab2, tab3 = st.tabs(["Directory & Book Resource", "My Booking Dashboard", "Availability View"])

    with tab1:
        st.subheader("Bookable Spaces & Hardware")
        conn = get_connection()
        resources = conn.execute("SELECT * FROM resources").fetchall()
        conn.close()

        # Display Directory
        for res in resources:
            with st.expander(f"{res['name']} ({res['type']}) - Capacity: {res['capacity']}"):
                st.write(f"**Specs:** {res['specs']}")
                st.write(f"**Guidelines:** {res['guidelines']}")

        st.markdown("---")
        st.subheader("Submit a Reservation Request")
        
        with st.form("booking_form"):
            col1, col2 = st.columns(2)
            with col1:
                user_name = st.text_input("Your Full Name")
                user_role = st.selectbox("Role", ["Student", "Professor", "Researcher"])
                resource_options = {res['name']: res['id'] for res in resources}
                selected_res_name = st.selectbox("Select Resource", list(resource_options.keys()))
            
            with col2:
                booking_date = st.date_input("Booking Date", min_value=date.today())
                start_val = st.time_input("Start Time", time(9, 0))
                end_val = st.time_input("End Time", time(10, 0))
            
            submitted = st.form_submit_button("Submit Request")
            
            if submitted:
                if not user_name.strip():
                    st.error("Please enter your name.")
                elif start_val >= end_val:
                    st.error("End time must be after start time.")
                else:
                    res_id = resource_options[selected_res_name]
                    start_str = start_val.strftime("%H:%M")
                    end_str = end_val.strftime("%H:%M")
                    date_str = booking_date.strftime("%Y-%m-%d")

                    # Check collision
                    if check_overlap(res_id, date_str, start_str, end_str):
                        st.error("Conflict detected: That slot is already booked and approved for this resource.")
                    else:
                        conn = get_connection()
                        conn.execute("""
                            INSERT INTO bookings (resource_id, user_name, user_role, booking_date, start_time, end_time, status)
                            VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                        """, (res_id, user_name, user_role, date_str, start_str, end_str))
                        conn.commit()
                        conn.close()
                        st.success("Request submitted successfully! Waiting for administrator approval.")

    with tab2:
        st.subheader("Track Your Bookings")
        search_user = st.text_input("Filter by your Name:")
        if search_user:
            conn = get_connection()
            user_bookings = conn.execute("""
                SELECT b.id, r.name as resource_name, b.booking_date, b.start_time, b.end_time, b.status, b.admin_notes
                FROM bookings b
                JOIN resources r ON b.resource_id = r.id
                WHERE b.user_name LIKE ?
                ORDER BY b.booking_date DESC
            """, (f"%{search_user}%",)).fetchall()
            conn.close()

            if user_bookings:
                for b in user_bookings:
                    badge_color = "orange" if b['status'] == "PENDING" else ("green" if b['status'] == "APPROVED" else "red")
                    st.markdown(f"**Booking ID #{b['id']}** | **{b['resource_name']}** | Date: `{b['booking_date']}` | Slot: `{b['start_time']} - {b['end_time']}`")
                    st.markdown(f"Status: :{badge_color}[{b['status']}]")
                    if b['admin_notes']:
                        st.caption(f"Admin Note: {b['admin_notes']}")
                    
                    if b['status'] in ['PENDING', 'APPROVED']:
                        if st.button(f"Cancel Request #{b['id']}", key=f"cancel_{b['id']}"):
                            conn = get_connection()
                            conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE id = ?", (b['id'],))
                            conn.commit()
                            conn.close()
                            st.rerun()
                    st.markdown("---")
            else:
                st.info("No bookings found under this name.")

    with tab3:
        st.subheader("Current Approved Reservations")
        filter_date = st.date_input("View Bookings for Date", date.today(), key="view_date")
        conn = get_connection()
        approved = conn.execute("""
            SELECT r.name, b.start_time, b.end_time, b.user_role
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            WHERE b.booking_date = ? AND b.status = 'APPROVED'
            ORDER BY b.start_time ASC
        """, (filter_date.strftime("%Y-%m-%d"),)).fetchall()
        conn.close()

        if approved:
            st.table([dict(row) for row in approved])
        else:
            st.info("All resources are completely free for this date.")

# ----------------- VIEW 2: ADMINISTRATOR -----------------
else:
    st.title("Admin Approval Dashboard & Audit Logs")
    
    tab_admin1, tab_admin2 = st.tabs(["Pending Approvals", "Full Booking History"])
    
    with tab_admin1:
        st.subheader("Pending Requests")
        conn = get_connection()
        pending = conn.execute("""
            SELECT b.id, b.resource_id, r.name as resource_name, b.user_name, b.user_role, b.booking_date, b.start_time, b.end_time
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            WHERE b.status = 'PENDING'
            ORDER BY b.created_at ASC
        """).fetchall()
        conn.close()

        if not pending:
            st.success("No pending booking requests.")
        else:
            for item in pending:
                with st.container(border=True):
                    col_info, col_actions = st.columns([2, 1])
                    with col_info:
                        st.markdown(f"### {item['resource_name']}")
                        st.write(f"**Requested By:** {item['user_name']} ({item['user_role']})")
                        st.write(f"**Date:** {item['booking_date']} | **Time:** {item['start_time']} - {item['end_time']}")
                    
                    with col_actions:
                        note = st.text_input("Admin Comment", key=f"note_{item['id']}")
                        
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if st.button("Approve", key=f"app_{item['id']}"):
                                # Final double-booking sanity check
                                if check_overlap(item['resource_id'], item['booking_date'], item['start_time'], item['end_time']):
                                    st.error("Cannot approve: A previously approved booking now clashes with this slot!")
                                else:
                                    conn = get_connection()
                                    conn.execute("UPDATE bookings SET status = 'APPROVED', admin_notes = ? WHERE id = ?", (note, item['id']))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
                        with btn_col2:
                            if st.button("Reject", key=f"rej_{item['id']}"):
                                conn = get_connection()
                                conn.execute("UPDATE bookings SET status = 'REJECTED', admin_notes = ? WHERE id = ?", (note, item['id']))
                                conn.commit()
                                conn.close()
                                st.rerun()

    with tab_admin2:
        st.subheader("System Booking Audit Log")
        conn = get_connection()
        logs = conn.execute("""
            SELECT b.id, r.name as resource_name, b.user_name, b.booking_date, b.start_time, b.end_time, b.status, b.admin_notes
            FROM bookings b
            JOIN resources r ON b.resource_id = r.id
            ORDER BY b.id DESC
        """).fetchall()
        conn.close()
        
        if logs:
            st.dataframe([dict(l) for l in logs], width="stretch")
        else:
            st.info("No logs registered.")
