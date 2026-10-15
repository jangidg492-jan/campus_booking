from datetime import date, datetime, time

import streamlit as st

from database import (
    approve_booking,
    authenticate_user,
    create_booking,
    database,
    delete_own_booking,
    init_db,
    register_user,
    update_booking,
)


st.set_page_config(page_title="Smart Campus Resource Booking", layout="wide")
init_db()


def show_authentication():
    st.title("Campus portal")
    st.caption("Sign in or create a student, professor, or researcher account.")
    login_tab, register_tab = st.tabs(["Log in", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email address", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in", type="primary")
        if submitted:
            user = authenticate_user(email, password)
            if user is None:
                st.error("Invalid email or password.")
            else:
                st.session_state["user"] = user
                st.rerun()

    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name", key="register_name")
            email = st.text_input("Email address", key="register_email")
            user_role = st.selectbox(
                "Campus role", ["Student", "Professor", "Researcher"]
            )
            password = st.text_input(
                "Password (at least 12 characters)",
                type="password",
                key="register_password",
            )
            confirm_password = st.text_input(
                "Confirm password", type="password", key="register_confirm_password"
            )
            submitted = st.form_submit_button("Create account", type="primary")
        if submitted:
            if password != confirm_password:
                st.error("The passwords do not match.")
            else:
                try:
                    st.session_state["user"] = register_user(
                        name, email, user_role, password
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success("Account created. You are now signed in.")
                    st.rerun()


if "user" not in st.session_state:
    show_authentication()
    st.stop()

current_user = st.session_state["user"]
is_admin = current_user["role"] == "ADMIN"

with st.sidebar:
    st.title("Campus portal")
    st.write(f"**{current_user['name']}**")
    st.caption(
        "Administrator" if is_admin else f"{current_user['user_role']} account"
    )
    if st.button("Log out"):
        del st.session_state["user"]
        st.rerun()


def load_resources():
    with database() as conn:
        return conn.execute("SELECT * FROM resources ORDER BY name").fetchall()


def validate_slot(start_val, end_val):
    if start_val >= end_val:
        st.error("End time must be after start time.")
        return False
    return True


def render_booking_form(resources, user, *, existing=None, key_prefix="new"):
    resource_options = {row["name"]: row["id"] for row in resources}
    if not resource_options:
        st.info("There are no bookable resources yet.")
        return

    resource_names = list(resource_options)
    if existing:
        current_resource = next(
            (
                name
                for name, resource_id in resource_options.items()
                if resource_id == existing["resource_id"]
            ),
            resource_names[0],
        )
        default_date = date.fromisoformat(existing["booking_date"])
        default_start = datetime.strptime(existing["start_time"], "%H:%M").time()
        default_end = datetime.strptime(existing["end_time"], "%H:%M").time()
    else:
        current_resource = resource_names[0]
        default_date = date.today()
        default_start = time(9, 0)
        default_end = time(10, 0)

    if default_date < date.today():
        st.info("Past bookings cannot be edited.")
        return

    with st.form(f"{key_prefix}_form"):
        col1, col2 = st.columns(2)
        with col1:
            selected_name = st.selectbox(
                "Resource",
                resource_names,
                index=resource_names.index(current_resource),
                key=f"{key_prefix}_resource",
            )
            booking_date = st.date_input(
                "Booking date",
                value=default_date,
                min_value=date.today(),
                key=f"{key_prefix}_date",
            )
        with col2:
            start_val = st.time_input(
                "Start time", value=default_start, key=f"{key_prefix}_start"
            )
            end_val = st.time_input(
                "End time", value=default_end, key=f"{key_prefix}_end"
            )
        submitted = st.form_submit_button(
            "Update booking" if existing else "Submit request",
            type="primary",
        )

    if submitted and validate_slot(start_val, end_val):
        values = (
            resource_options[selected_name],
            booking_date.strftime("%Y-%m-%d"),
            start_val.strftime("%H:%M"),
            end_val.strftime("%H:%M"),
        )
        try:
            if existing:
                update_booking(user["id"], existing["id"], *values)
                st.success("Booking updated.")
            else:
                create_booking(user, *values)
                st.success("Request submitted and is waiting for administrator approval.")
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()


if not is_admin:
    st.title("Smart campus resource and room booking")
    directory_tab, bookings_tab, availability_tab = st.tabs(
        ["Resources and booking", "My bookings", "Availability"]
    )
    resources = load_resources()

    with directory_tab:
        st.subheader("Bookable spaces and equipment")
        for resource in resources:
            with st.expander(
                f"{resource['name']} ({resource['type']}) · Capacity: {resource['capacity'] or 'Not specified'}"
            ):
                st.write(f"**Specs:** {resource['specs'] or 'Not specified'}")
                st.write(f"**Guidelines:** {resource['guidelines'] or 'None'}")

        st.divider()
        st.subheader("Submit a reservation request")
        render_booking_form(resources, current_user)

    with bookings_tab:
        st.subheader("Your reservation requests")
        with database() as conn:
            user_bookings = conn.execute(
                """
                SELECT b.id, b.resource_id, r.name AS resource_name, b.booking_date,
                       b.start_time, b.end_time, b.status, b.admin_notes
                FROM bookings b
                JOIN resources r ON r.id = b.resource_id
                WHERE b.user_id = ?
                ORDER BY b.booking_date DESC, b.start_time
                """,
                (current_user["id"],),
            ).fetchall()

        if not user_bookings:
            st.info("You have not submitted any booking requests.")
        for booking in user_bookings:
            with st.expander(
                f"#{booking['id']} · {booking['resource_name']} · {booking['booking_date']} · "
                f"{booking['start_time']}–{booking['end_time']} · {booking['status']}"
            ):
                if booking["admin_notes"]:
                    st.caption(f"Administrator note: {booking['admin_notes']}")
                if booking["status"] == "PENDING":
                    render_booking_form(
                        resources,
                        current_user,
                        existing=booking,
                        key_prefix=f"edit_{booking['id']}",
                    )
                    if st.button(
                        "Delete pending booking",
                        key=f"delete_booking_{booking['id']}",
                        type="secondary",
                    ):
                        try:
                            delete_own_booking(current_user["id"], booking["id"])
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.rerun()
                elif booking["status"] == "APPROVED":
                    if st.button(
                        "Cancel approved booking",
                        key=f"cancel_booking_{booking['id']}",
                    ):
                        with database() as conn:
                            conn.execute(
                                """
                                UPDATE bookings SET status = 'CANCELLED'
                                WHERE id = ? AND user_id = ? AND status = 'APPROVED'
                                """,
                                (booking["id"], current_user["id"]),
                            )
                        st.rerun()

    with availability_tab:
        st.subheader("Approved reservations")
        filter_date = st.date_input("View bookings for date", date.today())
        with database() as conn:
            approved = conn.execute(
                """
                SELECT r.name, b.start_time, b.end_time, b.user_role
                FROM bookings b
                JOIN resources r ON r.id = b.resource_id
                WHERE b.booking_date = ? AND b.status = 'APPROVED'
                ORDER BY b.start_time
                """,
                (filter_date.strftime("%Y-%m-%d"),),
            ).fetchall()
        if approved:
            st.table([dict(row) for row in approved])
        else:
            st.info("All resources are available for this date.")

else:
    st.title("Administrator dashboard")
    approvals_tab, history_tab, resources_tab = st.tabs(
        ["Pending approvals", "Booking history", "Manage resources"]
    )

    with approvals_tab:
        st.subheader("Pending requests")
        with database() as conn:
            pending = conn.execute(
                """
                SELECT b.id, b.resource_id, r.name AS resource_name, b.user_name,
                       b.user_role, b.booking_date, b.start_time, b.end_time
                FROM bookings b
                JOIN resources r ON r.id = b.resource_id
                WHERE b.status = 'PENDING'
                ORDER BY b.created_at
                """
            ).fetchall()

        if not pending:
            st.success("No pending booking requests.")
        for item in pending:
            with st.container(border=True):
                col_info, col_actions = st.columns([2, 1])
                with col_info:
                    st.markdown(f"### {item['resource_name']}")
                    st.write(f"**Requested by:** {item['user_name']} ({item['user_role']})")
                    st.write(
                        f"**Date:** {item['booking_date']} · **Time:** "
                        f"{item['start_time']}–{item['end_time']}"
                    )
                with col_actions:
                    note = st.text_input("Administrator note", key=f"note_{item['id']}")
                    approve_col, reject_col = st.columns(2)
                    with approve_col:
                        if st.button("Approve", key=f"approve_{item['id']}"):
                            try:
                                approve_booking(item["id"], note)
                            except ValueError as exc:
                                st.error(str(exc))
                            else:
                                st.rerun()
                    with reject_col:
                        if st.button("Reject", key=f"reject_{item['id']}"):
                            with database() as conn:
                                conn.execute(
                                    """
                                    UPDATE bookings
                                    SET status = 'REJECTED', admin_notes = ?
                                    WHERE id = ? AND status = 'PENDING'
                                    """,
                                    (note, item["id"]),
                                )
                            st.rerun()

    with history_tab:
        st.subheader("Booking history")
        with database() as conn:
            logs = conn.execute(
                """
                SELECT b.id, r.name AS resource_name, b.user_name, b.user_role,
                       b.booking_date, b.start_time, b.end_time, b.status, b.admin_notes
                FROM bookings b
                JOIN resources r ON r.id = b.resource_id
                ORDER BY b.id DESC
                """
            ).fetchall()
        if not logs:
            st.info("No booking history yet.")
        for booking in logs:
            with st.expander(
                f"#{booking['id']} · {booking['resource_name']} · "
                f"{booking['user_name']} · {booking['status']}"
            ):
                st.write(
                    f"{booking['booking_date']} · {booking['start_time']}–"
                    f"{booking['end_time']} · {booking['user_role']}"
                )
                if booking["admin_notes"]:
                    st.caption(f"Administrator note: {booking['admin_notes']}")
                if st.button(
                    "Delete booking record",
                    key=f"admin_delete_booking_{booking['id']}",
                ):
                    with database() as conn:
                        conn.execute("DELETE FROM bookings WHERE id = ?", (booking["id"],))
                    st.rerun()

    with resources_tab:
        st.subheader("Resource catalog")
        resources = load_resources()
        resource_names = {row["name"]: row for row in resources}
        selected_name = st.selectbox(
            "Select a resource to edit or delete",
            ["— Create a new resource —", *resource_names.keys()],
        )
        selected_resource = resource_names.get(selected_name)
        resource_types = ["Room", "Hardware", "Other"]
        if selected_resource and selected_resource["type"] not in resource_types:
            resource_types.append(selected_resource["type"])
        with st.form("resource_form"):
            name = st.text_input(
                "Resource name", value=selected_resource["name"] if selected_resource else ""
            )
            resource_type = st.selectbox(
                "Type",
                resource_types,
                index=(
                    resource_types.index(selected_resource["type"])
                    if selected_resource
                    else 0
                ),
            )
            capacity = st.number_input(
                "Capacity",
                min_value=1,
                value=(
                    selected_resource["capacity"]
                    if selected_resource and selected_resource["capacity"]
                    else 1
                ),
            )
            specs = st.text_area(
                "Specifications",
                value=selected_resource["specs"] or "" if selected_resource else "",
            )
            guidelines = st.text_area(
                "Guidelines",
                value=selected_resource["guidelines"] or "" if selected_resource else "",
            )
            submitted = st.form_submit_button(
                "Update resource" if selected_resource else "Create resource",
                type="primary",
            )
        if submitted:
            if not name.strip():
                st.error("Resource name is required.")
            else:
                with database(immediate=True) as conn:
                    duplicate = conn.execute(
                        """
                        SELECT id FROM resources
                        WHERE name = ? COLLATE NOCASE AND id != ?
                        """,
                        (
                            name.strip(),
                            selected_resource["id"] if selected_resource else -1,
                        ),
                    ).fetchone()
                    if duplicate:
                        st.error("A resource with that name already exists.")
                    else:
                        if selected_resource:
                            conn.execute(
                                """
                                UPDATE resources
                                SET name = ?, type = ?, capacity = ?, specs = ?, guidelines = ?
                                WHERE id = ?
                                """,
                                (
                                    name.strip(),
                                    resource_type,
                                    capacity,
                                    specs.strip(),
                                    guidelines.strip(),
                                    selected_resource["id"],
                                ),
                            )
                        else:
                            conn.execute(
                                """
                                INSERT INTO resources
                                    (name, type, capacity, specs, guidelines)
                                VALUES (?, ?, ?, ?, ?)
                                """,
                                (
                                    name.strip(),
                                    resource_type,
                                    capacity,
                                    specs.strip(),
                                    guidelines.strip(),
                                ),
                            )
                if not duplicate:
                    st.success("Resource saved.")
                    st.rerun()

        if selected_resource and st.button(
            "Delete resource", type="secondary", key="delete_resource"
        ):
            deleted = False
            with database(immediate=True) as conn:
                booking_count = conn.execute(
                    "SELECT COUNT(*) FROM bookings WHERE resource_id = ?",
                    (selected_resource["id"],),
                ).fetchone()[0]
                if booking_count:
                    st.error("This resource has booking history and cannot be deleted.")
                else:
                    conn.execute(
                        "DELETE FROM resources WHERE id = ?", (selected_resource["id"],)
                    )
                    deleted = True
            if deleted:
                st.rerun()
